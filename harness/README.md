# Harness

Python evaluation loop for [jaegertracing/jaeger#9135](https://github.com/jaegertracing/jaeger/issues/9135).

- `run_eval.py` — drives `gemini-3.5-flash` (temperature 0) against the **session-free** Jaeger MCP endpoint `http://localhost:16686/api/ai/mcp/`. All model calls go through `llm.call_llm(prompt, tools)`. `gemini-1.5-flash` and `gemini-2.5-flash` 404 for new AI Studio keys; override with `LLM_MODEL`.
- `score.py` — reads a trajectory JSON and prints the four metrics in design-doc.md. Placeholder files print `no data yet` and exit 0.
- `variants/` — A/B files. `tool_granular.json` is the live `get_span_details` schema; `tool_highlevel.json` is a proposed `analyze_trace_fault` composite the harness implements client-side. The two Skill files match the built-in Skill contract in `mcptools/skills/`.

```bash
pip install -r harness/requirements.txt
export GEMINI_API_KEY=...
export JAEGER_ENDPOINT=http://localhost:16686
python harness/run_eval.py --scenario cart_failure --variant granular --skill stepwise
python harness/score.py trajectories/cart_failure_baseline.json --save
```

`--variant highlevel` hides `get_span_details` / `get_trace_errors` / `get_trace_topology` / `get_critical_path` and exposes `analyze_trace_fault`, which composes those four on the real server so the A/B does not require a Jaeger fork.
