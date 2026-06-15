import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionLocal
from database.models.outbox import OutboxEvent, OutboxEventStatus

PublishFn = Callable[[str, dict], Awaitable[None]]

MODERATION_EVENT_TYPES = {
	"CREATED": "PRODUCT_CREATED",
	"EDITED": "PRODUCT_EDITED",
	"DELETED": "PRODUCT_DELETED",
}
MODERATION_ROUTING_KEYS = {
	"CREATED": "moderation.product.created",
	"EDITED": "moderation.product.edited",
	"DELETED": "moderation.product.deleted",
}
B2C_PRODUCT_DELETED_ROUTING_KEY = "b2c.product.deleted"
B2C_SKU_OUT_OF_STOCK_ROUTING_KEY = "b2c.sku.out_of_stock"
B2C_PRODUCT_BLOCKED_ROUTING_KEY = "b2c.product.blocked"


def build_moderation_product_event_payload(
	product_id: UUID,
	seller_id: UUID,
	idempotency_key: UUID,
	event: str = "CREATED",
	json_before: dict | None = None,
	json_after: dict | None = None,
) -> dict:
	occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
	event_type = MODERATION_EVENT_TYPES[event]
	event_payload = {
		"product_id": str(product_id),
		"seller_id": str(seller_id),
	}
	if event == "CREATED":
		if json_after is None:
			raise ValueError("PRODUCT_CREATED requires json_after")
		event_payload["json_after"] = json_after
	elif event == "EDITED":
		if json_before is None or json_after is None:
			raise ValueError("PRODUCT_EDITED requires json_before and json_after")
		event_payload["json_before"] = json_before
		event_payload["json_after"] = json_after

	return {
		"event_type": event_type,
		"idempotency_key": str(idempotency_key),
		"occurred_at": occurred_at,
		"payload": event_payload,
	}


def build_b2c_product_deleted_payload(
	product_id: UUID,
	sku_ids: list[UUID],
	idempotency_key: UUID,
) -> dict:
	occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
	return {
		"event_type": "PRODUCT_DELETED",
		"idempotency_key": str(idempotency_key),
		"occurred_at": occurred_at,
		"payload": {
			"product_id": str(product_id),
			"sku_ids": [str(sku_id) for sku_id in sku_ids],
		},
	}


def build_b2c_sku_out_of_stock_payload(
	sku_id: UUID,
	product_id: UUID,
	available_quantity: int,
	idempotency_key: UUID,
) -> dict:
	occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
	return {
		"event_type": "SKU_OUT_OF_STOCK",
		"idempotency_key": str(idempotency_key),
		"occurred_at": occurred_at,
		"payload": {
			"sku_id": str(sku_id),
			"product_id": str(product_id),
			"available_quantity": available_quantity,
		},
	}


def build_b2c_product_blocked_payload(
	product_id: UUID,
	sku_ids: list[UUID],
	hard_block: bool,
	idempotency_key: UUID,
	occurred_at: datetime | None = None,
) -> dict:
	when = occurred_at or datetime.now(timezone.utc)
	if when.tzinfo is None:
		when = when.replace(tzinfo=timezone.utc)
	return {
		"event_type": "PRODUCT_BLOCKED",
		"idempotency_key": str(idempotency_key),
		"occurred_at": when.isoformat().replace("+00:00", "Z"),
		"payload": {
			"product_id": str(product_id),
			"sku_ids": [str(sku_id) for sku_id in sku_ids],
			"hard_block": hard_block,
		},
	}


async def enqueue_moderation_product_event(
	db: AsyncSession,
	product_id: UUID,
	seller_id: UUID,
	event: str = "CREATED",
	json_before: dict | None = None,
	json_after: dict | None = None,
) -> OutboxEvent:
	idempotency_key = uuid.uuid4()
	event_type = MODERATION_EVENT_TYPES[event]
	routing_key = MODERATION_ROUTING_KEYS[event]
	payload = build_moderation_product_event_payload(
		product_id=product_id,
		seller_id=seller_id,
		idempotency_key=idempotency_key,
		event=event,
		json_before=json_before,
		json_after=json_after,
	)
	outbox_event = OutboxEvent(
		idempotency_key=idempotency_key,
		event_type=event_type,
		routing_key=routing_key,
		payload=payload,
		status=OutboxEventStatus.PENDING,
	)
	db.add(outbox_event)
	await db.flush()
	return outbox_event


