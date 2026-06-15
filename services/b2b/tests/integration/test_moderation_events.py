import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.catalog.base import Product, ProductStatusEnum
from database.models.outbox import OutboxEvent
from tests.integration.conftest import (
	MODERATION_SERVICE_KEY_HEADERS,
	ModerationEventData,
	auth_headers,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _body(
	product_id: uuid.UUID,
	status: str,
	*,
	idempotency_key: uuid.UUID | None = None,
	hard_block: bool = False,
) -> dict:
	body = {
		"idempotency_key": str(idempotency_key or uuid.uuid4()),
		"product_id": str(product_id),
		"event_type": status,
		"hard_block": hard_block,
		"occurred_at": datetime.now(timezone.utc).isoformat(),
	}
	if status == "BLOCKED":
		body.update(
			{
				"blocking_reason_id": str(uuid.uuid4()),
				"blocking_reason_title": "Product content violates policy",
				"moderator_comment": "Fix the description and images",
				"field_reports": [
					{
						"field_name": "description",
						"comment": "Description does not match the product",
					}
				],
			}
		)
	return body


async def _post(client: AsyncClient, body: dict) -> object:
	return await client.post(
		"/api/v1/moderation/events",
		headers=MODERATION_SERVICE_KEY_HEADERS,
		json=body,
	)


async def _reload_product(db: AsyncSession, product_id: uuid.UUID) -> Product:
	result = await db.execute(
		select(Product)
		.where(Product.id == product_id)
		.execution_options(populate_existing=True)
	)
	return result.scalar_one()


async def _blocked_events(db: AsyncSession, product_id: uuid.UUID) -> list[OutboxEvent]:
	result = await db.execute(
		select(OutboxEvent).where(OutboxEvent.event_type == "PRODUCT_BLOCKED")
	)
	return [
		event
		for event in result.scalars().all()
		if event.payload["payload"]["product_id"] == str(product_id)
	]


async def test_moderated_event_clears_blocking_data(
	client: AsyncClient,
	moderation_event_data: ModerationEventData,
	db_session: AsyncSession,
) -> None:
	response = await _post(
		client,
		_body(moderation_event_data.blocked_product.id, "MODERATED"),
	)

	assert response.status_code == 204
	assert response.content == b""
	product = await _reload_product(
		db_session, moderation_event_data.blocked_product.id
	)
	assert product.status == ProductStatusEnum.MODERATED
	assert product.blocked_reason_id is None
	assert product.blocking_reason_title is None
	assert product.moderator_comment == ""
	assert product.field_reports == []


async def test_blocked_soft_saves_field_reports(
	client: AsyncClient,
	moderation_event_data: ModerationEventData,
	db_session: AsyncSession,
) -> None:
	response = await _post(
		client,
		_body(moderation_event_data.product.id, "BLOCKED"),
	)

	assert response.status_code == 204
	assert response.content == b""
	product = await _reload_product(db_session, moderation_event_data.product.id)
	assert product.status == ProductStatusEnum.BLOCKED
	assert product.blocking_reason_title == "Product content violates policy"
	assert product.field_reports[0]["field_name"] == "description"
	events = await _blocked_events(db_session, product.id)
	assert len(events) == 1
	assert events[0].routing_key == "b2c.product.blocked"
	assert events[0].payload["payload"]["sku_ids"] == [
		str(moderation_event_data.sku.id)
	]
	assert events[0].payload["payload"]["hard_block"] is False


async def test_blocked_hard_sets_terminal_status(
	client: AsyncClient,
	moderation_event_data: ModerationEventData,
	db_session: AsyncSession,
) -> None:
	response = await _post(
		client,
		_body(moderation_event_data.product.id, "BLOCKED", hard_block=True),
	)

	assert response.status_code == 204
	assert response.content == b""
	product = await _reload_product(db_session, moderation_event_data.product.id)
	assert product.status == ProductStatusEnum.HARD_BLOCKED
	events = await _blocked_events(db_session, product.id)
	assert len(events) == 1
	assert events[0].payload["payload"]["hard_block"] is True


async def test_hard_blocked_product_rejects_seller_edits(
	client: AsyncClient,
	moderation_event_data: ModerationEventData,
	db_session: AsyncSession,
) -> None:
	await _post(
		client,
		_body(moderation_event_data.product.id, "BLOCKED", hard_block=True),
	)
	headers = await auth_headers(moderation_event_data.seller.id, db_session)

	edit_response = await client.patch(
		f"/api/v1/products/{moderation_event_data.product.id}",
		headers=headers,
		json={"title": "Forbidden edit"},
	)
	delete_response = await client.delete(
		f"/api/v1/products/{moderation_event_data.product.id}",
		headers=headers,
	)

	assert edit_response.status_code == 403
	assert edit_response.json()["code"] == "FORBIDDEN"
	assert delete_response.status_code == 403
	assert delete_response.json()["code"] == "FORBIDDEN"


async def test_duplicate_event_same_idempotency_key_no_side_effects(
	client: AsyncClient,
	moderation_event_data: ModerationEventData,
	db_session: AsyncSession,
) -> None:
	key = uuid.uuid4()
	body = _body(
		moderation_event_data.product.id,
		"BLOCKED",
		idempotency_key=key,
	)

	first = await _post(client, body)
	second = await _post(client, body)

	assert first.status_code == 204
	assert first.content == b""
	assert second.status_code == 204
	assert second.content == b""
	assert len(await _blocked_events(db_session, moderation_event_data.product.id)) == 1


async def test_missing_service_key_returns_401(
	client: AsyncClient,
	moderation_event_data: ModerationEventData,
) -> None:
	response = await client.post(
		"/api/v1/moderation/events",
		json=_body(moderation_event_data.product.id, "MODERATED"),
	)

	assert response.status_code == 401
	assert set(response.json()) == {"code", "message"}
	assert response.json()["code"] == "UNAUTHORIZED"


async def test_b2c_service_key_cannot_apply_moderation(
	client: AsyncClient,
	moderation_event_data: ModerationEventData,
) -> None:
	response = await client.post(
		"/api/v1/moderation/events",
		headers={"X-Service-Key": "test-b2c-service-key"},
		json=_body(moderation_event_data.product.id, "MODERATED"),
	)

	assert response.status_code == 401
	assert response.json()["code"] == "UNAUTHORIZED"


async def test_blocked_without_reason_returns_flat_400(
	client: AsyncClient,
	moderation_event_data: ModerationEventData,
) -> None:
	body = _body(moderation_event_data.product.id, "BLOCKED")
	body.pop("blocking_reason_id")

	response = await _post(client, body)

	assert response.status_code == 400
	assert set(response.json()) == {"code", "message"}
	assert response.json()["code"] == "VALIDATION_ERROR"
