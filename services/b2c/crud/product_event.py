import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.cart.item import CartItem
from database.models.cart.product_event import ProductEventProcessed


async def lock_idempotency_key(db: AsyncSession, idempotency_key: uuid.UUID) -> None:
	unsigned_key = idempotency_key.int & ((1 << 63) - 1)
	await db.execute(select(func.pg_advisory_xact_lock(unsigned_key)))


async def get_processed_event(
	db: AsyncSession, idempotency_key: uuid.UUID
) -> ProductEventProcessed | None:
	result = await db.execute(
		select(ProductEventProcessed).where(
			ProductEventProcessed.idempotency_key == idempotency_key
		)
	)
	return result.scalar_one_or_none()


def add_processed_event(
	db: AsyncSession, idempotency_key: uuid.UUID, event_type: str
) -> ProductEventProcessed:
	event = ProductEventProcessed(idempotency_key=idempotency_key, event_type=event_type)
	db.add(event)
	return event


async def mark_cart_items_unavailable(
	db: AsyncSession, sku_ids: list[uuid.UUID], reason: str
) -> int:
	if not sku_ids:
		return 0
	result = await db.execute(
		update(CartItem)
		.where(CartItem.sku_id.in_(sku_ids))
		.values(unavailable_reason=reason)
	)
	return result.rowcount or 0
