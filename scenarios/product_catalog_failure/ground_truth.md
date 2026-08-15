# Ground truth: productCatalogFailure

**Not scored.** `status: broken` — see `scenario.md` and [opentelemetry-demo#3816](https://github.com/open-telemetry/opentelemetry-demo/issues/3816). Values below are what a valid run *would* require after the flagd targeting workaround.

- **Root cause:** `product-catalog` failed `GetProduct` for SKU `OLJCESPC7Z` with status message `Error: Product Catalog Fail Feature Flag Enabled`.
- **Key evidence span:** `product-catalog` / `oteldemo.ProductCatalogService/GetProduct` / `status.message` + attribute `demo.product.id`
- **Causal chain:** frontend or checkout GetProduct client span → `product-catalog` `oteldemo.ProductCatalogService/GetProduct` (Error) → user-visible product-page / checkout failure for that SKU
- **Acceptable answer variants:**
  - `product-catalog` / `oteldemo.ProductCatalogService/GetProduct` failed for `OLJCESPC7Z` (`Error: Product Catalog Fail Feature Flag Enabled`)
  - GetProduct on the product-catalog service returns Internal for that product ID
  - The originating error is the product-catalog GetProduct span (feature-flag failure named on the span)
- **Incorrect answer examples:**
  - "Recommendation service is failing" (list-products of that SKU does not error)
  - "Product not found" (`NotFound` is a different branch in `GetProduct`; the flag path is `Internal`)
  - Naming `product-catalog` without `GetProduct` / `OLJCESPC7Z`
