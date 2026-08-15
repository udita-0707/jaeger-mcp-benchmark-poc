# Results

These files are the four metrics from design-doc.md, computed by `harness/score.py` from a trajectory JSON. Regenerate with:

```bash
python harness/score.py trajectories/cart_failure_baseline.json --save
```

That overwrites `results/baseline_metrics.md`. Placeholder input prints `no data yet` and does not write numbers. Do not hand-edit the table to look finished — the point of the POC is that the numbers come from a real MCP run.
