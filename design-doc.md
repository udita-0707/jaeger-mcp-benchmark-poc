# Design: Evaluating Jaeger MCP Tools and Skills

POC for [jaegertracing/jaeger#9135](https://github.com/jaegertracing/jaeger/issues/9135). This document is the methodology the harness implements, not a proposal for new architecture.

---

## 1. Problem

Jaeger's AI assistant reasons over traces through two layers that were designed by intuition and have never been measured against each other. The **tools** are registered in [`cmd/jaeger/internal/extension/jaegerquery/internal/mcptools/server.go`](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/internal/extension/jaegerquery/internal/mcptools/server.go): nine handlers (`get_services`, `get_span_names`, `search_traces`, `get_span_details`, `get_trace_errors`, `get_trace_topology`, `get_critical_path`, `get_service_dependencies`, `read_skill`) served session-free at `/api/ai/mcp/` on the query port. On current `main` that is gated by `extensions.jaeger_query.ai.mcp: {}` ([`cmd/jaeger/internal/all-in-one.yaml`](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/internal/all-in-one.yaml)); the last *released* tag that serves MCP is **v2.20.0**, which still uses `ai.enable_mcp: true` — that is what this POC's compose file pins, because `jaegertracing/jaeger:latest` was still v2.19.0 and rejects the `mcp` key. Input and output shapes live in [`mcptools/internal/types/`](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/internal/extension/jaegerquery/internal/mcptools/internal/types/). The **Skills** are Soumya's [#8440](https://github.com/jaegertracing/jaeger/issues/8440) work: declarative Markdown playbooks, not plugins, discovered by progressive disclosure. The catalog is [`mcptools/skills/SKILL.md`](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/internal/extension/jaegerquery/internal/mcptools/skills/SKILL.md); the two built-ins are [`error-root-cause/SKILL.md`](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/internal/extension/jaegerquery/internal/mcptools/skills/error-root-cause/SKILL.md) (procedure: `get_trace_errors` → `get_trace_topology` → `get_span_details`) and [`detect-n-plus-one/SKILL.md`](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/internal/extension/jaegerquery/internal/mcptools/skills/detect-n-plus-one/SKILL.md). Server-level steering is the embedded [`INSTRUCTIONS.md`](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/internal/extension/jaegerquery/internal/mcptools/INSTRUCTIONS.md). Frontmatter `allowed-tools` is advisory — nothing in Go enforces it. Until we A/B the *shape* of a tool (granular `get_span_details` vs. a composite that pre-summarizes a fault) and the *wording* of a Skill (the five-step procedure in `error-root-cause` vs. a goal-oriented equivalent) against the same seeded fault, default configuration is a guess, and every new Skill inherits that guess.

"Trace-solvable" is the isolation criterion because this project measures the MCP + Skills surface, not a generic SRE agent. A fault whose root cause is visible on a span — status code, status message, attributes, parent-child path — can be solved with the nine tools above and nothing else. Faults that require application logs, config files, or out-of-band context would score the agent's ability to leave Jaeger, which is Nabil's BYOA/ACP work ([#7832](https://github.com/jaegertracing/jaeger/issues/7832)), not this harness. Concrete example: OpenTelemetry Demo `cartFailure` at `100%` makes `CartService.EmptyCart` route to a Valkey store at `badhost:1234` (`src/cart/src/Program.cs`). The `.NET` instrumentation records `oteldemo.CartService/EmptyCart` with status `Error` and message `Can't access cart storage. …`. That pattern is unambiguous from spans: a non-OK status, a message that names storage access as the failure, and a parent-child chain from checkout/frontend into `cart`. No log line is required. Evidence markers are therefore span-level (`oteldemo.CartService/EmptyCart`), never service-level (`cart`) — `get_services` returns every service name, so a service-level marker would make steps-to-evidence trivially 1 on the first call.

---

## 2. Trace-solvable fault isolation

A scenario is **trace-solvable** if and only if all three hold:

1. A specific span has a non-OK status code (`Error`, not `Unset` or `Ok`).
2. The error message or an attribute on that span names the root cause (not merely that *something* failed).
3. The causal chain from that span to the user-visible failure is reconstructible from parent-child relationships (`get_trace_topology.path`, or `parent_span_id` on `get_span_details`) without log context.

**Disqualified:** faults whose discriminating signal lives in application logs, process config, or host metrics that are not span-derived (SPM RED metrics computed from spans are allowed; CPU-stolen-by-GC with no span error is not — `adHighCpu` / `adManualGc` show inflated `self_time_us` and do not name the mechanism). Faults that are currently no-ops in the seed environment are documented, not scored: see `productCatalogFailure` (`status: broken`).

**Verification checklist** (run on every candidate before it enters the suite):

1. Enable the fault, capture one trace, open it in Jaeger UI. Confirm a span with `status.code = Error`.
2. Read that span's `status.message` and attributes. Confirm the seeded cause is named there (not only in a log body or a resource attribute that every span on the service carries).
3. Walk `parent_span_id` / topology `path` from that span to the root. Confirm the user-visible failure is an ancestor, not a sibling in a different tree.
4. Confirm the evidence marker is an operation name that does **not** appear in `get_services` or in the static tool descriptions (guard against the steps-to-evidence contamination in [#9135](https://github.com/jaegertracing/jaeger/issues/9135)).
5. Blind reconstruction: given only the MCP tool outputs (no demo source, no logs), write the one-sentence ground truth. If you cannot, the scenario is not trace-solvable.

---

## 3. Evaluation loop design

**Framework: Opik.** The one technical reason over Langfuse or Arize Phoenix: Opik ships a native [`TrajectoryAccuracy`](https://www.comet.com/docs/opik/evaluation/metrics/trajectory_accuracy) metric that scores a ReAct-style list of `{thought, action, observation}` steps plus `final_result` — the same structure this harness records — and accepts custom `BaseMetric` subclasses so call-error-rate, steps-to-evidence, and context-bloat become experiment columns on the traces `@track` already logged. Langfuse is generation/trace observability and prompt management; Phoenix is embedding/RAG evaluation. Neither treats a tool-call trajectory as a first-class scored object. This POC scores locally (`harness/score.py`) so the repo runs without an Opik server; the mentorship wires the same JSONL into Opik experiments.

**LLM: `gemini-3.5-flash`** via Google AI Studio (`GEMINI_API_KEY`), temperature `0` (was `gemini-1.5-flash`; that model and `gemini-2.5-flash` 404 for new AI Studio keys as of 2026-08-16). Flash is cheap enough that a 2×2 A/B (tool shape × Skill wording) × N scenarios stays in a student's API budget; it has native function calling, which is the whole point of measuring MCP tool schemas; and Jaeger's existing AI sidecar already speaks Gemini, so the harness evaluates the model family operators actually run. All provider calls go through `harness/llm.py:call_llm(prompt, tools)` so swapping the model does not touch the evaluation loop. The harness drives the **session-free** `/api/ai/mcp/` endpoint, not the ACP sidecar — otherwise tool-shape × Skill effects are confounded by BYOA routing ([#7832](https://github.com/jaegertracing/jaeger/issues/7832)).

**Four metrics** (plus the process/outcome split from Cloud-OpsBench; OpenRCA ICLR'25 scores final-answer exact match only and is not used here):

| Metric | Definition | "Good" |
|---|---|---|
| **Call error rate** | `(invalid tool calls) / (total tool calls)` per run. Invalid = unregistered name, schema-failing arguments, or MCP `isError`. Empty-but-successful results are *not* errors (they are often the correct answer). | 0 on well-schema'd tools. A 0.00 that coincides with a 47-call cycle is a different failure mode (repetition); noted, not folded into this number. |
| **Steps to evidence** | 1-based index of the first tool response whose body contains the ground-truth **span/operation name**. `None` if the run ends without it. | Lower is better, but a composite tool that internally does the walk will win by moving reasoning out of the agent — report that arm in a separate column, not ranked against granular tools. |
| **Context bloat** | `(sum of tool-response tokens) / (minimum tokens theoretically needed)`. Minimum is estimated from the ground-truth evidence span's serialized size (status + identifying attributes + topology path), not from the full trace. Measured on delivered response text (the wire payload is ~2× because go-sdk duplicates `structuredContent` and `content[].text`). Static `tools/list` schemas are reported separately; they are a per-turn constant, not a between-arm effect. | Ratio near 1. Ratios >> 1 mean the tool returned spans/attributes the answer did not use. |
| **Root-cause accuracy** | Binary. 1 iff the final answer matches an acceptable variant in the scenario's `ground_truth.md` (locus: service + operation + named cause). Mechanism names that are not in the spans (e.g. "CPU" for `adHighCpu`) score 0. | 1. |

**Trajectory capture.** Each run writes `trajectories/<scenario>_<variant>.json`:

```json
{
  "scenario": "cart_failure",
  "llm": "gemini-3.5-flash",
  "tool_variant": "granular",
  "skill_variant": "stepwise",
  "run_timestamp": "ISO8601",
  "final_answer": "…",
  "trajectory": [
    {
      "step": 1,
      "tool_name": "get_trace_errors",
      "input": {"trace_id": "…"},
      "response_length_tokens": 840,
      "response_summary": "first 200 chars",
      "timestamp_ms": 0
    }
  ]
}
```

This is Cloud-OpsBench's process object (the `T = [(t, a, o), …]` sequence) plus OpenRCA-style structured final answer, scored separately.

---

## 4. A/B variant design

Variants are files under `harness/variants/`. They are production-shaped enough to drop onto `ai.mcp.skills_dir` or to compare against `types.GetSpanDetailsInput` / a proposed composite. The harness `--variant` flag selects which tool *surface* the model sees; `--skill` selects which Skill text is injected. The live MCP server is not modified — high-level tools are composed client-side from the real nine, so a win cannot be "we changed Jaeger."

### Pair 1 — Tool granularity

**Variant A (granular):** the actual `get_span_details` schema from [`types/get_span_details.go`](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/internal/extension/jaegerquery/internal/mcptools/internal/types/get_span_details.go). One call fetches attributes/events/status for named span IDs; the agent must obtain those IDs first (`get_trace_topology.path` or `get_trace_errors`). See `harness/variants/tool_granular.json`.

**Variant B (high-level):** a proposed `analyze_trace_fault` tool that, given only `trace_id`, runs `get_trace_errors` + `get_trace_topology` + `get_critical_path` internally and returns a pre-summarized fault object (originating error span, propagation chain, critical-path self-time). See `harness/variants/tool_highlevel.json`. Not registered in `server.go`; the harness implements it as a wrapper so the A/B is a schema experiment, not a Jaeger fork.

**Predicted trajectory effect.** Granular: more calls, lower tokens per call, lower hallucination risk because the model sees raw `status.message`. High-level: fewer calls, higher tokens per call, higher hallucination risk if the summary drops the discriminating field (the thread already saw an analytical-only arm invent `product-service`). Composite arms are not ranked on steps-to-evidence against granular arms — that metric is then measuring where the walk happened, not whether the agent reasoned.

### Pair 2 — Skill wording

Both files match the built-in Skill contract (YAML frontmatter, `allowed-tools`, Procedure/Gotchas) from [`mcptools/README.md`](https://github.com/jaegertracing/jaeger/blob/main/cmd/jaeger/internal/extension/jaegerquery/internal/mcptools/README.md). They can be served via `ai.mcp.skills_dir` under `custom/` without a rebuild.

**Variant A (strict step-by-step):** `harness/variants/skill_stepwise.md` — the `error-root-cause` procedure, made fully prescriptive. Excerpt:

```
1. If you do not yet have a `trace_id`, call `search_traces` with
   `with_errors: true` and take the first matching `trace_id`.
2. Call `get_trace_errors` with that `trace_id`. List every returned span's
   `service`, `span_name`, and `status.message`.
3. Call `get_trace_topology` with the same `trace_id`. Using each span's
   `path` (slash-delimited span IDs from root to self), identify parent-child
   relationships among the error spans.
4. Walk from each error span toward the leaves. The deepest error span with
   no errored children is the candidate root cause.
```

**Variant B (goal-oriented):** `harness/variants/skill_goaloriented.md` — same allowed tools and output contract, no ordered steps. Excerpt:

```
## Goal

Identify the root-cause span — the deepest error span with no errored
children — and report its service, operation, and status message, plus the
parent-child chain that carried the failure to the user. Use whichever of
the allowed tools you need, in whatever order the evidence requires.

Prefer structured tool output over speculation.
```

**Predicted trajectory effect.** Strict: more predictable call sequence, higher call error rate on edge cases (the procedure does not mention `search_traces`, so a run that starts without a `trace_id` has to improvise or fail). Goal-oriented: shorter trajectories on simple faults, higher variance, more cycling (the 47-call `get_services → get_span_names → get_trace_errors` loop in #9135 was an unconstrained arm).

---

## 5. Expected findings

The static MCP surface is already expensive in a way that will dominate naive context-bloat: `tools/list` is ~15 KB, ~64% of it output schemas, and `SpanDetail` is serialized twice ([#9330](https://github.com/jaegertracing/jaeger/issues/9330)). Response payloads ship twice (`structuredContent` + `content[].text`). `get_critical_path` is the largest single response on a ~100-span error trace, which sits awkwardly next to `INSTRUCTIONS.md` telling the agent to prefer "structural overviews before verbose OTLP details." I expect the granular + stepwise arm to win **root-cause accuracy** and **call grounding** on `cartFailure` (the status message is on the span; `get_span_details` / `get_trace_errors` surface it), and to lose **steps-to-evidence** and **raw token count** to the high-level arm. I expect the high-level arm to occasionally name a service that is not in the trace, because the summary is one more place to drop a field. I expect stepwise Skills to produce near-identical call sequences across runs at temperature 0, and goal-oriented Skills to sometimes skip `read_skill` entirely and sometimes cycle.

That split is the decision the default assistant configuration needs. If stepwise + granular is more accurate and only moderately more expensive, `error-root-cause/SKILL.md` should stay procedural and `analyze_trace_fault` should *not* replace `get_span_details` — it can exist as an optional Skill-composed workflow, which is exactly the #8440 boundary (Skills compose reviewed tools; they do not register new behavior). If the high-level tool wins accuracy *and* tokens, the recommendation is the opposite: promote a composite into `registerTools` and keep Skills short. Either result is an upstreamable default; a pooled score that hides the split is not.

---

## 6. Scope and non-goals

**This POC covers:** 1 valid fault scenario (`cartFailure`), 1 documented-broken scenario (`productCatalogFailure`, not scored), 1 LLM (`gemini-3.5-flash`, temperature 0), baseline trajectory capture against the live session-free MCP server, manual metric computation via `score.py`.

**Full mentorship scope:** 5–10 verified trace-solvable scenarios (including ablated twins for abstention, scored as the *gap* in abstention rate, not raw hedge rate); automated scoring in Opik with custom `BaseMetric`s plus `TrajectoryAccuracy`; full 2×2 A/B across both variant pairs; per-fault-class reporting (not one pooled number); upstreamed recommendation for the default tool surface and Skill wording; optional cycle/repetition metric, which the four headline numbers do not catch.

**Not in scope:** building new MCP tools or Skills from scratch (Soumya, #8440); modifying the Jaeger agent / ACP sidecar architecture (Nabil, #7832); treating `MaxSpanDetailsPerRequest` as an experimental factor in v0 (held at the default 20, results reported as conditional on it).
