import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.outbox import OutboxEvent, OutboxEventStatus


def build_moderated_event_payload(
	product_id: uuid.UUID,
	idempotency_key: uuid.UUID,
) -> dict:
	occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
	return {
		"idempotency_key": str(idempotency_key),
		"product_id": str(product_id),
		"event_type": "MODERATED",
		"hard_block": False,
		"occurred_at": occurred_at,
	}


def enqueue_moderated_event(db: AsyncSession, product_id: uuid.UUID) -> OutboxEvent:
	idempotency_key = uuid.uuid4()
	event = OutboxEvent(
		idempotency_key=idempotency_key,
		event_type="MODERATED",
		payload=build_moderated_event_payload(product_id, idempotency_key),
		status=OutboxEventStatus.PENDING,
	)
	db.add(event)
	return event


async def fetch_pending_events(db: AsyncSession, limit: int = 50) -> list[OutboxEvent]:
	result = await db.execute(
		select(OutboxEvent)
		.where(OutboxEvent.status == OutboxEventStatus.PENDING)
		.order_by(OutboxEvent.created_at)
		.limit(limit)
	)
	return list(result.scalars().all())


async def mark_event_sent(db: AsyncSession, event: OutboxEvent) -> None:
	event.status = OutboxEventStatus.SENT
	event.sent_at = datetime.now(timezone.utc)
	db.add(event)
	await db.commit()
