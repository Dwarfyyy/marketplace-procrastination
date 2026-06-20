import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ModerationStatus, OutboxEvent, ProductModeration
from services.product_events import apply_product_event

pytestmark = pytest.mark.asyncio


async def _card(
	db: AsyncSession,
	*,
	status: ModerationStatus = ModerationStatus.IN_REVIEW,
	moderator_id: uuid.UUID | None = None,
	skus: list[dict] | None = None,
) -> ProductModeration:
	card = ProductModeration(
		product_id=uuid.uuid4(),
		seller_id=uuid.uuid4(),
		status=status,
		queue_priority=1,
		moderator_id=moderator_id or uuid.uuid4(),
		json_after={"skus": [{"id": str(uuid.uuid4())}] if skus is None else skus},
		field_reports=[{"field_path": "title", "message": "Old report"}],
	)
	db.add(card)
	await db.commit()
	return card


def _headers(moderator_id: uuid.UUID) -> dict[str, str]:
	return {"X-Moderator-ID": str(moderator_id)}


async def test_approve_transitions_to_moderated_and_emits_event(
	client: AsyncClient, db: AsyncSession
) -> None:
	moderator_id = uuid.uuid4()
	card = await _card(db, moderator_id=moderator_id)

	response = await client.post(
		f"/api/v1/tickets/{card.id}/approve",
		headers=_headers(moderator_id),
		json={"comment": "Looks good"},
	)

	assert response.status_code == 200
	body = response.json()
	assert body["id"] == str(card.id)
	assert body["product_id"] == str(card.product_id)
	assert body["seller_id"] == str(card.seller_id)
	assert body["kind"] == "PRODUCT"
	assert body["status"] == "APPROVED"
	assert body["queue_priority"] == card.queue_priority
	assert set(body) == {
		"id",
		"product_id",
		"seller_id",
		"kind",
		"status",
		"queue_priority",
		"created_at",
	}
	await db.refresh(card)
	assert card.status == ModerationStatus.MODERATED
	assert card.moderator_comment == "Looks good"
	assert card.date_moderation is not None
	assert card.field_reports == []
	result = await db.execute(select(OutboxEvent))
	event = result.scalar_one()
	assert event.event_type == "MODERATED"
	assert event.payload["product_id"] == str(card.product_id)
	assert event.payload["event_type"] == "MODERATED"
	assert event.payload["idempotency_key"] == str(event.idempotency_key)


async def test_approve_others_card_returns_403(
	client: AsyncClient, db: AsyncSession
) -> None:
	card = await _card(db, moderator_id=uuid.uuid4())

	response = await client.post(
		f"/api/v1/tickets/{card.id}/approve",
		headers=_headers(uuid.uuid4()),
		json={},
	)

	assert response.status_code == 403
	assert response.json()["code"] == "FORBIDDEN"
	assert set(response.json()) == {"code", "message"}


async def test_approve_after_edited_returns_409(
	client: AsyncClient, db: AsyncSession
) -> None:
	moderator_id = uuid.uuid4()
	card = await _card(db, moderator_id=moderator_id)
	await apply_product_event(
		db,
		{
			"event_type": "PRODUCT_EDITED",
			"payload": {
				"product_id": str(card.product_id),
				"seller_id": str(card.seller_id),
				"json_after": {"skus": [{"id": str(uuid.uuid4())}]},
			},
		},
	)

	response = await client.post(
		f"/api/v1/tickets/{card.id}/approve",
		headers=_headers(moderator_id),
		json={},
	)

	assert response.status_code == 409
	assert response.json()["code"] == "CONFLICT"
	assert set(response.json()) == {"code", "message"}


async def test_approve_without_sku_returns_409(
	client: AsyncClient, db: AsyncSession
) -> None:
	moderator_id = uuid.uuid4()
	card = await _card(db, moderator_id=moderator_id, skus=[])

	response = await client.post(
		f"/api/v1/tickets/{card.id}/approve",
		headers=_headers(moderator_id),
		json={},
	)

	assert response.status_code == 409
	assert response.json()["code"] == "CONFLICT"
	assert set(response.json()) == {"code", "message"}
