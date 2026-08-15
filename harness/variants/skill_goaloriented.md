---
name: error-root-cause-goaloriented
description: >-
  Identify the originating error span of a failed trace. Use when a request
  failed and the user wants to know where and why.
license: Apache-2.0
metadata:
  author: jaeger-mcp-benchmark-poc
  version: "1.0"
  variant: goaloriented
allowed-tools: get_trace_errors get_trace_topology get_span_details search_traces
---

# Error Root Cause Analysis (goal-oriented)

## When this applies

A request failed. The user wants the originating failure, not cascading
symptoms.

## Goal

Identify the root-cause span — the deepest error span with no errored
children — and report its service, operation, and status message, plus the
parent-child chain that carried the failure to the user. Use whichever of
the allowed tools you need, in whatever order the evidence requires.

Prefer structured tool output over speculation. If a field you would like
to name (a mechanism, a config flag, a host metric) is not present on a
span, say so and name the missing evidence class instead of guessing.

## Output

- Root-cause span: service, operation, error message
- Propagation chain
- Recommendation, grounded in the spans you inspected

## Gotchas

- Parent timeouts can hide the child that actually failed.
- `get_trace_errors` may truncate; `total_error_count` vs. returned `spans`
  is the truncation signal.
- Service names alone are not a root cause.
- Feature-flag client spans (`ResolveBoolean` / `ResolveFloat`) can be Error
  and are not the user-visible fault. Filter `search_traces` by the reported
  operation's `span_name`.
- Once `status.message` names the failure, stop calling tools and answer.
