---
status: valid
fault: cartFailure
evidence_span: oteldemo.CartService/EmptyCart
---

# Scenario: cartFailure

## Fault name

`cartFailure` (OpenTelemetry Demo Astronomy Shop). Percentage flag; this scenario uses the `100%` variant.

## How to trigger

1. Start the stack (`docker compose up -d` from the repo root). Flagd UI is `http://localhost:4000`.
2. Set `cartFailure` to **`100%`** (not `on` — the flag is a double, variants are `10%` / `25%` / `50%` / `75%` / `90%` / `100%` / `off`). Default is `off`.
3. Generate an `EmptyCart` RPC. With the load generator running against the shop at `http://localhost:8080`, a checkout that reaches "empty cart" is enough. Against the cart service directly:

```bash
# Flagd OFREP is evaluation-only; changing the flag is done in Flagd UI
# (http://localhost:4000) or by editing flagd/demo.flagd.json (flagd watches the file).
#
# Then produce an EmptyCart. If the full demo frontend-proxy is up:
curl -sS -X POST http://localhost:8080/api/cart/empty \
  -H 'Content-Type: application/json' \
  -d '{"userId":"benchmark-user"}' || true
```

The cart implementation (`src/cart/src/services/CartService.cs`) reads `GetDoubleValueAsync("cartFailure", 0)` inside `EmptyCart`. When the roll hits, it calls a second `ValkeyCartStore` constructed with host `badhost:1234` (`src/cart/src/Program.cs`).

## Expected user-visible symptom

Emptying the cart fails (checkout cannot clear the cart after placing an order; the shop UI / API returns an error on EmptyCart). Add-item and GetCart are not on this flag.

## Trace signature

| Field | Value |
|---|---|
| Service | `cart` (`OTEL_SERVICE_NAME=cart`) |
| Operation | `oteldemo.CartService/EmptyCart` |
| Status code | `Error` |
| Status message | `Can't access cart storage. …` (RpcException, `FailedPrecondition`, from the Valkey client failing to reach `badhost:1234`) |
| Span event | exception recorded on the span (`Activity.Current?.AddException`) |

## Why trace-solvable

The discriminating signal is on the span: `status.code = Error` and `status.message` names cart-storage access as the failure. The causal chain is the gRPC parent-child path from checkout/frontend's EmptyCart client span into `cart`'s server span. No application log is required to name the locus. Evidence marker is the **operation name** `oteldemo.CartService/EmptyCart`, which does not appear in `get_services`.

## Ground truth answer

The `cart` service's `oteldemo.CartService/EmptyCart` span is in `Error` status because cart storage is unreachable (`Can't access cart storage`), which is the seeded `cartFailure` fault.

## Disqualification check

No log correlation is needed. The status message is copied onto the span by the `.NET` instrumentation in `EmptyCart`'s `catch (RpcException)`. Config inspection is not required to *locate* the fault; knowing that a feature flag caused it is mechanism, not locus — the scored answer is the span locus plus the storage-access error, not the string `cartFailure`.
