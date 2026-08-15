# Jaeger MCP Tools + Skills benchmark POC

Private pre-application POC for LFX Mentorship Term 3: [Benchmarking the AI Assistant's MCP Tools and Skills](https://github.com/jaegertracing/jaeger/issues/9135).

## What this demonstrates

- The **trace-solvable** fault scenario design (`cartFailure` is valid; `productCatalogFailure` is documented as broken after empirical verification).
- The **evaluation harness** architecture: session-free `/api/ai/mcp/`, trajectory capture, four Cloud-OpsBench-style metrics.
- The **A/B variant** approach for tool schema (`get_span_details` vs. `analyze_trace_fault`) and Skill wording (stepwise vs. goal-oriented).

## How to run

```bash
docker compose up -d
# Trigger cartFailure: open http://localhost:4000 and set cartFailure to 100%, then hit EmptyCart on the cart service (localhost:7070) or the shop at http://localhost:8080 if you started the full demo.
export GEMINI_API_KEY=... JAEGER_ENDPOINT=http://localhost:16686
python harness/run_eval.py --scenario cart_failure --variant granular --skill stepwise
python harness/score.py trajectories/cart_failure_baseline.json --save
```

`CAPTURE_FIXTURE=true` on the eval command also writes `scenarios/cart_failure/fixture.otlp.json`. MCP is `http://localhost:16686/api/ai/mcp/` — not the ACP sidecar.

## What to read first

- [`design-doc.md`](design-doc.md) — methodology (isolation criterion, metrics, A/B, scope).
- [`scenarios/cart_failure/scenario.md`](scenarios/cart_failure/scenario.md) — first fault scenario.
- [`trajectories/cart_failure_baseline.json`](trajectories/cart_failure_baseline.json) — sample output (**populated after a local run**).
- [`results/baseline_metrics.md`](results/baseline_metrics.md) — computed metrics (**populated after** `score.py --save`).

This is a pre-application POC demonstrating the approach I would take during the mentorship. The harness is intentionally minimal — the full implementation would extend this with N scenarios, automated scoring, and the full A/B comparison pipeline described in design-doc.md.
