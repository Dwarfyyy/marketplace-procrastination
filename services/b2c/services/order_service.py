import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

import crud.address as address_crud
import crud.cart as cart_crud
import crud.order as order_crud
import crud.payment_method as payment_method_crud
from database.models.catalog.base import ProductStatusEnum
from database.models.orders.order import OrderStatusEnum
from exceptions.order import (
	AddressNotFoundError,
	EmptyCartError,
	IdempotencyConflictError,
	InvalidIdempotencyKeyError,
	OrderNotCancelableError,
	OrderNotFoundError,
	PaymentMethodNotFoundError,
	ReserveFailedError,
)
from schemas.cart import CartValidationResponse
from schemas.order import OrderResponse, PaginatedOrders
from services import cart_service, schemas_builder

logger = logging.getLogger(__name__)


def parse_idempotency_key(value: str) -> uuid.UUID:
	try:
		return uuid.UUID(value)
	except ValueError as err:
		raise InvalidIdempotencyKeyError() from err


def _build_failed_item(
	sku_id: uuid.UUID,
	requested: int,
	available: int | None,
	reason: str,
) -> dict:
	item: dict = {"sku_id": str(sku_id), "requested": requested, "reason": reason}
	if available is not None:
		item["available"] = available
	return item


async def _ensure_checkout_refs_exist(
	db: AsyncSession,
	buyer_id: uuid.UUID,
	address_id: uuid.UUID,
	payment_method_id: uuid.UUID,
) -> None:
	address = await address_crud.get_address_by_id_for_user(db, address_id, buyer_id)
	if address is None:
		raise AddressNotFoundError()

	payment_method = await payment_method_crud.get_payment_method_by_id_for_user(
		db, payment_method_id, buyer_id
	)
	if payment_method is None:
		raise PaymentMethodNotFoundError()


async def _get_checkout_items(db: AsyncSession, buyer_id: uuid.UUID) -> list[tuple]:
	enriched_items = await cart_crud.get_cart_items_with_details(db, buyer_id, None)
	if not enriched_items:
		raise EmptyCartError()
	return enriched_items


def _validate_snapshot_if_needed(
	enriched_items: list[tuple],
	items_snapshot: list[dict] | None,
	cart_validation: CartValidationResponse,
) -> CartValidationResponse | None:
	if items_snapshot is None:
		return None

	current = {
		str(cart_item.sku_id): {
			"sku_id": str(cart_item.sku_id),
			"quantity": cart_item.quantity,
			"unit_price": sku.price,
		}
		for cart_item, sku, _product, _image in enriched_items
	}
	provided = {str(item["sku_id"]): item for item in items_snapshot}
	if current != provided:
		return CartValidationResponse(
			is_valid=False, cart=cart_validation.cart, issues=[]
		)
	return None


def _aggregate_requested_by_sku(enriched_items: list[tuple]) -> dict[uuid.UUID, int]:
	requested_by_sku: dict[uuid.UUID, int] = {}
	for cart_item, _sku, _product, _image in enriched_items:
		requested_by_sku[cart_item.sku_id] = (
			requested_by_sku.get(cart_item.sku_id, 0) + cart_item.quantity
		)
	return requested_by_sku


def _collect_precheck_failures(enriched_items: list[tuple]) -> list[dict]:
	failed_items: list[dict] = []
	for cart_item, sku, product, _image in enriched_items:
		if product.deleted:
			failed_items.append(
				_build_failed_item(sku.id, cart_item.quantity, None, "PRODUCT_DELETED")
			)
			continue
		if product.status == ProductStatusEnum.BLOCKED:
			failed_items.append(
				_build_failed_item(sku.id, cart_item.quantity, None, "PRODUCT_BLOCKED")
			)
			continue
		if product.status != ProductStatusEnum.MODERATED:
			failed_items.append(
				_build_failed_item(sku.id, cart_item.quantity, None, "PRODUCT_BLOCKED")
			)
			continue
		if sku.active_quantity <= 0:
			failed_items.append(
				_build_failed_item(sku.id, cart_item.quantity, 0, "OUT_OF_STOCK")
			)
			continue
		if cart_item.quantity > sku.active_quantity:
			failed_items.append(
				_build_failed_item(
					sku.id,
					cart_item.quantity,
					sku.active_quantity,
					"INSUFFICIENT_STOCK",
				)
			)
	return failed_items


