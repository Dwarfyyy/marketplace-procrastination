# US-B2B-10: fulfill on delivery

## Implementation

Added service-to-service endpoint `POST /api/v1/inventory/fulfill`, protected by the B2C
`X-Service-Key`. The request contains an `order_id` UUID and a non-empty list of
`{sku_id, quantity}` items. Duplicate SKU entries are aggregated before any
inventory checks.

Fulfill locks all affected SKU rows in stable UUID order and atomically decreases
only `reserved_quantity`. `active_quantity` remains unchanged. If a SKU does not
exist or has insufficient reserved quantity, no item is changed. All 4xx responses
use the flat `{code, message}` contract.

## Idempotency

Successful operations are stored in `catalog.fulfilled_orders`, keyed by
`order_id`. The stored normalized request and inventory snapshot allow identical
retries to return the original `{order_id, status, processed_at}` response with
`200` without another deduction. Reusing an order ID with a
different payload returns `409 INVENTORY_CONFLICT`. A transaction-scoped advisory
lock serializes concurrent requests for the same order before SKU rows are read.

## Tests

- `test_fulfill_decreases_reserved_quantity`
- `test_active_quantity_unchanged`
- `test_idempotent_fulfill_no_double_deduction`
- `test_missing_service_key_returns_401`
- atomic rollback on insufficient reserved quantity
- changed-payload idempotency conflict
- flat validation-error response

## ADR

The alternatives were a dedicated `fulfilled_orders` table, a
`last_fulfilled_order` field on every SKU, and inference from current reserved
quantity. The dedicated table was chosen because it prevents double deduction
across multi-SKU orders and stores a stable response for retries. A per-SKU field
cannot represent multiple concurrent orders cleanly, while quantity inference
cannot distinguish a retry from a new fulfillment. The table and advisory lock add
some implementation complexity but provide explicit, transaction-safe semantics.