async def enqueue_product_deleted_events(
	db: AsyncSession,
	product_id: UUID,
	seller_id: UUID,
	sku_ids: list[UUID],
) -> tuple[OutboxEvent, OutboxEvent]:
	moderation_event = await enqueue_moderation_product_event(
		db,
		product_id=product_id,
		seller_id=seller_id,
		event="DELETED",
	)

	idempotency_key = uuid.uuid4()
	b2c_payload = build_b2c_product_deleted_payload(
		product_id=product_id,
		sku_ids=sku_ids,
		idempotency_key=idempotency_key,
	)
	b2c_event = OutboxEvent(
		idempotency_key=idempotency_key,
		event_type="PRODUCT_DELETED",
		routing_key=B2C_PRODUCT_DELETED_ROUTING_KEY,
		payload=b2c_payload,
		status=OutboxEventStatus.PENDING,
	)
	db.add(b2c_event)
	await db.flush()
	return moderation_event, b2c_event


async def enqueue_sku_out_of_stock_event(
	db: AsyncSession,
	sku_id: UUID,
	product_id: UUID,
	available_quantity: int,
) -> OutboxEvent:
	idempotency_key = uuid.uuid4()
	event = OutboxEvent(
		idempotency_key=idempotency_key,
		event_type="SKU_OUT_OF_STOCK",
		routing_key=B2C_SKU_OUT_OF_STOCK_ROUTING_KEY,
		payload=build_b2c_sku_out_of_stock_payload(
			sku_id,
			product_id,
			available_quantity,
			idempotency_key,
		),
		status=OutboxEventStatus.PENDING,
	)
	db.add(event)
	await db.flush()
	return event


async def enqueue_product_blocked_event(
	db: AsyncSession,
	product_id: UUID,
	sku_ids: list[UUID],
	hard_block: bool,
	occurred_at: datetime | None = None,
) -> OutboxEvent:
	idempotency_key = uuid.uuid4()
	event = OutboxEvent(
		idempotency_key=idempotency_key,
		event_type="PRODUCT_BLOCKED",
		routing_key=B2C_PRODUCT_BLOCKED_ROUTING_KEY,
		payload=build_b2c_product_blocked_payload(
			product_id,
			sku_ids,
			hard_block,
			idempotency_key,
			occurred_at,
		),
		status=OutboxEventStatus.PENDING,
	)
	db.add(event)
	await db.flush()
	return event


async def fetch_pending_events(db: AsyncSession, limit: int = 50) -> list[OutboxEvent]:
	result = await db.execute(
		select(OutboxEvent)
		.where(OutboxEvent.status == OutboxEventStatus.PENDING)
		.order_by(OutboxEvent.created_at)
		.limit(limit)
	)
	return list(result.scalars().all())


async def get_pending_event_by_id(
	db: AsyncSession, event_id: UUID
) -> OutboxEvent | None:
	event = await db.get(OutboxEvent, event_id)
	if event is None or event.status != OutboxEventStatus.PENDING:
		return None
	return event


async def mark_event_sent(db: AsyncSession, event: OutboxEvent) -> None:
	event.status = OutboxEventStatus.SENT
	event.sent_at = datetime.now(timezone.utc)
	db.add(event)
	await db.commit()


async def deliver_pending_event(
	db: AsyncSession,
	event_id: UUID,
	publish: PublishFn,
) -> bool:
	db_event = await get_pending_event_by_id(db, event_id)
	if db_event is None:
		return False
	try:
		await publish(db_event.routing_key, db_event.payload)
		await mark_event_sent(db, db_event)
		return True
	except Exception:  # noqa
		await db.rollback()
		return False


async def process_pending_batch(publish: PublishFn, limit: int = 50) -> int:
	processed = 0
	async with SessionLocal() as db:
		events = await fetch_pending_events(db, limit=limit)

	for event in events:
		async with SessionLocal() as db:
			if await deliver_pending_event(db, event.id, publish):
				processed += 1
	return processed
