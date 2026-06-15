import uuid
from datetime import datetime

from sqlalchemy import Result, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models.catalog.base import ProductStatusEnum
from database.models.catalog.variants import Sku
from database.models.orders.order import Order, OrderStatusEnum, OrderStatusHistory
from database.models.orders.order_item import OrderItem
from exceptions.order import OrderNotFoundError, ReserveFailedError


async def get_order_by_idempotency_key(
	db: AsyncSession, idempotency_key: uuid.UUID
) -> Order | None:
	result: Result = await db.execute(
		select(Order)
		.where(Order.idempotency_key == idempotency_key)
		.options(
			selectinload(Order.items),
			selectinload(Order.address),
			selectinload(Order.payment_method),
			selectinload(Order.status_history),
		)
	)
	return result.scalar_one_or_none()


async def get_order_by_id_for_buyer(
	db: AsyncSession, order_id: uuid.UUID, buyer_id: uuid.UUID
) -> Order | None:
	result: Result = await db.execute(
		select(Order)
		.where(Order.id == order_id, Order.buyer_id == buyer_id)
		.options(
			selectinload(Order.items),
			selectinload(Order.address),
			selectinload(Order.payment_method),
			selectinload(Order.status_history),
		)
	)
	return result.scalar_one_or_none()


async def get_order_by_id(db: AsyncSession, order_id: uuid.UUID) -> Order | None:
	result: Result = await db.execute(
		select(Order)
		.where(Order.id == order_id)
		.options(
			selectinload(Order.items),
			selectinload(Order.address),
			selectinload(Order.payment_method),
			selectinload(Order.status_history),
		)
	)
	return result.scalar_one_or_none()


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


async def _lock_skus_for_update(
	db: AsyncSession, requested_by_sku: dict[uuid.UUID, int]
) -> dict[uuid.UUID, Sku]:
	sku_ids_sorted = sorted(requested_by_sku.keys(), key=lambda sku_id: str(sku_id))
	locked_result = await db.execute(
		select(Sku)
		.where(Sku.id.in_(sku_ids_sorted))
		.options(selectinload(Sku.product))
		.with_for_update()
	)
	return {sku.id: sku for sku in locked_result.scalars().all()}


def _collect_reserve_failures(
	requested_by_sku: dict[uuid.UUID, int], locked_skus: dict[uuid.UUID, Sku]
) -> list[dict]:
	reserve_failed: list[dict] = []
	for sku_id in sorted(requested_by_sku.keys(), key=lambda s: str(s)):
		sku = locked_skus.get(sku_id)
		if sku is None:
			reserve_failed.append(
				_build_failed_item(sku_id, requested_by_sku[sku_id], 0, "SKU_NOT_FOUND")
			)
			continue

		product = sku.product
		req_qty = requested_by_sku[sku_id]
		if product.deleted:
			reserve_failed.append(
				_build_failed_item(sku.id, req_qty, None, "PRODUCT_DELETED")
			)
		elif product.status == ProductStatusEnum.BLOCKED:
			reserve_failed.append(
				_build_failed_item(sku.id, req_qty, None, "PRODUCT_BLOCKED")
			)
		elif product.status != ProductStatusEnum.MODERATED:
			reserve_failed.append(
				_build_failed_item(sku.id, req_qty, None, "PRODUCT_BLOCKED")
			)
		elif sku.active_quantity < req_qty:
			reason = (
				"OUT_OF_STOCK" if sku.active_quantity <= 0 else "INSUFFICIENT_STOCK"
			)
			reserve_failed.append(
				_build_failed_item(sku.id, req_qty, sku.active_quantity, reason)
			)
	return reserve_failed


def _apply_reserve(
	locked_skus: dict[uuid.UUID, Sku], requested_by_sku: dict[uuid.UUID, int]
) -> None:
	for sku_id, req_qty in requested_by_sku.items():
		sku = locked_skus[sku_id]
		sku.active_quantity -= req_qty
		sku.reserved_quantity += req_qty


async def _create_order(
	db: AsyncSession,
	buyer_id: uuid.UUID,
	address_id: uuid.UUID,
	payment_method_id: uuid.UUID,
	comment: str | None,
	idempotency_key: uuid.UUID,
	request_hash: str,
	now: datetime,
) -> Order:
	order = Order(
		buyer_id=buyer_id,
		status=OrderStatusEnum.PAID,
		subtotal=0,
		delivery_cost=0,
		total=0,
		address_id=address_id,
		payment_method_id=payment_method_id,
		comment=comment,
		idempotency_key=idempotency_key,
		idempotency_request_hash=request_hash,
		paid_at=now,
	)
	db.add(order)
	await db.flush()
	return order


def _build_order_items(
	order_id: uuid.UUID,
	enriched_items: list[tuple],
	locked_skus: dict[uuid.UUID, Sku],
) -> tuple[list[OrderItem], int]:
	subtotal = 0
	order_items: list[OrderItem] = []
	for cart_item, _sku, _product, image in enriched_items:
		sku = locked_skus[cart_item.sku_id]
		product = sku.product
		unit_price = sku.price
		line_total = unit_price * cart_item.quantity
		subtotal += line_total

		image_url = image.url if image is not None else None
		order_items.append(
			OrderItem(
				order_id=order_id,
				sku_id=sku.id,
				product_id=product.id,
				product_title=product.title,
				sku_name=sku.name,
				quantity=cart_item.quantity,
				unit_price=unit_price,
				line_total=line_total,
				image_url=image_url,
			)
		)
	return order_items, subtotal


