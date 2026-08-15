# Scenarios

A scenario is **trace-solvable** when a specific span has a non-OK status, that span's error message or attributes name the root cause, and the causal chain from that span to the user-visible failure is reconstructible from parent-child relationships without application logs. Evidence markers are span/operation names (e.g. `oteldemo.CartService/EmptyCart`), never service names — `get_services` would otherwise make steps-to-evidence trivially 1. See design-doc.md section 2 for the full criterion and the five-point verification checklist.

## Adding a scenario

1. **Trigger the fault** in a running OpenTelemetry Demo (feature flag via Flagd UI at `http://localhost:4000`, or the HTTP note in that scenario's `scenario.md`).
2. **Capture a trace** that contains the failing span. Save it as `fixture.otlp.json` (`CAPTURE_FIXTURE=true python harness/run_eval.py --scenario <name>`).
3. **Fill `scenario.md` and `ground_truth.md`** from the template. Run the verification checklist in design-doc.md section 2. If any check fails, do not mark the scenario valid — document why (`status: broken` in the frontmatter), the way `product_catalog_failure` documents the flagd targeting no-op.

## Current scenarios

| Directory | Fault | Status |
|---|---|---|
| `cart_failure/` | OTel Demo `cartFailure` @ 100% | **documented, valid** — first benchmark scenario |
| `product_catalog_failure/` | OTel Demo `productCatalogFailure` | **documented, broken** — flagd targeting is a no-op ([opentelemetry-demo#3816](https://github.com/open-telemetry/opentelemetry-demo/issues/3816)); not scored |
