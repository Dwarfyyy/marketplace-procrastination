import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import services.card_service as card_service
from database.models.card import ModerationCard, ModerationCardStatus
from database.models.outbox import OutboxEvent, OutboxEventStatus
from tests.integration.cards.conftest import auth_headers, make_card

pytestmark = pytest.mark.asyncio(loop_scope="session")

PRODUCT_SNAPSHOT_WITH_SKU = {
	"title": "Product",
	"skus": [{"id": str(uuid.uuid4()), "price": 100}],
}
PRODUCT_SNAPSHOT_WITHOUT_SKU = {"title": "Product", "skus": []}


async def _reload_card(db: AsyncSession, card_id: uuid.UUID) -> ModerationCard:
	result = await db.execute(
		select(ModerationCard)
		.where(ModerationCard.id == card_id)
		.execution_options(populate_existing=True)
	)
	return result.scalar_one()


async def _outbox_events(db: AsyncSession, product_id: uuid.UUID) -> list[OutboxEvent]:
	result = await db.execute(select(OutboxEvent))
	return [
		event
		for event in result.scalars().all()
		if event.payload["product_id"] == str(product_id)
	]


@pytest.fixture(autouse=True)
def _mock_b2b_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
	async def _fake_send(_payload: dict) -> bool:
		return True

	monkeypatch.setattr(card_service, "send_moderation_event", _fake_send)


async def test_approve_transitions_to_moderated_and_emits_event(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
	moderator_id: uuid.UUID,
) -> None:
	product_id = uuid.uuid4()
	card = await make_card(
		db_session,
		product_id=product_id,
		seller_id=seller_id,
		status=ModerationCardStatus.IN_REVIEW,
		moderator_id=moderator_id,
		json_after=PRODUCT_SNAPSHOT_WITH_SKU,
	)

	response = await client.post(
		f"/api/v1/cards/{card.id}/approve", headers=auth_headers(moderator_id)
	)

	assert response.status_code == 200
	body = response.json()
	assert body["card_id"] == str(card.id)
	assert body["status"] == "MODERATED"

	reloaded = await _reload_card(db_session, card.id)
	assert reloaded.status == ModerationCardStatus.MODERATED

	events = await _outbox_events(db_session, product_id)
	assert len(events) == 1
	assert events[0].event_type == "MODERATED"
	assert events[0].status == OutboxEventStatus.SENT
	assert events[0].payload["product_id"] == str(product_id)


async def test_approve_others_card_returns_403(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
	moderator_id: uuid.UUID,
) -> None:
	other_moderator_id = uuid.uuid4()
	card = await make_card(
		db_session,
		product_id=uuid.uuid4(),
		seller_id=seller_id,
		status=ModerationCardStatus.IN_REVIEW,
		moderator_id=other_moderator_id,
		json_after=PRODUCT_SNAPSHOT_WITH_SKU,
	)

	response = await client.post(
		f"/api/v1/cards/{card.id}/approve", headers=auth_headers(moderator_id)
	)

	assert response.status_code == 403

	reloaded = await _reload_card(db_session, card.id)
	assert reloaded.status == ModerationCardStatus.IN_REVIEW


async def test_approve_after_edited_returns_409(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
	moderator_id: uuid.UUID,
) -> None:
	# Seller edited the product while it was in review: PRODUCT_EDITED on a
	# MODERATED card returns it to PENDING (see flows/moderation-flows.md),
	# so a retried approve must reject the now-stale IN_REVIEW assumption.
	card = await make_card(
		db_session,
		product_id=uuid.uuid4(),
		seller_id=seller_id,
		status=ModerationCardStatus.PENDING,
		moderator_id=moderator_id,
		json_after=PRODUCT_SNAPSHOT_WITH_SKU,
	)

	response = await client.post(
		f"/api/v1/cards/{card.id}/approve", headers=auth_headers(moderator_id)
	)

	assert response.status_code == 409

	reloaded = await _reload_card(db_session, card.id)
	assert reloaded.status == ModerationCardStatus.PENDING


async def test_approve_without_sku_returns_409(
	client: AsyncClient,
	db_session: AsyncSession,
	seller_id: uuid.UUID,
	moderator_id: uuid.UUID,
) -> None:
	card = await make_card(
		db_session,
		product_id=uuid.uuid4(),
		seller_id=seller_id,
		status=ModerationCardStatus.IN_REVIEW,
		moderator_id=moderator_id,
		json_after=PRODUCT_SNAPSHOT_WITHOUT_SKU,
	)

	response = await client.post(
		f"/api/v1/cards/{card.id}/approve", headers=auth_headers(moderator_id)
	)

	assert response.status_code == 409

	reloaded = await _reload_card(db_session, card.id)
	assert reloaded.status == ModerationCardStatus.IN_REVIEW