async def change_order_status(
	db: AsyncSession,
	order_id: uuid.UUID,
	status: OrderStatusEnum,
	reason: str | None,
) -> None:
	order = await get_order_by_id(db, order_id)
	if order is None:
		raise OrderNotFoundError()

	order_status_history = OrderStatusHistory(
		order_id=order_id,
		status=status,
		reason=reason,
	)
	db.add(order_status_history)
	order.status_history.append(order_status_history)
	order.status = status
	await db.flush()


async def reserve_and_create_order(
	db: AsyncSession,
	buyer_id: uuid.UUID,
	idempotency_key: uuid.UUID,
	request_hash: str,
	address_id: uuid.UUID,
	payment_method_id: uuid.UUID,
	comment: str | None,
	now: datetime,
	requested_by_sku: dict[uuid.UUID, int],
	enriched_items: list[tuple],
) -> uuid.UUID:
	transaction_ctx = db.begin_nested() if db.in_transaction() else db.begin()
	async with transaction_ctx:
		locked_skus = await _lock_skus_for_update(db, requested_by_sku)
		reserve_failed = _collect_reserve_failures(requested_by_sku, locked_skus)
		if reserve_failed:
			raise ReserveFailedError(reserve_failed)

		_apply_reserve(locked_skus, requested_by_sku)
		for sku in locked_skus.values():
			db.add(sku)

		order = await _create_order(
			db,
			buyer_id,
			address_id,
			payment_method_id,
			comment,
			idempotency_key,
			request_hash,
			now,
		)
		order_items, subtotal = _build_order_items(
			order.id, enriched_items, locked_skus
		)
		order.subtotal = subtotal
		order.total = subtotal
		db.add_all(order_items)
		db.add(order)
		await change_order_status(db, order.id, OrderStatusEnum.PAID, None)

	return order.id


async def _lock_skus_for_order_items(
	db: AsyncSession, order_items: list[OrderItem]
) -> dict[uuid.UUID, Sku]:
	sku_ids_sorted = sorted({item.sku_id for item in order_items}, key=str)
	locked_result = await db.execute(
		select(Sku).where(Sku.id.in_(sku_ids_sorted)).with_for_update()
	)
	return {sku.id: sku for sku in locked_result.scalars().all()}


def _apply_unreserve(
	locked_skus: dict[uuid.UUID, Sku], order_items: list[OrderItem]
) -> None:
	for item in order_items:
		sku = locked_skus.get(item.sku_id)
		if sku is None:
			continue
		sku.reserved_quantity = max(0, sku.reserved_quantity - item.quantity)
		sku.active_quantity += item.quantity


async def unreserve_order_items(db: AsyncSession, order: Order) -> None:
	transaction_ctx = db.begin_nested() if db.in_transaction() else db.begin()
	async with transaction_ctx:
		locked_skus = await _lock_skus_for_order_items(db, order.items)
		_apply_unreserve(locked_skus, order.items)
		for sku in locked_skus.values():
			db.add(sku)


def _apply_fulfill(
	locked_skus: dict[uuid.UUID, Sku], order_items: list[OrderItem]
) -> None:
	for item in order_items:
		sku = locked_skus.get(item.sku_id)
		if sku is None:
			continue
		sku.reserved_quantity = max(0, sku.reserved_quantity - item.quantity)


async def fulfill_order_items(db: AsyncSession, order: Order, now: datetime) -> None:
	transaction_ctx = db.begin_nested() if db.in_transaction() else db.begin()
	async with transaction_ctx:
		locked_skus = await _lock_skus_for_order_items(db, order.items)
		_apply_fulfill(locked_skus, order.items)
		for sku in locked_skus.values():
			db.add(sku)
		order.fulfilled_at = now
		db.add(order)


async def get_orders_pending_fulfillment(db: AsyncSession) -> list[Order]:
	result: Result = await db.execute(
		select(Order)
		.where(
			Order.status == OrderStatusEnum.DELIVERED,
			Order.fulfilled_at.is_(None),
		)
		.options(selectinload(Order.items))
	)
	return list(result.scalars().all())


async def get_buyer_orders(
	db: AsyncSession,
	buyer_id: uuid.UUID,
	limit: int,
	offset: int,
	status: OrderStatusEnum | None,
) -> tuple[list[Order], int]:
	filters = [Order.buyer_id == buyer_id]
	if status is not None:
		filters.append(Order.status == status)

	count_result = await db.execute(
		select(func.count()).select_from(Order).where(*filters)
	)
	total_count = count_result.scalar() or 0

	query = (
		select(Order)
		.where(*filters)
		.order_by(Order.created_at.desc())
		.limit(limit)
		.offset(offset)
		.options(
			selectinload(Order.items),
			selectinload(Order.address),
			selectinload(Order.payment_method),
			selectinload(Order.status_history),
		)
	)
	result: Result = await db.execute(query)
	return list(result.scalars().all()), total_count
