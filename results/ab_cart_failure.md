# cart_failure 2×2 (`gemini-3.7-flash`, temperature 0)

All four arms named `cart` / `POST /oteldemo.CartService/EmptyCart` with `Can't access cart storage`. Accuracy is not the discriminator on this fault; **cost** is.

| Arm | Calls | Steps to evidence | Bloat | Accuracy | Notes |
|---|---|---|---|---|---|
| **highlevel × stepwise** | **4** | **4** | **14.39** | 1 | Called `analyze_trace_fault` once. Cheapest complete solve. |
| granular × goaloriented | 4 | 4 | 18.64 | 1 | `get_trace_errors` on EmptyCart; stopped. |
| highlevel × goaloriented | 8 | 8 | 118.09 | 1 | Several `search_traces` before `analyze_trace_fault`. Composite only helps when invoked early. |
| granular × stepwise | 12 | 12 | 123.67 | 1 | Found evidence at 12; valid but slow. Earlier run without stop rule was 15 calls / accuracy 0. |

Trajectories: `trajectories/cart_failure_{granular,highlevel}_{stepwise,goaloriented}.json`.

## What this suggests for #9135

On a trace-solvable fault whose status message is on the originating span:

1. **A composite `analyze_trace_fault` is worth exposing** if Skills tell the agent to call it after `search_traces` — highlevel × stepwise is ~8× fewer response tokens than granular × stepwise.
2. **Hiding the granular tools is not enough.** Highlevel × goaloriented still burned 7 search calls before the composite (bloat 118). The Skill must name the tool.
3. **Stop-on-evidence is load-bearing.** Granular × stepwise without it hit `MAX_STEPS` and scored 0 even after seeing the storage error.
4. **Flagd `ResolveBoolean` error traces** dominate `search_traces(service=cart, with_errors=true)`. Filtering by `span_name` (or skipping flag-evaluation roots) is part of a correct `error-root-cause` Skill, not a Jaeger storage bug.

This is one scenario × one model. Mentorship work is repeating the grid on 5–10 verified faults, including abstention twins, before changing `registerTools`.
