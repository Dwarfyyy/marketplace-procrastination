import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ModerationStatus, OutboxEvent, OutboxStatus, ProductModeration
from services.outbox import deliver_event
from services.product_events import apply_product_event

pytestmark = pytest.mark.asyncio


async def test_created_event_builds_pending_card_without_private_sku_fields(
	db: AsyncSession,
) -> None:
	product_id = uuid.uuid4()
	await apply_product_event(
		db,
		{
			"event_type": "PRODUCT_CREATED",
			"payload": {
				"product_id": str(product_id),
				"seller_id": str(uuid.uuid4()),
				"json_after": {
					"skus": [
						{
							"id": str(uuid.uuid4()),
							"cost_price": 100,
							"reserved_quantity": 2,
						}
					]
				},
			},
		},
	)

	result = await db.execute(
		select(ProductModeration).where(ProductModeration.product_id == product_id)
	)
	card = result.scalar_one()
	assert card.status == ModerationStatus.PENDING
	assert "cost_price" not in card.json_after["skus"][0]
	assert "reserved_quantity" not in card.json_after["skus"][0]


async def test_outbox_delivery_is_idempotent(db: AsyncSession) -> None:
	event = OutboxEvent(
		idempotency_key=uuid.uuid4(),
		event_type="MODERATED",
		payload={"event_type": "MODERATED"},
	)
	db.add(event)
	await db.commit()
	published: list[dict] = []

	async def publish(payload: dict) -> None:
		published.append(payload)

	assert await deliver_event(db, event.id, publish) is True
	assert await deliver_event(db, event.id, publish) is False
	await db.refresh(event)
	assert event.status == OutboxStatus.SENT
	assert published == [{"event_type": "MODERATED"}]
