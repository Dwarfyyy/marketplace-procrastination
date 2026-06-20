from typing import Annotated
import uuid

import fastapi

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPBearer
from core import db
from database.models.orders.order import OrderStatusEnum
from exceptions.order import (
	AddressNotFoundError,
	B2BUnavailableError,
	EmptyCartError,
	IdempotencyConflictError,
	InvalidIdempotencyKeyError,
	OrderNotCancelableError,
	OrderNotFoundError,
	PaymentMethodNotFoundError,
	ReserveFailedError,
)
from schemas.cart import CartValidationResponse
from schemas.order import (
	OrderCancelRequest,
	OrderCreateRequest,
	OrderResponse,
	PaginatedOrders,
)
from services import order_service


security = HTTPBearer()
router = fastapi.APIRouter(
	prefix="/api/v1/orders", tags=["Orders"], dependencies=[fastapi.Depends(security)]
)


@router.post(
	"",
	status_code=201,
	response_model=OrderResponse,
)
async def create_order(
	request: fastapi.Request,
	body: OrderCreateRequest,
	idempotency_key: Annotated[str, fastapi.Header(alias="Idempotency-Key")],
	db_session: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
) -> OrderResponse:
	try:
		key_uuid = order_service.parse_idempotency_key(idempotency_key)
	except InvalidIdempotencyKeyError as err:
		raise fastapi.HTTPException(
			status_code=400,
			detail={
				"code": "BAD_REQUEST",
				"message": "Idempotency-Key must be a valid UUID",
			},
		) from err

	buyer_id_raw = getattr(request.state, "user_id", None)
	if not buyer_id_raw:
		raise fastapi.HTTPException(
			status_code=401,
			detail={
				"code": "UNAUTHORIZED",
				"message": "Missing or invalid Authorization header",
			},
		)
	buyer_id = order_service.parse_idempotency_key(str(buyer_id_raw))
	body_dump = body.model_dump(mode="json")

	try:
		result = await order_service.checkout(
			db_session,
			buyer_id=buyer_id,
			idempotency_key=key_uuid,
			body_raw=body_dump,
			address_id=body.address_id,
			payment_method_id=body.payment_method_id,
			comment=body.comment,
			items_snapshot=[
				item.model_dump(mode="json") for item in body.items_snapshot
			]
			if body.items_snapshot is not None
			else None,
		)
	except EmptyCartError as err:
		raise fastapi.HTTPException(
			status_code=400,
			detail={"code": "BAD_REQUEST", "message": "Cart is empty"},
		) from err
	except AddressNotFoundError as err:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": "Address not found"},
		) from err
	except PaymentMethodNotFoundError as err:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": "Payment method not found"},
		) from err
	except IdempotencyConflictError as err:
		raise fastapi.HTTPException(
			status_code=409,
			detail={
				"code": "IDEMPOTENCY_CONFLICT",
				"message": "Idempotency key already used with different request body",
			},
		) from err
	except ReserveFailedError as err:
		details = err.args[0] if err.args else []
		raise fastapi.HTTPException(
			status_code=409,
			detail={
				"code": "RESERVE_FAILED",
				"message": "Partial reserve failed",
				"details": details,
			},
		) from err
	except B2BUnavailableError as err:
		raise fastapi.HTTPException(
			status_code=503,
			detail={"code": "B2B_UNAVAILABLE", "message": "Catalog service is unavailable"},
		) from err

	if isinstance(result, CartValidationResponse):
		raise fastapi.HTTPException(
			status_code=422,
			detail={
				"code": "VALIDATION_ERROR",
				"message": "Cart validation failed",
				"details": result.model_dump(mode="json"),
			},
		)

	return result


@router.post(
	"/{order_id}/cancel",
	status_code=200,
	response_model=OrderResponse,
)
async def cancel_order(
	order_id: uuid.UUID,
	http_request: fastapi.Request,
	db_session: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
	body: OrderCancelRequest | None = None,
) -> OrderResponse:
	user_id = uuid.UUID(str(getattr(http_request.state, "user_id", None)))
	try:
		return await order_service.cancel_order(
			db_session, order_id, user_id, reason=body.reason if body else None
		)
	except OrderNotFoundError as err:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": "Order not found"},
		) from err
	except OrderNotCancelableError as err:
		raise fastapi.HTTPException(
			status_code=409,
			detail={
				"code": "CANCEL_NOT_ALLOWED",
				"message": "Can't cancel order in this state",
			},
		) from err


@router.get(
	"/{order_id}",
	status_code=200,
	response_model=OrderResponse,
)
async def get_order_by_id_for_buyer(
	order_id: uuid.UUID,
	http_request: fastapi.Request,
	db_session: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
) -> OrderResponse:
	"""Get order by id for buyer. Throws 404 OrderNotFoundError if order not found.

	Args:
		order_id (uuid.UUID): Order ID
		http_request (fastapi.Request): HTTP request
		db_session (Annotated[AsyncSession, fastapi.Depends]): Database session

	Returns:
		OrderResponse: Order response
	"""
	user_id = uuid.UUID(str(getattr(http_request.state, "user_id", None)))
	try:
		return await order_service.get_order_by_id_for_buyer(
			db_session, order_id, user_id
		)
	except OrderNotFoundError as err:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": "Order not found"},
		) from err


@router.get(
	"",
	status_code=200,
	response_model=PaginatedOrders,
)
async def get_buyer_orders(
	db_session: Annotated[AsyncSession, fastapi.Depends(db.get_db)],
	request: fastapi.Request,
	limit: Annotated[int, fastapi.Query(ge=1, le=100)] = 20,
	offset: Annotated[int, fastapi.Query(ge=0)] = 0,
	status: Annotated[OrderStatusEnum | None, fastapi.Query()] = None,
) -> PaginatedOrders:
	user_id = uuid.UUID(str(getattr(request.state, "user_id", None)))
	try:
		return await order_service.get_buyer_orders(
			db_session, user_id, limit, offset, status
		)
	except OrderNotFoundError as err:
		raise fastapi.HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": "Order not found"},
		) from err
