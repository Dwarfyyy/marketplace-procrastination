import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ModerationStatus, ProductModeration
from tests.integration.events.conftest import (
	PRODUCT_EVENT_SERVICE_KEY_HEADERS,
	make_card,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _body(
	event_type: str,
	product_id: uuid.UUID,
	seller_id: uuid.UUID,
	*,
	idempotency_key: uuid.UUID | None = None,
	json_after: dict | None = None,
) -> dict:
	return {
		"event_type": event_type,
		"idempotency_key": str(idempotency_key or uuid.uuid4()),
		"occurred_at": datetime.now(timezone.utc).isoformat(),
		"payload": {
			"product_id": str(product_id),
			"seller_id": str(seller_id),
			"json_after": json_after if json_after is not None else {"title": "Product"},
		},
	}


async def _post(client: AsyncClient, body: dict) -> object:
	return await client.post(
		"/api/v1/b2b/events",
		headers=PRODUCT_EVENT_SERVICE_KEY_HEADERS,
		json=body,
	)


async def _reload_card(db: AsyncSession, product_id: uuid.UUID) -> ProductModeration:
	result = await db.execute(
		select(ProductModeration)
		.where(ProductModeration.product_id == product_id)
		.execution_options(populate_existing=True)
	)
	return result.scalar_one()


async def test_created_pending(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
) -> None:
	product_id = uuid.uuid4()
	snapshot = {"title": "New product", "price": 1000, "skus": []}

	response = await _post(
		client, _body("PRODUCT_CREATED", product_id, seller_id, json_after=snapshot)
	)

	assert response.status_code == 202
	body = response.json()
	assert body["processed"] is True
	assert body["status"] == "PENDING"

	card = await _reload_card(db_session, product_id)
	assert card.status == ModerationStatus.PENDING
	assert card.json_after == snapshot
	assert card.json_before is None


async def test_edited_returns_to_review(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
) -> None:
	product_id = uuid.uuid4()
	old_snapshot = {"title": "Old title", "price": 1000, "skus": []}
	new_snapshot = {"title": "New title", "price": 1200, "skus": []}
	await make_card(
		db_session,
		product_id=product_id,
		seller_id=seller_id,
		status=ModerationStatus.MODERATED,
		json_after=old_snapshot,
	)

	response = await _post(
		client, _body("PRODUCT_EDITED", product_id, seller_id, json_after=new_snapshot)
	)

	assert response.status_code == 202
	body = response.json()
	assert body["processed"] is True
	assert body["status"] == "PENDING"

	card = await _reload_card(db_session, product_id)
	assert card.status == ModerationStatus.PENDING
	assert card.json_after == new_snapshot
	assert card.json_before == old_snapshot


async def test_edited_updates_in_review(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
) -> None:
	# An edit arriving while the card is IN_REVIEW invalidates the
	# in-flight review: the card goes back to PENDING and the assigned
	# moderator is cleared, same as edits on MODERATED/BLOCKED cards.
	# This is what tests/test_approval.py::test_approve_after_edited_returns_409
	# relies on (approve must 409 once the underlying data changed).
	product_id = uuid.uuid4()
	old_snapshot = {"title": "Old title", "price": 1000, "skus": []}
	new_snapshot = {"title": "Updated title", "price": 1100, "skus": []}
	moderator_id = uuid.uuid4()
	card = await make_card(
		db_session,
		product_id=product_id,
		seller_id=seller_id,
		status=ModerationStatus.IN_REVIEW,
		json_after=old_snapshot,
	)
	card.moderator_id = moderator_id
	await db_session.commit()

	response = await _post(
		client, _body("PRODUCT_EDITED", product_id, seller_id, json_after=new_snapshot)
	)

	assert response.status_code == 202
	body = response.json()
	assert body["processed"] is True
	assert body["status"] == "PENDING"

	card = await _reload_card(db_session, product_id)
	assert card.status == ModerationStatus.PENDING
	assert card.json_after == new_snapshot
	assert card.json_before == old_snapshot
	assert card.moderator_id is None


async def test_deleted_archived(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
) -> None:
	# PRODUCT_DELETED removes the card from the moderation queue entirely
	# rather than tombstoning it, matching the credited US-MOD-01 behavior
	# (services/product_events.py: card row is deleted, not re-created).
	product_id = uuid.uuid4()
	await make_card(
		db_session,
		product_id=product_id,
		seller_id=seller_id,
		status=ModerationStatus.IN_REVIEW,
		json_after={"title": "Product"},
	)

	response = await _post(client, _body("PRODUCT_DELETED", product_id, seller_id))

	assert response.status_code == 202
	body = response.json()
	assert body["processed"] is True

	result = await db_session.execute(
		select(ProductModeration).where(ProductModeration.product_id == product_id)
	)
	assert result.scalar_one_or_none() is None


async def test_duplicate_event_no_side_effects(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
) -> None:
	product_id = uuid.uuid4()
	key = uuid.uuid4()
	body = _body(
		"PRODUCT_CREATED",
		product_id,
		seller_id,
		idempotency_key=key,
		json_after={"title": "Product", "price": 500},
	)

	first = await _post(client, body)
	second = await _post(client, body)

	assert first.status_code == 202
	assert first.json()["processed"] is True

	assert second.status_code == 409
	assert second.json()["code"] == "DUPLICATE_EVENT"

	# Only one card was created, and its status was not touched again.
	result = await db_session.execute(
		select(ProductModeration).where(ProductModeration.product_id == product_id)
	)
	cards = result.scalars().all()
	assert len(cards) == 1
	assert cards[0].status == ModerationStatus.PENDING


async def test_missing_service_header_401(
	client: AsyncClient,
	seller_id: uuid.UUID,
) -> None:
	product_id = uuid.uuid4()

	response = await client.post(
		"/api/v1/b2b/events",
		json=_body("PRODUCT_CREATED", product_id, seller_id),
	)

	assert response.status_code == 401
	assert set(response.json()) == {"code", "message"}
	assert response.json()["code"] == "UNAUTHORIZED"
