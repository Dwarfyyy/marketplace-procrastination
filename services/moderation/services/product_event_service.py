from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import crud.product_event as product_event_crud
from database.models import ModerationStatus, ProductModeration
from schemas.product_event import ProductEventRequest, ProductEventResponse
from services.product_events import apply_product_event


async def apply_product_event_with_idempotency(
	db: AsyncSession, request: ProductEventRequest
) -> ProductEventResponse:
	"""Apply product event with idempotency check."""
	await product_event_crud.lock_idempotency_key(db, request.idempotency_key)

	existing = await product_event_crud.get_processed_event(db, request.idempotency_key)
	if existing is not None:
		# Event already processed; return 409 via exception raised in API
		from fastapi import HTTPException
		raise HTTPException(
			status_code=409,
			detail={
				"code": "DUPLICATE_EVENT",
				"message": "Event with this idempotency_key has already been processed",
			},
		)

	# Build event dict for product_events function
	event = {
		"event_type": request.event_type,
		"payload": {
			"product_id": str(request.payload.product_id),
			"seller_id": str(request.payload.seller_id),
			"json_after": dict(request.payload.json_after),
		},
	}

	# Apply the event
	await apply_product_event(db, event)

	# Record processed event for idempotency
	product_event_crud.add_processed_event(
		db, request.idempotency_key, request.payload.product_id, request.event_type
	)
	await db.commit()

	# Fetch card to get final status
	result = await db.execute(
		select(ProductModeration).where(
			ProductModeration.product_id == request.payload.product_id
		)
	)
	card = result.scalar_one_or_none()

	return ProductEventResponse(
		idempotency_key=request.idempotency_key,
		processed=True,
		card_id=card.id if card else None,
		status=card.status.value if card else None,
	)
