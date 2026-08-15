# Baseline metrics (`cart_failure`)

| Metric | Value | Notes |
|--------|-------|-------|
| Call error rate | 0.00 (0/4) | invalid = unknown name or MCP isError |
| Steps to evidence | 4 | marker `oteldemo.CartService/EmptyCart` + `can't access cart storage` |
| Context bloat ratio | 14.39 | 1151 response tokens / 80 min |
| Root-cause accuracy | 1 (match) | substring match against ground_truth.md variants |

Call error rate is invalid tool calls over total calls; 0.00 is expected on this schema, and a 0.00 that coincides with a long cycle is a different failure (repetition), not a win. Steps to evidence is the 1-based index of the first tool response that contains the span-level marker **and** the discriminating status message — a catalog listing of the operation name does not count. Context bloat is delivered response tokens over the estimated tokens of the evidence span alone; closer to 1 is better, and silent truncation is not scored as efficiency. Root-cause accuracy is binary: the final answer must name the seeded locus (operation + status message), not a plausible-sounding mechanism that is not on the span.
