---
status: broken
fault: productCatalogFailure
evidence_span: oteldemo.ProductCatalogService/GetProduct
---

# Scenario: productCatalogFailure (broken — not a valid benchmark scenario)

This file exists because the issue names `productCatalogFailure` as a seed fault, and because verifying it empirically is the point of the trace-solvable gate. **Do not add this scenario to a scored run.** `status: broken`.

## Fault name

`productCatalogFailure` (OpenTelemetry Demo Astronomy Shop). Intended to fail `GetProduct` for product ID `OLJCESPC7Z`.

## Why it is broken

In current `src/flagd/demo.flagd.json` (verified against [open-telemetry/opentelemetry-demo@main](https://github.com/open-telemetry/opentelemetry-demo/blob/main/src/flagd/demo.flagd.json)), the targeting rule is a no-op:

```json
"productCatalogFailure": {
  "defaultVariant": "off",
  "targeting": {
    "if": [
      { "==": [ { "var": "product_id" }, "OLJCESPC7Z" ] },
      "off",
      "off"
    ]
  },
  "variants": { "off": false, "on": true }
}
```

Both branches of the `if` resolve to `"off"`, which overrides `defaultVariant`. Toggling the flag to `on` in Flagd UI therefore does not fail `GetProduct`. Upstream: [open-telemetry/opentelemetry-demo#3816](https://github.com/open-telemetry/opentelemetry-demo/issues/3816) (fix attempt #3817).

This is the verification step working as designed: a flag the docs advertise as a fault is not trace-solvable in the running demo, because there is no error span to inspect.

## Workaround (required before this can become a valid scenario)

Edit `src/flagd/demo.flagd.json` (or this repo's `flagd/demo.flagd.json`) so the **match** branch is `"on"`:

```json
"if": [
  { "==": [ { "var": "product_id" }, "OLJCESPC7Z" ] },
  "on",
  "off"
]
```

flagd watches the file; no restart. Then `GetProduct(OLJCESPC7Z)` hits `checkProductFailure` in `src/product-catalog/main.go`, which sets span status `Error` with message `Error: Product Catalog Fail Feature Flag Enabled` and attribute `demo.product.id=OLJCESPC7Z`.

Until that patch (or #3817) is in the demo you are running, `fixture.otlp.json` will not contain the evidence span and any trajectory against this scenario is invalid.

## How to trigger (after the workaround)

1. Apply the targeting fix above.
2. Set `productCatalogFailure` to `on` if you are not relying on targeting alone.
3. Request product `OLJCESPC7Z` (shop frontend product page, or checkout that includes that SKU).

```bash
curl -sS "http://localhost:8080/api/products/OLJCESPC7Z" || true
```

## Expected user-visible symptom (once un-broken)

The product page / GetProduct for National Park Foundation pin (`OLJCESPC7Z`) returns an internal error. Other product IDs succeed. Recommendation's `get_product_list` does not error; the failure is on `GetProduct` only.

## Trace signature (once un-broken)

| Field | Value |
|---|---|
| Service | `product-catalog` |
| Operation | `oteldemo.ProductCatalogService/GetProduct` |
| Status code | `Error` |
| Status message | `Error: Product Catalog Fail Feature Flag Enabled` |
| Attribute | `demo.product.id=OLJCESPC7Z` |
| Span event | `Error: Product Catalog Fail Feature Flag Enabled` |

## Why it *would* be trace-solvable

The status message names the feature-flag failure on the span; `demo.product.id` identifies the SKU; parent-child from frontend/checkout `GetProduct` client spans into `product-catalog` is the chain. No logs required. Evidence marker would be `oteldemo.ProductCatalogService/GetProduct`, not `product-catalog`.

## Ground truth answer (do not score until un-broken)

`product-catalog` / `oteldemo.ProductCatalogService/GetProduct` for `OLJCESPC7Z` is in `Error` status with message `Error: Product Catalog Fail Feature Flag Enabled`.

## Disqualification check

Once the targeting fix is applied, no log correlation is needed. **Until then, the scenario is disqualified because there is no error span** — not because it needs logs.
