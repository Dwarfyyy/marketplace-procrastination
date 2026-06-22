import uuid

from sqlalchemy.ext.asyncio import AsyncSession

import crud.product_event as product_event_crud
from schemas.product_event import ProductEventRequest, ProductEventResponse

# Cart unavailable_reason per event type. SKU_BACK_IN_STOCK clears the mark
# instead, and PRICE_CHANGED doesn't affect availability (surfaced via
# cart/validate), so neither appears here.
EVENT_UNAVAILABLE_REASON = {
	"PRODUCT_BLOCKED": "PRODUCT_BLOCKED",
	"PRODUCT_HARD_BLOCKED": "PRODUCT_BLOCKED",
	"PRODUCT_DELETED": "PRODUCT_DELETED",
	"SKU_OUT_OF_STOCK": "OUT_OF_STOCK",
}


async def _resolve_sku_ids(
	db: AsyncSession, request: ProductEventRequest
) -> list[uuid.UUID]:
	# SKU-level events carry the SKU(s) directly; product-level events carry
	# only product_id, so resolve the affected SKUs from the catalog.
	if request.sku_ids:
		return request.sku_ids
	return await product_event_crud.get_product_sku_ids(db, request.payload.product_id)


async def apply_product_event(
	db: AsyncSession, request: ProductEventRequest
) -> ProductEventResponse:
	await product_event_crud.lock_idempotency_key(db, request.idempotency_key)
	existing = await product_event_crud.get_processed_event(db, request.idempotency_key)
	if existing is not None:
		return ProductEventResponse(
			idempotency_key=request.idempotency_key,
			processed=False,
		)

	updated_count = 0
	if request.event_type == "SKU_BACK_IN_STOCK":
		sku_ids = await _resolve_sku_ids(db, request)
		updated_count = await product_event_crud.restore_cart_items(db, sku_ids)
	elif request.event_type in EVENT_UNAVAILABLE_REASON:
		sku_ids = await _resolve_sku_ids(db, request)
		updated_count = await product_event_crud.mark_cart_items_unavailable(
			db, sku_ids, EVENT_UNAVAILABLE_REASON[request.event_type]
		)
	# PRICE_CHANGED: no availability change; recorded for idempotency only.

	product_event_crud.add_processed_event(
		db, request.idempotency_key, request.event_type
	)
	await db.commit()
	return ProductEventResponse(
		idempotency_key=request.idempotency_key,
		processed=True,
		updated_count=updated_count,
	)
