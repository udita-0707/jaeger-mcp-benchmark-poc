# Baseline metrics (`cart_failure`)

2×2 complete. Model `gemini-3.7-flash`, temperature 0. See `results/ab_cart_failure.md`.

| Arm | Calls | Steps to evidence | Bloat | Accuracy |
|---|---|---|---|---|
| highlevel × stepwise | 4 | 4 | 14.39 | 1 |
| granular × goaloriented | 4 | 4 | 18.64 | 1 |
| highlevel × goaloriented | 8 | 8 | 118.09 | 1 |
| granular × stepwise | 12 | 12 | 123.67 | 1 |

All four named `Can't access cart storage` on `POST /oteldemo.CartService/EmptyCart`. The high-level tool wins **tokens and steps** on this fault; it does not win accuracy (already 1 everywhere). Goal-oriented high-level still wasted searches until it called `analyze_trace_fault`.
