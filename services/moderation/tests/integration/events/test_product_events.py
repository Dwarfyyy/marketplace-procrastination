import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.card import ModerationCard, ModerationCardStatus
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


async def _reload_card(db: AsyncSession, product_id: uuid.UUID) -> ModerationCard:
	result = await db.execute(
		select(ModerationCard)
		.where(ModerationCard.product_id == product_id)
		.execution_options(populate_existing=True)
	)
	return result.scalar_one()


async def test_created_pending(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
) -> None:
	product_id = uuid.uuid4()
	snapshot = {"title": "New product", "price": 1000}

	response = await _post(
		client, _body("PRODUCT_CREATED", product_id, seller_id, json_after=snapshot)
	)

	assert response.status_code == 202
	body = response.json()
	assert body["processed"] is True
	assert body["status"] == "PENDING"

	card = await _reload_card(db_session, product_id)
	assert card.status == ModerationCardStatus.PENDING
	assert card.json_after == snapshot
	assert card.json_before is None


async def test_edited_returns_to_review(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
) -> None:
	product_id = uuid.uuid4()
	old_snapshot = {"title": "Old title", "price": 1000}
	new_snapshot = {"title": "New title", "price": 1200}
	await make_card(
		db_session,
		product_id=product_id,
		seller_id=seller_id,
		status=ModerationCardStatus.MODERATED,
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
	assert card.status == ModerationCardStatus.PENDING
	assert card.json_after == new_snapshot
	assert card.json_before == old_snapshot


async def test_edited_updates_in_review(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
) -> None:
	product_id = uuid.uuid4()
	old_snapshot = {"title": "Old title", "price": 1000}
	new_snapshot = {"title": "Updated title", "price": 1100}
	await make_card(
		db_session,
		product_id=product_id,
		seller_id=seller_id,
		status=ModerationCardStatus.IN_REVIEW,
		json_after=old_snapshot,
	)

	response = await _post(
		client, _body("PRODUCT_EDITED", product_id, seller_id, json_after=new_snapshot)
	)

	assert response.status_code == 202
	body = response.json()
	assert body["processed"] is True
	assert body["status"] == "IN_REVIEW"

	card = await _reload_card(db_session, product_id)
	assert card.status == ModerationCardStatus.IN_REVIEW
	assert card.json_after == new_snapshot
	assert card.json_before is None


async def test_deleted_archived(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
) -> None:
	product_id = uuid.uuid4()
	await make_card(
		db_session,
		product_id=product_id,
		seller_id=seller_id,
		status=ModerationCardStatus.IN_REVIEW,
		json_after={"title": "Product"},
	)

	response = await _post(client, _body("PRODUCT_DELETED", product_id, seller_id))

	assert response.status_code == 202
	body = response.json()
	assert body["processed"] is True
	assert body["status"] == "ARCHIVED"

	card = await _reload_card(db_session, product_id)
	assert card.status == ModerationCardStatus.ARCHIVED


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
		select(ModerationCard).where(ModerationCard.product_id == product_id)
	)
	cards = result.scalars().all()
	assert len(cards) == 1
	assert cards[0].status == ModerationCardStatus.PENDING


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
