#!/usr/bin/env python3
"""Score a trajectory JSON against the four metrics in design-doc.md.

Reads trajectories written by run_eval.py. Placeholder files exit cleanly.

Usage:
  python harness/score.py trajectories/cart_failure_baseline.json
  python harness/score.py trajectories/cart_failure_baseline.json --save
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_VALID_TOOLS = [
    "get_services",
    "get_span_names",
    "search_traces",
    "get_span_details",
    "get_trace_errors",
    "get_trace_topology",
    "get_critical_path",
    "get_service_dependencies",
    "read_skill",
    "analyze_trace_fault",  # harness-side high-level variant, not in server.go
]

DEFAULT_EVIDENCE = {
    "cart_failure": "oteldemo.CartService/EmptyCart",
    "product_catalog_failure": "oteldemo.ProductCatalogService/GetProduct",
}

DEFAULT_ACCEPTABLE = {
    "cart_failure": [
        "can't access cart storage",
        "oteldemo.CartService/EmptyCart",
        "emptycart",
        "cart storage",
    ],
    "product_catalog_failure": [
        "product catalog fail feature flag enabled",
        "oteldemo.ProductCatalogService/GetProduct",
        "oljcespc7z",
    ],
}

# Estimated tokens of the evidence span (status + name + path) — not the full trace.
DEFAULT_MIN_TOKENS = {
    "cart_failure": 80,
    "product_catalog_failure": 80,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trajectory", type=Path)
    parser.add_argument(
        "--valid-tools",
        default=",".join(DEFAULT_VALID_TOOLS),
        help="Comma-separated list of registered tool names",
    )
    parser.add_argument(
        "--evidence-span",
        default="",
        help="Ground-truth span/operation name. Default: from scenario field.",
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=0,
        help="Minimum tokens theoretically needed to answer. Default: per-scenario estimate.",
    )
    parser.add_argument(
        "--acceptable",
        default="",
        help="Comma-separated acceptable answer substrings (case-insensitive).",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Write the markdown table to results/baseline_metrics.md",
    )
    return parser.parse_args(argv)


def haystack(step: dict) -> str:
    return " ".join(
        str(step.get(k) or "")
        for k in ("response_excerpt", "response_summary", "tool_name")
    )


def compute(data: dict, args: argparse.Namespace) -> dict:
    scenario = data.get("scenario") or "cart_failure"
    steps = data.get("trajectory") or []
    valid = {n.strip() for n in args.valid_tools.split(",") if n.strip()}
    evidence = args.evidence_span or DEFAULT_EVIDENCE.get(scenario, "")
    min_tokens = args.min_tokens or DEFAULT_MIN_TOKENS.get(scenario, 80)
    if args.acceptable:
        acceptable = [s.strip().lower() for s in args.acceptable.split(",") if s.strip()]
    else:
        acceptable = list(DEFAULT_ACCEPTABLE.get(scenario, []))

    total = len(steps)
    invalid = 0
    for step in steps:
        name = step.get("tool_name") or ""
        if name not in valid or step.get("is_error"):
            invalid += 1
    call_error_rate = (invalid / total) if total else 0.0

    steps_to_evidence: int | None = None
    if evidence:
        for step in steps:
            if evidence in haystack(step):
                steps_to_evidence = step.get("step")
                break

    total_tokens = sum(int(step.get("response_length_tokens") or 0) for step in steps)
    bloat = (total_tokens / min_tokens) if min_tokens else None

    final = (data.get("final_answer") or "").lower()
    accuracy = 0
    if final and acceptable:
        accuracy = int(any(s in final for s in acceptable))

    return {
        "scenario": scenario,
        "n_calls": total,
        "call_error_rate": call_error_rate,
        "invalid_calls": invalid,
        "steps_to_evidence": steps_to_evidence,
        "evidence_span": evidence,
        "context_bloat_ratio": bloat,
        "total_response_tokens": total_tokens,
        "min_tokens": min_tokens,
        "root_cause_accuracy": accuracy,
        "final_answer": data.get("final_answer") or "",
    }


def render(metrics: dict) -> str:
    ste = metrics["steps_to_evidence"]
    ste_s = str(ste) if ste is not None else "n/a (evidence span never appeared)"
    bloat = metrics["context_bloat_ratio"]
    bloat_s = f"{bloat:.2f}" if bloat is not None else "n/a"
    acc = "1 (match)" if metrics["root_cause_accuracy"] else "0 (no match)"
    lines = [
        f"# Baseline metrics (`{metrics['scenario']}`)",
        "",
        "| Metric | Value | Notes |",
        "|--------|-------|-------|",
        f"| Call error rate | {metrics['call_error_rate']:.2f} ({metrics['invalid_calls']}/{metrics['n_calls']}) | invalid = unknown name or MCP isError |",
        f"| Steps to evidence | {ste_s} | marker `{metrics['evidence_span']}` |",
        f"| Context bloat ratio | {bloat_s} | {metrics['total_response_tokens']} response tokens / {metrics['min_tokens']} min |",
        f"| Root-cause accuracy | {acc} | substring match against ground_truth.md variants |",
        "",
        "Call error rate is invalid tool calls over total calls; 0.00 is expected on this schema, "
        "and a 0.00 that coincides with a long cycle is a different failure (repetition), not a win. "
        "Steps to evidence is the 1-based index of the first tool response that contains the "
        "span-level marker — service names do not count. Context bloat is delivered response "
        "tokens over the estimated tokens of the evidence span alone; closer to 1 is better, "
        "and silent truncation is not scored as efficiency. Root-cause accuracy is binary: "
        "the final answer must name the seeded locus (operation + status message), not a "
        "plausible-sounding mechanism that is not on the span.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = args.trajectory
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if data.get("_placeholder") is True:
        print("no data yet")
        return 0

    if not data.get("trajectory"):
        print("no data yet")
        return 0

    metrics = compute(data, args)
    table = render(metrics)
    print(table, end="")
    if args.save:
        out = REPO_ROOT / "results" / "baseline_metrics.md"
        out.write_text(table, encoding="utf-8")
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
