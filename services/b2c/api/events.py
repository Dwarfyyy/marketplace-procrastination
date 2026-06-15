from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from schemas.product_event import ProductEventRequest, ProductEventResponse
from services import product_event_service

router = APIRouter(prefix="/events", tags=["Product Events"])


@router.post("/product", response_model=ProductEventResponse)
async def receive_product_event(
	request: ProductEventRequest,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> ProductEventResponse:
	return await product_event_service.apply_product_event(db, request)
