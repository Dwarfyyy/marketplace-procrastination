import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
	BlockingReason,
	ModerationStatus,
	OutboxEvent,
	ProductModeration,
)
from services.product_events import apply_product_event

pytestmark = pytest.mark.asyncio


async def _hard_reason(db: AsyncSession) -> BlockingReason:
	reason = BlockingReason(title="Counterfeit product", hard_block=True)
	db.add(reason)
	await db.commit()
	return reason


async def _card(
	db: AsyncSession,
	*,
	status: ModerationStatus = ModerationStatus.IN_REVIEW,
	moderator_id: uuid.UUID | None = None,
) -> ProductModeration:
	card = ProductModeration(
		product_id=uuid.uuid4(),
		seller_id=uuid.uuid4(),
		status=status,
		queue_priority=1,
		moderator_id=moderator_id or uuid.uuid4(),
		json_after={"title": "Product", "skus": [{"id": str(uuid.uuid4())}]},
	)
	db.add(card)
	await db.commit()
	return card


def _headers(moderator_id: uuid.UUID) -> dict[str, str]:
	return {"X-Moderator-ID": str(moderator_id)}


def _decline_body(reason_id: uuid.UUID) -> dict:
	return {
		"blocking_reason_ids": [str(reason_id)],
		"comment": "Confirmed counterfeit product",
		"field_reports": [
			{
				"field_path": "description",
				"message": "Description does not match product",
			}
		],
	}


async def _hard_block(
	client: AsyncClient,
	db: AsyncSession,
) -> tuple[ProductModeration, BlockingReason, uuid.UUID]:
	moderator_id = uuid.uuid4()
	card = await _card(db, moderator_id=moderator_id)
	reason = await _hard_reason(db)
	response = await client.post(
		f"/api/v1/tickets/{card.id}/block",
		headers=_headers(moderator_id),
		json=_decline_body(reason.id),
	)
	assert response.status_code == 200
	body = response.json()
	assert body["id"] == str(card.id)
	assert body["product_id"] == str(card.product_id)
	assert body["seller_id"] == str(card.seller_id)
	assert body["kind"] == "PRODUCT"
	assert body["status"] == "HARD_BLOCKED"
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
	return card, reason, moderator_id


async def test_hard_block_transitions_to_terminal_and_emits_event(
	client: AsyncClient,
	db: AsyncSession,
) -> None:
	card, reason, _moderator_id = await _hard_block(client, db)

	await db.refresh(card)
	assert card.status == ModerationStatus.HARD_BLOCKED
	assert card.blocking_reason_id == reason.id
	assert card.date_moderation is not None
	assert card.field_reports == [
		{
			"field_path": "description",
			"message": "Description does not match product",
		}
	]
	result = await db.execute(select(OutboxEvent))
	event = result.scalar_one()
	assert event.event_type == "BLOCKED"
	assert event.payload["event_type"] == "BLOCKED"


async def test_hard_block_event_carries_hard_block_true(
	client: AsyncClient,
	db: AsyncSession,
) -> None:
	card, reason, _moderator_id = await _hard_block(client, db)

	result = await db.execute(select(OutboxEvent))
	event = result.scalar_one()
	assert event.payload["product_id"] == str(card.product_id)
	assert event.payload["hard_block"] is True
	assert event.payload["blocking_reason_id"] == str(reason.id)
	assert event.payload["blocking_reason_title"] == reason.title
	assert event.payload["field_reports"] == [
		{
			"field_name": "description",
			"comment": "Description does not match product",
		}
	]
	assert event.payload["idempotency_key"] == str(event.idempotency_key)


async def test_any_modify_on_hard_blocked_returns_403(
	client: AsyncClient,
	db: AsyncSession,
) -> None:
	card, reason, moderator_id = await _hard_block(client, db)

	approve_response = await client.post(
		f"/api/v1/tickets/{card.id}/approve",
		headers=_headers(moderator_id),
		json={},
	)
	decline_response = await client.post(
		f"/api/v1/tickets/{card.id}/block",
		headers=_headers(moderator_id),
		json=_decline_body(reason.id),
	)

	assert approve_response.status_code == 403
	assert decline_response.status_code == 403
	assert approve_response.json()["code"] == "FORBIDDEN"
	assert decline_response.json()["code"] == "FORBIDDEN"
	assert set(approve_response.json()) == {"code", "message"}
	assert set(decline_response.json()) == {"code", "message"}


async def test_edited_event_on_hard_blocked_is_ignored(
	client: AsyncClient,
	db: AsyncSession,
) -> None:
	card, _reason, moderator_id = await _hard_block(client, db)
	original_snapshot = card.json_after
	event = {
		"event_type": "PRODUCT_EDITED",
		"payload": {
			"product_id": str(card.product_id),
			"seller_id": str(card.seller_id),
			"json_after": {"title": "Changed", "skus": []},
		},
	}

	await apply_product_event(db, event)
	await apply_product_event(db, event)
	await db.refresh(card)

	assert card.status == ModerationStatus.HARD_BLOCKED
	assert card.moderator_id == moderator_id
	assert card.json_after == original_snapshot


async def test_deleted_event_removes_hard_blocked(
	client: AsyncClient,
	db: AsyncSession,
) -> None:
	card, _reason, _moderator_id = await _hard_block(client, db)

	await apply_product_event(
		db,
		{
			"event_type": "PRODUCT_DELETED",
			"payload": {"product_id": str(card.product_id)},
		},
	)

	result = await db.execute(
		select(ProductModeration).where(
			ProductModeration.product_id == card.product_id
		)
	)
	assert result.scalar_one_or_none() is None
