from sqlalchemy.ext.asyncio import AsyncSession

import crud.product_event as product_event_crud
from schemas.product_event import ProductEventRequest, ProductEventResponse

EVENT_UNAVAILABLE_REASON = {
	"PRODUCT_BLOCKED": "PRODUCT_BLOCKED",
	"PRODUCT_DELETED": "PRODUCT_DELETED",
	"SKU_OUT_OF_STOCK": "OUT_OF_STOCK",
}


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

	reason = EVENT_UNAVAILABLE_REASON[request.event_type]
	updated_count = await product_event_crud.mark_cart_items_unavailable(
		db, request.sku_ids, reason
	)
	product_event_crud.add_processed_event(
		db, request.idempotency_key, request.event_type
	)
	await db.commit()
	return ProductEventResponse(
		idempotency_key=request.idempotency_key,
		processed=True,
		updated_count=updated_count,
	)
