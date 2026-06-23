from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from schemas.product_event import ProductEventRequest, ProductEventResponse
from services.product_events import apply_product_event

router = APIRouter(prefix="/b2b/events", tags=["Product Events"])


@router.post("", response_model=ProductEventResponse, status_code=202)
async def receive_product_event(
	request: ProductEventRequest,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> ProductEventResponse:
	event = {
		"event_type": request.event_type,
		"payload": {
			"product_id": str(request.payload.product_id),
			"seller_id": str(request.payload.seller_id),
			"json_after": dict(request.payload.json_after),
		},
	}
	await apply_product_event(db, event)
	return ProductEventResponse(
		idempotency_key=request.idempotency_key,
		processed=True,
	)
