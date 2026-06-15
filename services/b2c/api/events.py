from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from exceptions.order import OrderNotDeliverableError, OrderNotFoundError
from schemas.order import OrderDeliveredEventRequest, OrderResponse
from schemas.product_event import ProductEventRequest, ProductEventResponse
from services import order_service, product_event_service

router = APIRouter(prefix="/events", tags=["Product Events"])


@router.post("/product", response_model=ProductEventResponse)
async def receive_product_event(
	request: ProductEventRequest,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> ProductEventResponse:
	return await product_event_service.apply_product_event(db, request)


@router.post("/order-delivered", response_model=OrderResponse)
async def receive_order_delivered_event(
	request: OrderDeliveredEventRequest,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> OrderResponse:
	try:
		return await order_service.deliver_order(db, request.order_id)
	except OrderNotFoundError as err:
		raise HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": "Order not found"},
		) from err
	except OrderNotDeliverableError as err:
		raise HTTPException(
			status_code=409,
			detail={
				"code": "DELIVER_NOT_ALLOWED",
				"message": "Can't deliver a cancelled order",
			},
		) from err