async def checkout(
	db: AsyncSession,
	buyer_id: uuid.UUID,
	idempotency_key: uuid.UUID,
	body_raw: dict,
	address_id: uuid.UUID,
	payment_method_id: uuid.UUID,
	comment: str | None,
	items_snapshot: list[dict] | None,
) -> OrderResponse | CartValidationResponse:
	payload = json.dumps(
		body_raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
	)
	request_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

	existing = await order_crud.get_order_by_idempotency_key(db, idempotency_key)
	if existing is not None:
		if existing.idempotency_request_hash != request_hash:
			raise IdempotencyConflictError()
		return schemas_builder.build_order_response(existing)

	await _ensure_checkout_refs_exist(db, buyer_id, address_id, payment_method_id)
	enriched_items = await _get_checkout_items(db, buyer_id)

	validation = await cart_service.validate_cart(db, buyer_id, None)
	if not validation.is_valid:
		return validation

	snapshot_mismatch = _validate_snapshot_if_needed(
		enriched_items, items_snapshot, validation
	)
	if snapshot_mismatch is not None:
		return snapshot_mismatch

	requested_by_sku = _aggregate_requested_by_sku(enriched_items)
	failed_items = _collect_precheck_failures(enriched_items)
	if failed_items:
		raise ReserveFailedError(failed_items)

	now = datetime.now(timezone.utc)
	try:
		order_id = await order_crud.reserve_and_create_order(
			db,
			buyer_id=buyer_id,
			idempotency_key=idempotency_key,
			request_hash=request_hash,
			address_id=address_id,
			payment_method_id=payment_method_id,
			comment=comment,
			now=now,
			requested_by_sku=requested_by_sku,
			enriched_items=enriched_items,
		)
		order = await order_crud.get_order_by_id_for_buyer(db, order_id, buyer_id)
		return schemas_builder.build_order_response(order)

	except IntegrityError:
		existing2 = await order_crud.get_order_by_idempotency_key(db, idempotency_key)
		if existing2 is None:
			raise
		if existing2.idempotency_request_hash != request_hash:
			raise IdempotencyConflictError() from None
		return schemas_builder.build_order_response(existing2)


async def cancel_order(
	db: AsyncSession,
	order_id: uuid.UUID,
	buyer_id: uuid.UUID,
	reason: str | None = None,
) -> OrderResponse:
	order = await order_crud.get_order_by_id_for_buyer(db, order_id, buyer_id)
	if order is None:
		raise OrderNotFoundError()

	if order.status not in [OrderStatusEnum.CREATED, OrderStatusEnum.PAID]:
		raise OrderNotCancelableError()

	try:
		await order_crud.unreserve_order_items(db, order)
	except SQLAlchemyError:
		logger.exception(
			"Unreserve failed for order %s, marking CANCEL_PENDING", order_id
		)
		await order_crud.change_order_status(
			db, order.id, OrderStatusEnum.CANCEL_PENDING, reason
		)
		order_updated = await order_crud.get_order_by_id_for_buyer(
			db, order_id, buyer_id
		)
		return schemas_builder.build_order_response(order_updated)

	await order_crud.change_order_status(db, order.id, OrderStatusEnum.CANCELLED, reason)
	order_updated = await order_crud.get_order_by_id_for_buyer(db, order_id, buyer_id)

	return schemas_builder.build_order_response(order_updated)


async def get_order_by_id_for_buyer(
	db: AsyncSession,
	order_id: uuid.UUID,
	buyer_id: uuid.UUID,
) -> OrderResponse:
	order = await order_crud.get_order_by_id_for_buyer(db, order_id, buyer_id)
	if order is None:
		raise OrderNotFoundError()
	return schemas_builder.build_order_response(order)


async def get_buyer_orders(
	db: AsyncSession,
	buyer_id: uuid.UUID,
	limit: int,
	offset: int,
	status: OrderStatusEnum | None,
) -> PaginatedOrders:
	orders, total_count = await order_crud.get_buyer_orders(
		db, buyer_id, limit, offset, status
	)
	return PaginatedOrders(
		items=[schemas_builder.build_order_response(order) for order in orders],
		total_count=total_count,
		limit=limit,
		offset=offset,
	)
