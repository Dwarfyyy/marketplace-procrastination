import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import SessionLocal
from database.models import OutboxEvent, OutboxStatus

PublishFn = Callable[[dict], Awaitable[None]]


async def publish_to_b2b(payload: dict) -> None:
	headers = {"X-Service-Key": settings.MOD_TO_B2B_KEY}
	async with httpx.AsyncClient(base_url=settings.B2B_URL, timeout=10) as client:
		response = await client.post(
			"/api/v1/moderation/events", json=payload, headers=headers
		)
		response.raise_for_status()


async def deliver_event(
	db: AsyncSession,
	event_id: UUID,
	publish: PublishFn = publish_to_b2b,
) -> bool:
	event = await db.get(OutboxEvent, event_id)
	if event is None or event.status != OutboxStatus.PENDING:
		return False
	try:
		await publish(event.payload)
	except Exception:  # noqa: BLE001 - every delivery failure must remain retryable
		await db.rollback()
		return False
	event.status = OutboxStatus.SENT
	event.sent_at = datetime.now(timezone.utc)
	await db.commit()
	return True


async def process_pending_batch(limit: int = 50) -> int:
	async with SessionLocal() as db:
		result = await db.execute(
			select(OutboxEvent.id)
			.where(OutboxEvent.status == OutboxStatus.PENDING)
			.order_by(OutboxEvent.created_at)
			.limit(limit)
		)
		event_ids = list(result.scalars())

	delivered = 0
	for event_id in event_ids:
		async with SessionLocal() as db:
			delivered += int(await deliver_event(db, event_id))
	return delivered


async def run_forever() -> None:
	while True:
		await process_pending_batch()
		await asyncio.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)
