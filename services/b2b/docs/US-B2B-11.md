# US-B2B-11: seller product list

## Implementation

`GET /api/v1/products` now supports two explicit authentication modes. A Bearer
JWT returns the seller-cabinet list, while `X-Service-Key` preserves the existing
B2C public catalog behavior. In seller mode, `seller_id` is always taken from the
validated JWT claim; a query parameter with the same name is accepted but ignored.

The seller list includes soft-deleted products and exposes `deleted`,
`skus_count`, and `total_active_quantity`. It supports exact status filtering and
case-insensitive title search. Responses use the
`{items, total_count, limit, offset}` pagination contract. Soft-deleted products
are included by default and can be excluded with `include_deleted=false`. The
query never includes products owned by another seller.

## Tests

- `test_list_returns_only_own_products`
- `test_idor_query_param_seller_id_ignored`
- `test_deleted_products_visible_with_deleted_flag`
- `test_status_filter_works_correctly`
- `test_search_by_title_case_insensitive`
- `test_pagination_and_include_deleted_filter`

Existing public-catalog tests continue to cover the service-key mode and ensure
that B2C does not receive seller-only inventory fields.

## ADR

The alternatives for SKU aggregates were a grouped SQLAlchemy query, prefetching
all SKU rows and aggregating in Python, and raw SQL. A SQLAlchemy aggregate
subquery joined to products was chosen because it computes count and sum in one
database query without an N+1 problem. Prefetching would transfer unnecessary SKU
rows, while raw SQL would be harder to maintain alongside the existing ORM
queries. The subquery also keeps products without SKU rows in the result with
zero-valued aggregates.
