# Cover letter

Mentee: Udita  
Email: udita.23csai@nst.rishihood.edu.in  
GitHub: https://github.com/udita-0707  
Project: OpenTelemetry-Native Query and State Layers Migration ([jaegertracing/jaeger-ui#4278](https://github.com/jaegertracing/jaeger-ui/issues/4278))  
Term: LFX Mentorship 2026 Term 3 (Sep–Nov)  
Availability: full-time for the LFX term; no overlapping internship.

I am a final-year B.Tech CS (AI) student at Newton School of Technology (graduating 2027) and an active jaeger-ui contributor. Merged work includes [jaeger-ui#4054](https://github.com/jaegertracing/jaeger-ui/pull/4054) (Monitor/SPM dark-mode hover and design-token refactor under ADR 0010). Summary Fields ([jaeger-ui#4063](https://github.com/jaegertracing/jaeger-ui/pull/4063) and follow-ups) was split into independently mergeable PRs on the same layout-settings priority stack this project still has to finish. I work with Yuri Shkuro and Jonah Kowall on CNCF Slack.

Issue #4278 is not a greenfield OTLP client. The UI already speaks attributes, resources, events, and links, but a single trace still arrives over legacy `/api/traces/:id` and is reshaped in the browser. Redux is almost gone except the timeline dual-write (analytics middleware still keys on old action types). RFC 0007's `URL > heuristics > localStorage` stack is designed and not built, so a shared link still cannot reproduce the sender's view. The job is to finish those three migrations, delete what they replaced, and land the PRs already open against those seams rather than starting over.

That is the same discipline I have already used in this repository. #4063 (Summary Fields) was closed and split; the independently mergeable follow-ups that landed are HTTP status chips ([#4149](https://github.com/jaegertracing/jaeger-ui/pull/4149)) and span pills ([#4214](https://github.com/jaegertracing/jaeger-ui/pull/4214), [#4220](https://github.com/jaegertracing/jaeger-ui/pull/4220)), each leaving the timeline functional. At Razorpay I migrated 20+ Angular repos to 16+ and resolved 50+ transitive conflicts without a flag-day cutover, which is the same constraint as deleting the facade while Trace View stays up. The testing habit this plumbing needs is catching a regression that only appears when Redux and Zustand disagree on the same timeline click; each deletion step therefore keeps the UI up and has an interaction test, not only a typecheck.

I have read [jaeger-ui#4278](https://github.com/jaegertracing/jaeger-ui/issues/4278), RFC 0002 / 0004 / 0006 / 0007, ADR-0002 / 0004 / 0005, the open PRs named below, and the [application](https://www.jaegertracing.io/mentorship/applying/) and [for-mentees](https://www.jaegertracing.io/mentorship/for-mentees/) guidelines. The proposal follows.

---

Project: OpenTelemetry-Native Query and State Layers Migration  
Mentee: Udita  
Term: LFX 2026 Term 3 (Sep–Nov)  
Mentors: Yuri Shkuro, Jonah Kowall  
Upstream issue: https://github.com/jaegertracing/jaeger-ui/issues/4278

## 1. Problem statement

Jaeger UI is two-thirds of the way through three interlocking migrations, at three different stages (#4278).

The OpenTelemetry-native data path stopped at a deliberate decision. Components program against OTEL vocabulary through a facade (ADR-0002). Service discovery and search already use `/api/v3/`. Loading one trace does not. `hooks/useTraceLoading.ts` still calls the legacy `/api/traces/:id` path and `transformTraceData`. Every rendered trace is a Jaeger model wrapped in the browser. That is the first payload that pulls the entire OTLP model into the query layer: nested `resourceSpans` / `scopeSpans`, the recursive `AnyValue` union, events, links, status. How that model enters the codebase (generated types validated at the network boundary, or hand-written structural types with no runtime checks) is the central judgement, not an implementation detail.

The cost of leaving the facade in place is paid on the 80k-span path. Parsing, enrichment, and state updates all sit on that path. A design that is elegant at 100 spans and quadratic at 50,000 is not a design. The project is not finished when `/api/v3/traces/{id}` returns 200. It is finished when the facade, the legacy transformer, the legacy types, the upload round-trip, and (where policy allows) the v1 HTTP handlers in `jaeger-query` are gone, and the project stops paying for two of everything (RFC 0002 milestones 3.2, 3.4, Phase 4).

State management is close to done (RFC 0004). Two reducers remain. The timeline writes to both Redux and Zustand because analytics is a Redux middleware keyed on old action types; tracking has to move before that slice can die. The unified architecture (RFC 0006, RFC 0007) is designed, not built. Several contributors already have PRs on these seams. Refereeing those PRs is deliverable work.

## 2. Prerequisite answers

### Prerequisite 1. Wire-format analysis

Fetched 2026-08-16 from the POC's `jaegertracing/jaeger:2.20.0` at `http://localhost:16686`. Compared `GET /api/v3/traces/{id}` against `idl/swagger/api_v3/query_service.openapi.yaml` (`QueryService_GetTrace`) and `packages/jaeger-ui/src/api/v3/schemas.ts` (plus `generated-client.ts`, which `schemas.ts` re-exports for everything except TraceSummary constraints).

Two responses: a live cart span (`traceId=1b0c67a52a36e6f7baeb2df1043c05db`) and a probe span ingested over OTLP/HTTP JSON (`traceId=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`) that exercises every `AnyValue` arm, `kind=0`, events, links, and `intValue=9007199254740993` (`2^53+1`).

| Field | Spec claim | Observed encoding | `schemas.ts` match |
|---|---|---|---|
| HTTP body | Schema `$ref` is `TracesData` (`resourceSpans` at top level). Description says the JSON is wrapped in `{"result": ...}` and cannot be unmarshalled with JSONPb directly. | Both responses are exactly `{"result":{"resourceSpans":[...]}}`. Top-level keys are `["result"]` only. | No GetTrace schema at all. `client.ts` has no `getTrace()`. Generated `TracesData` starts at `resourceSpans` and would fail on the envelope. |
| `traceId` / `spanId` | OpenAPI `format: bytes` (base64 in OpenAPI JSON). Path parameter is documented separately as "Hex encoded 64 or 128 bit trace ID." OTLP/JSON treats IDs as hex. | 32-char lowercase hex (`1b0c67a52a36e6f7baeb2df1043c05db`) and 16-char hex (`3033bbca92fde2e8`). Base64 of those 16 bytes would be `GwxnpSo25ve66y3xBDwF2w==`; that string never appears. | Summaries: `traceIdHex` (`/^[0-9a-f]{32}$/i`) matches. Span path: generated `z.string()` with no hex check. `spanIdHex` exists in `schemas.ts` and is unused. |
| `AnyValue.bytesValue` | `type: string`, `format: bytes` (base64). | Probe `probe.bytes` came back `"bytesValue":"AQIDBA=="` (base64 of `01 02 03 04`). | Generated `z.string()`. Same type as `traceId`, so a single `format: bytes` rule cannot cover both IDs and `bytesValue`. |
| `startTimeUnixNano` / `endTimeUnixNano` / `intValue` | proto3 JSON: int64 as a decimal string (TraceSummary text says this is to avoid float64 loss above `2^53`). | Quoted strings. Cart: `"1786876531335214700"`. Probe: `"1786870000000000001"` and `"intValue":"9007199254740993"`. `Number(9007199254740993) === 9007199254740992`. | Summaries: `z.string().regex(/^\d+$/)`. Generated span timestamps and `intValue` are `z.string()` with no digit check. |
| `kind` | integer, `format: enum`. | Cart CLIENT span: `"kind":3`. Probe ingested with `kind: 0` (`SPAN_KIND_UNSPECIFIED`): field omitted. | Generated `kind: z.number().int()` under `.partial()`, so omission passes. Treating missing `kind` as invalid would reject every unset-kind span. |
| `status` | object; "when Status isn't set, assume `STATUS_CODE_UNSET` (code = 0)". | Cart unset: `"status":{}` (empty object, not omitted, no `code: 0`). Probe error: `"status":{"message":"probe error","code":2}`. | Generated Status is `.partial()`, so `{}` passes. No `GetTrace` consumer in `schemas.ts`. |
| Zero / empty fields | proto3 JSON omits defaults. | Root probe omitted `parentSpanId` and `flags`. `droppedAttributesCount` / `droppedEventsCount` / `droppedLinksCount` omitted when 0. Events and links omitted when empty (cart). | Generated Span is `.partial().passthrough()`, so omitted zeros pass. Strictifying those fields to required would break the live payload. |
| Attribute / event order | Spec does not require sort order. Attribute keys must be unique. | Ingested `z.last` before `a.first`; GetTrace returned keys sorted (`a.first`, then `probe.*`, then `z.last`). Events ingested `z-event` then `a-event`; returned `a-event` then `z-event`. Event attributes sorted `a`, `b`. | No order assertion in `schemas.ts`. Tests that `toEqual` an unsorted fixture against GetTrace will flake. This is `SortAttributesAndEventsAdjuster` (jaeger#9212), not a parse bug. |

`schemas.ts` today validates `/api/v3/services`, `/api/v3/operations`, and `/api/v3/trace-summaries` only. TraceSummary `traceId` is already hex, and the nano timestamps are already decimal strings; that half of the spec matches the wire. The single-trace path has no runtime schema, and the generated `TracesData` schema does not know about the `result` envelope or the hex-vs-base64 split on `format: bytes`. Those two facts are what Prerequisite 2 has to encode: unwrap `result` first, then validate OTLP, with a hex constraint on IDs and a base64 constraint on `bytesValue`.

### Prerequisite 2. Generated vs hand-written OTLP types

Position: generate the wire types from the OpenAPI spec and validate them at runtime with Zod, then map into the existing enriched domain model. Hand-enrich the generated schema where OpenAPI cannot express the recursive `AnyValue` union or the two encodings of protobuf `bytes` (hex `traceId`/`spanId` vs base64 `bytesValue`).

What this gives up: schema generation adds build-time complexity (`openapi-zod-client` or equivalent in the UI package script). Generated files must be treated as generated (same rule as Jaeger's `*.pb.go`). Reviewers will see larger diffs on spec bumps.

What this buys: a malformed `AnyValue` arm fails at the network boundary, before enrichment walks 80k spans. Hand-written types pass against hand-written fixtures and fail against a real server. That is the failure mode #4278 warns about, and it is already visible in `src/api/v3/client.ts` plus the fixtures under `src/utils/fixtures/`. ADR-0002 already validates `/api/v3/` search responses; extending that pattern to a full trace is consistent, not a new religion.

The envelope (`{"result":{"resourceSpans":[...]}}`) is transport. The Zod schema for OTLP starts after a one-line unwrap, the same seam as today's `traceID`/`traceId` normalisation in `schemas.ts`. Validating the gRPC-gateway wrapper would make a future unary client a schema change. Stripping first keeps the schema OTLP and keeps one hand-written line outside the generated file, which is the accepted tradeoff.

### Prerequisite 3. Migration and deletion plan

Each step removes a named piece of legacy code and leaves the UI functional. Pattern: the Summary Fields decomposition (#4063 closed, then #4149 / #4214 / #4220), each PR independently mergeable.

**Step 1. OTLP trace loading over `/api/v3/` with Zod validation.**  
Deletes: the browser-side facade reshape on the single-trace path (`OtelSpanFacade` / wrap in `useTrace` / `useTraces` once #4129's parser is connected to a validated schema).  
UI still does: search, compare, DAG, Monitor, file upload (legacy).  
Tests: span-for-span parity of the enriched model against the legacy path on a fixture and on one large trace (thousands of spans, not 40). `getTrace()` exists on `JaegerClient`. RFC 0002 milestone 3.2 marked in the same PR.

**Step 2. Legacy transformer removal.**  
Deletes: `transformTraceData` and the Jaeger-model to enriched-model transformer used by `useTraceLoading`.  
UI still does: everything step 1 does, still served from v3.  
Tests: no remaining import of `transformTraceData` outside upload (until step 5). Revert is one PR.

**Step 3. Legacy type definitions removed.**  
Deletes: jaeger-specific span/trace type files that exist only to feed the facade.  
UI still does: render from the enriched OTEL model only.  
Tests: `tsc` and the package test suite; any leftover `JaegerTrace` / `JaegerSpan` reference is a compile failure, not a runtime surprise.

**Step 4. Redux fully removed.**  
Deletes: remaining reducers, store, provider, the four Redux dependencies, and the dual-write on the timeline. Prerequisite: move analytics off the Redux middleware (RFC 0004 phases 1c, 2f, 2g, 4).  
UI still does: collapse, zoom, find, detail panel, with state in Zustand + TanStack Query (ADR-0004 / ADR-0005 inventory).  
Tests: timeline interaction tests rewritten off `duck.ts` action types. This step is the one that is hardest to revert in isolation; it lands after analytics has a new home, not before.

**Step 5. Uploaded OTLP files parsed in the browser.**  
Deletes: the backend round-trip that converts uploaded OTLP (`FileLoader` / transform endpoint).  
UI still does: upload, with the same Zod parser as the network path.  
Tests: the same awkward fixture (all `AnyValue` arms, 2^53+1 int, omitted `kind`) parsed client-side. Event-order divergence vs the server adjuster chain (`SortAttributesAndEventsAdjuster` in `jaegerquery/internal/adjuster/sort.go`, jaeger#9212) is an explicit contract note in the PR, not an inherited surprise.

Backend v1 HTTP deprecation in `jaegertracing/jaeger` is a follow-on after step 5, and is what gets cut if the UI work overruns (Prerequisite 5).

### Prerequisite 4. Engaging with open PRs

Refereeing is scheduled work, not background noise. Review within 48 hours of a ping. A merged PR from another contributor that I shepherded counts as a met deliverable (#4278). I will not open a competing implementation of a PR that is already green.

In-flight work I will engage, by number:

| PR | What it is | Engagement |
|---|---|---|
| [#4129](https://github.com/jaegertracing/jaeger-ui/pull/4129) (`feat(api/v3): Load traces via OTLP parser`, Me-Priyank) | Milestone 3.2 parser + `getTrace()`, streaming `result` unwrap. Rebased, one merge conflict, open `genAIKind` question. | Review within 48 hours. Write down the design decision that unblocks it: connect this parser to a Zod-validated boundary rather than replacing the parser; decide `genAIKind` with Me-Priyank and #4362 rather than unilaterally. Help it merge. |
| [#3977](https://github.com/jaegertracing/jaeger-ui/pull/3977) | Extend OTLP Zod schema coverage. | Same schema decision as Prerequisite 2. If it generates more of `AnyValue` correctly, land it under step 1 instead of regenerating from scratch. |
| [#4371](https://github.com/jaegertracing/jaeger-ui/pull/4371) | Generated Zod schemas for the structured query filter. | Review as the search-side half of the same generation pipeline. Do not let filter schemas and trace schemas diverge on int64 / bytes rules. |
| [#3852](https://github.com/jaegertracing/jaeger-ui/pull/3852), [#3853](https://github.com/jaegertracing/jaeger-ui/pull/3853), [#4112](https://github.com/jaegertracing/jaeger-ui/pull/4112) | RFC 0007 layout: URL utilities, persist flag on store setters, Zustand persist middleware. | These are the five-PR stack RFC 0007 named. Agree the `URL > heuristics > localStorage` seam with the authors; a shared link that overwrites the recipient's defaults is a failed deliverable. |
| [#4376](https://github.com/jaegertracing/jaeger-ui/pull/4376), [#4377](https://github.com/jaegertracing/jaeger-ui/pull/4377) | Dead `hoverIndentGuideIds` Redux state; `shouldDisableCollapse` moved off `duck.ts`. | Land as step-4 prep. Smaller than moving analytics; they shrink the residual Redux surface ADR-0005 lists. |
| [#4323](https://github.com/jaegertracing/jaeger-ui/pull/4323), [#4324](https://github.com/jaegertracing/jaeger-ui/pull/4324) | `OtelSpanFacade` null/array guards. | Review as facade-lifetime patches. They must not become a reason to keep the facade after step 1. |
| [#4283](https://github.com/jaegertracing/jaeger-ui/pull/4283) | Analytics: preserve zero event values. | The dual-write cannot die until tracking no longer keys on Redux actions. Treat this PR as the start of that move, not as unrelated polish. |
| [#4330](https://github.com/jaegertracing/jaeger-ui/pull/4330) | Poll `useTrace` / `useTraces` for partial traces. | Must keep working after the v3 client replaces the legacy fetch. Review against #4129's streaming unwrap. |
| [#4337](https://github.com/jaegertracing/jaeger-ui/pull/4337), [#4199](https://github.com/jaegertracing/jaeger-ui/pull/4199) | Upload / transform-backend error reporting. | Step 5 deletes that backend. Until then, do not let upload errors be mislabeled as parse errors. |

### Prerequisite 5. Timeline

Weeks 1–2 are research only: no feature commits. Output is the filled wire-format table, a written decision on generated Zod vs hand-written types (this proposal's position, updated if the live bytes disagree), and a one-page map of the open PRs above with a merge-or-rebase call on each. Weeks 3–12 implement the deletion sequence. Demo-able artifacts every 2–3 weeks. If behind, backend v1 HTTP endpoint deprecation in `jaegertracing/jaeger` is deferred. Frontend work ships first.

## 3. Non-goals

This project finishes the UI data path, Redux removal, and RFC 0007 layout stack. It does not build Nabil Salah's BYOA agent, ACP sidecar, or NL search ([#7832](https://github.com/jaegertracing/jaeger/issues/7832)). It does not author Skills ([#8440](https://github.com/jaegertracing/jaeger/issues/8440), Soumya Raikwar). It does not add GenAI trace visualization, icons, or a side panel ([#8401](https://github.com/jaegertracing/jaeger/issues/8401), Swetalin Rout). Those surfaces consume the enriched model this migration leaves behind; they are not this term's PRs.

## 4. Proposed approach

The plans of record (RFC 0002 / 0004 / 0006 / 0007, ADR-0002 / 0004 / 0005) already say what to build. The non-obvious constraint is landing order: the three migrations are not a pipeline.

RFC 0007 URL work (#3852, #3853, #4112) does not wait on `/api/v3/traces/{id}`. Redux removal does wait: analytics has to leave the middleware (#4283) before #4376 / #4377 are more than shrinking ADR-0005's leftover surface, and before `duck.ts` can die. Facade-lifetime patches (#4323, #4324) are mergeable now and must not accrue into a reason to keep `OtelSpanFacade` after #4129 is connected to a Zod boundary. Upload error reporting (#4199, #4337) is a stop-gap; step 5 deletes that backend. Partial-trace polling (#4330) has to be re-checked against #4129's `result` unwrap or the v3 client drops in-flight traces. Filter schemas (#4371) and trace schemas (#3977) share int64 / bytes rules; they land as one pipeline, not two.

After that order: `getTrace(id)` unwraps `result`, Zod-parses, and enriches into the model components already use. RFC status boxes get checked in the same PR that deletes the old path. Parse and enrich are measured on a large trace, not a 40-span fixture; attribute/event equality tests must not assume send order (the server sorts). Backend v1 HTTP deprecation waits until the UI has stopped calling it.

## 5. Milestone plan (12 weeks)

| Week | Milestone | Deliverable | Success criteria |
|---|---|---|---|
| 1–2 | Research (no feature commits) | Confirm wire-format table against the term's Jaeger build + PR map | Maintainer reads one table (field / spec / bytes) and a list of open PRs with merge-or-rebase; under five minutes |
| 3–4 | Zod boundary + #4129 | Validated `/api/v3/traces/{id}` load | Opening a trace in the UI uses `getTrace()`; legacy `/api/traces/:id` is not on that path; `npm test` green; RFC 0002 3.2 box checked in the same PR |
| 5–6 | Delete transformer + types | Steps 2–3 | `transformTraceData` has no remaining single-trace callers; `tsc` fails if a deleted Jaeger span type is reintroduced |
| 7–8 | RFC 0007 + residual Redux prep | Land or rebase #3852 / #3853 / #4112 / #4376 / #4377 | Shared URL reproduces span-name column width and detail-panel mode; hover-guide Redux state gone |
| 9–10 | Redux gone | Step 4 | No `react-redux` / `redux` in `package.json`; timeline interactions still work; analytics events still fire |
| 11–12 | Browser upload + docs | Step 5 + RFC status | File upload parses OTLP in-browser; transform backend unused; RFC 0002 Phase 4 annotated |

What I cut first if behind: backend v1 HTTP endpoint deprecation in the `jaeger` repo. The UI migration still ships.

## 6. Why me

I already work in the Trace Timeline files this migration still has to keep green (`SpanBarRow`, `spanPills`, `VirtualizedTraceView` in #4149 / #4214 / #4220) and in Monitor URL persistence (#4119 / #4182), which is the same `URL > defaults` problem RFC 0007 has not finished for Trace View. Razorpay's 20-repo Angular 16+ migration is the same constraint (delete the old path, keep the product up). Those chips and pills are live attribute rendering on the timeline, not a tutorial. The Summary Fields work was decomposed from #4063 into independently mergeable PRs following ADR 0010, each leaving the UI functional; that decomposition pattern is exactly how this migration must be executed, and I have already applied it in this codebase under review from the same mentors.

## 7. Risk and mitigation

Wire-format divergence between the OpenAPI spec and the real `/api/v3/` response may surface more edge cases than the two-week research window allows. Mitigation: scope the initial Zod schema to the fields actually used by the enriched domain model, not the full OTLP spec. Expand field coverage iteratively as downstream consumers need it.

## 8. Blog post outline

Hariom Gupta, Harshith Mente, and Saransh Shankar each published a post-mentorship write-up; this term's post will do the same for #4278. It will cover the decomposition pattern for a large migration without a flag day (what each PR deleted, what the UI could still do), and the wire-format lessons from putting OTLP in the browser (generated Zod at the boundary, the `result` unwrap, hex vs base64 `bytes`, quoted int64, and why a fixture that passes `Number()` on round timestamps is not a test).
