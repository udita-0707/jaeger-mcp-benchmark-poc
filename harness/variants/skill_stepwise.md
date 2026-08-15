---
name: error-root-cause-stepwise
description: >-
  Walk a failed trace to the first originating error span. Use when a trace
  has errors and the user asks why it failed or which service is the root cause.
license: Apache-2.0
metadata:
  author: jaeger-mcp-benchmark-poc
  version: "1.0"
  variant: stepwise
allowed-tools: get_trace_errors get_trace_topology get_span_details search_traces
---

# Error Root Cause Analysis (step-by-step)

## When this applies

A trace contains one or more error spans and the user wants the originating
failure, not the symptoms.

## Procedure

1. If you do not yet have a `trace_id`, call `search_traces` with
   `with_errors: true` and take the first matching `trace_id`.
2. Call `get_trace_errors` with that `trace_id`. List every returned span's
   `service`, `span_name`, and `status.message`.
3. Call `get_trace_topology` with the same `trace_id`. Using each span's
   `path` (slash-delimited span IDs from root to self), identify parent-child
   relationships among the error spans.
4. Walk from each error span toward the leaves. The deepest error span with
   no errored children is the candidate root cause. Do not stop at a parent
   timeout — inspect its children even if they lack error status.
5. Call `get_span_details` with the candidate span's `span_id` (the last
   segment of `path`). Read `status.message`, attributes, and events.
6. Report only what those tool responses contain: root-cause span (service,
   operation, error message), the propagation chain as topology paths, and
   a recommendation. Do not name a mechanism that does not appear on a span.

## Gotchas

- Timeouts at a parent may mask the real cause in a child that was cancelled.
- Multiple independent root causes can exist in a single trace.
- `get_trace_errors` may truncate; compare `total_error_count` to the length
  of `spans` before treating the list as complete.
