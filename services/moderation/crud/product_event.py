import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ProductEventProcessed


async def lock_idempotency_key(db: AsyncSession, idempotency_key: uuid.UUID) -> None:
	bind = db.get_bind()
	if bind.dialect.name != "postgresql":
		# Advisory locks are Postgres-specific; other dialects (e.g. the
		# SQLite engine used in tests) rely on the unique constraint on
		# product_events_processed.idempotency_key instead.
		return
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
	db: AsyncSession,
	idempotency_key: uuid.UUID,
	product_id: uuid.UUID,
	event_type: str,
) -> ProductEventProcessed:
	event = ProductEventProcessed(
		idempotency_key=idempotency_key,
		product_id=product_id,
		event_type=event_type,
	)
	db.add(event)
	return event
