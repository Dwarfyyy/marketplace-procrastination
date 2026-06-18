import uuid
from datetime import datetime

from sqlalchemy import Result, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models.orders.order import Order, OrderStatusEnum, OrderStatusHistory
from database.models.orders.order_item import OrderItem
from exceptions.order import OrderNotFoundError


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


async def _create_order(
	db: AsyncSession,
	order_id: uuid.UUID,
	buyer_id: uuid.UUID,
	address_id: uuid.UUID,
	payment_method_id: uuid.UUID,
	comment: str | None,
	idempotency_key: uuid.UUID,
	request_hash: str,
	now: datetime,
) -> Order:
	order = Order(
		id=order_id,
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
) -> tuple[list[OrderItem], int]:
	subtotal = 0
	order_items: list[OrderItem] = []
	for cart_item, sku, product, image in enriched_items:
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


async def create_order_with_items(
	db: AsyncSession,
	order_id: uuid.UUID,
	buyer_id: uuid.UUID,
	idempotency_key: uuid.UUID,
	request_hash: str,
	address_id: uuid.UUID,
	payment_method_id: uuid.UUID,
	comment: str | None,
	now: datetime,
	enriched_items: list[tuple],
) -> uuid.UUID:
	transaction_ctx = db.begin_nested() if db.in_transaction() else db.begin()
	async with transaction_ctx:
		order = await _create_order(
			db,
			order_id,
			buyer_id,
			address_id,
			payment_method_id,
			comment,
			idempotency_key,
			request_hash,
			now,
		)
		order_items, subtotal = _build_order_items(order.id, enriched_items)
		order.subtotal = subtotal
		order.total = subtotal
		db.add_all(order_items)
		db.add(order)
		await change_order_status(db, order.id, OrderStatusEnum.PAID, None)

	return order.id


async def cancel_order(
	db: AsyncSession,
	order_id: uuid.UUID,
	buyer_id: uuid.UUID,
	reason: str | None = None,
) -> None:
	order = await get_order_by_id_for_buyer(db, order_id, buyer_id)
	if order is None:
		raise OrderNotFoundError()

	await change_order_status(db, order.id, OrderStatusEnum.CANCELLED, reason)
	await db.flush()
	return order.id


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
