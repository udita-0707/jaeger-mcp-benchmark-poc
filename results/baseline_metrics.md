| Metric | Value | Notes |
|--------|-------|-------|
| Call error rate | [run harness] | |
| Steps to evidence | [run harness] | |
| Context bloat ratio | [run harness] | |
| Root-cause accuracy | [run harness] | |

Call error rate is invalid tool calls (unknown name or MCP `isError`) over total calls — 0.00 is expected on this schema; a 0.00 that coincides with a long cycle is repetition, not a win. Steps to evidence is the 1-based index of the first tool response that contains the span-level marker (`oteldemo.CartService/EmptyCart`); service names do not count. Context bloat is delivered response tokens over the estimated tokens of the evidence span alone; closer to 1 is better, and silent truncation is not “efficient.” Root-cause accuracy is binary: the final answer must name the seeded locus (operation + status message), not a plausible mechanism that is not on the span.
