from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from schemas.product_event import ProductEventRequest, ProductEventResponse
from services import product_event_service

router = APIRouter(prefix="/b2b/events", tags=["Product Events"])


@router.post("", response_model=ProductEventResponse, status_code=202)
async def receive_product_event(
	request: ProductEventRequest,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> ProductEventResponse:
	return await product_event_service.apply_product_event(db, request)
