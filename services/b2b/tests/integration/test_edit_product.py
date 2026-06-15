import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.outbox import OutboxEvent, OutboxEventStatus
from tests.integration.conftest import EditProductData, auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _outbox_events_for_product(
	db: AsyncSession, product_id: uuid.UUID
) -> list[OutboxEvent]:
	result = await db.execute(
		select(OutboxEvent).where(
			OutboxEvent.payload["payload"]["product_id"].astext == str(product_id)
		)
	)
	return list(result.scalars().all())


async def test_edit_moderated_product_returns_to_on_moderation(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	data = edit_product_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.patch(
		f"/api/v1/products/{data.moderated_product.id}",
		headers=headers,
		json={"title": "Updated moderated title"},
	)
	assert response.status_code == 200
	body = response.json()
	assert body["status"] == "ON_MODERATION"
	assert body["title"] == "Updated moderated title"

	events = await _outbox_events_for_product(db_session, data.moderated_product.id)
	assert len(events) == 1
	assert events[0].event_type == "PRODUCT_EDITED"
	assert set(events[0].payload) == {
		"event_type",
		"idempotency_key",
		"occurred_at",
		"payload",
	}
	assert events[0].payload["event_type"] == "PRODUCT_EDITED"
	assert events[0].payload["occurred_at"].endswith("Z")
	assert events[0].payload["payload"]["product_id"] == str(data.moderated_product.id)
	assert events[0].payload["payload"]["seller_id"] == str(data.owner.id)
	json_before = events[0].payload["payload"]["json_before"]
	json_after = events[0].payload["payload"]["json_after"]
	assert json_before["title"] != "Updated moderated title"
	assert json_before["status"] == "MODERATED"
	assert json_after["title"] == "Updated moderated title"
	assert json_after["status"] == "ON_MODERATION"
	assert uuid.UUID(events[0].payload["idempotency_key"]) == events[0].idempotency_key
	assert events[0].status == OutboxEventStatus.PENDING


async def test_edit_blocked_product_returns_to_on_moderation(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	data = edit_product_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.patch(
		f"/api/v1/products/{data.blocked_product.id}",
		headers=headers,
		json={"description": "Fixed description after block"},
	)
	assert response.status_code == 200
	assert response.json()["status"] == "ON_MODERATION"

	events = await _outbox_events_for_product(db_session, data.blocked_product.id)
	assert len(events) == 1
	assert events[0].payload["event_type"] == "PRODUCT_EDITED"
	assert events[0].payload["payload"]["seller_id"] == str(data.owner.id)
	json_before = events[0].payload["payload"]["json_before"]
	json_after = events[0].payload["payload"]["json_after"]
	assert json_before["description"] != "Fixed description after block"
	assert json_before["status"] == "BLOCKED"
	assert json_after["description"] == "Fixed description after block"
	assert json_after["status"] == "ON_MODERATION"
	assert events[0].status == OutboxEventStatus.PENDING


async def test_reserves_preserved_after_sku_edit(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	data = edit_product_data
	headers = await auth_headers(data.owner.id, db_session)
	initial_reserved = data.reserved_sku.reserved_quantity
	assert initial_reserved == 5

	response = await client.patch(
		f"/api/v1/skus/{data.reserved_sku.id}",
		headers=headers,
		json={
			"name": "Updated SKU with reserves",
			"price": 999,
			"reserved_quantity": 0,
		},
	)
	assert response.status_code == 200
	body = response.json()
	assert body["reserved_quantity"] == initial_reserved
	assert body["name"] == "Updated SKU with reserves"
	assert body["price"] == 999
	await db_session.refresh(data.reserved_sku)
	assert data.reserved_sku.reserved_quantity == initial_reserved

	product_response = await client.get(
		f"/api/v1/products/{data.moderated_product.id}",
		headers=headers,
	)
	assert product_response.status_code == 200
	assert product_response.json()["status"] == "ON_MODERATION"

	events = await _outbox_events_for_product(db_session, data.moderated_product.id)
	assert len(events) == 1
	assert events[0].payload["event_type"] == "PRODUCT_EDITED"
	json_before = events[0].payload["payload"]["json_before"]
	json_after = events[0].payload["payload"]["json_after"]
	before_sku = next(
		sku for sku in json_before["skus"] if sku["id"] == str(data.reserved_sku.id)
	)
	after_sku = next(
		sku for sku in json_after["skus"] if sku["id"] == str(data.reserved_sku.id)
	)
	assert before_sku["name"] != "Updated SKU with reserves"
	assert before_sku["price"] != 999
	assert before_sku["reserved_quantity"] == initial_reserved
	assert after_sku["name"] == "Updated SKU with reserves"
	assert after_sku["price"] == 999
	assert after_sku["reserved_quantity"] == initial_reserved
	assert json_before["status"] == "MODERATED"
	assert json_after["status"] == "ON_MODERATION"


async def test_nested_product_skus_route_returns_owned_skus(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	data = edit_product_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.get(
		f"/api/v1/products/{data.moderated_product.id}/skus",
		headers=headers,
	)

	assert response.status_code == 200
	assert {item["id"] for item in response.json()} == {str(data.moderated_sku.id)}


async def test_edit_hard_blocked_returns_403(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	data = edit_product_data
	headers = await auth_headers(data.owner.id, db_session)

	product_response = await client.patch(
		f"/api/v1/products/{data.hard_blocked_product.id}",
		headers=headers,
		json={"title": "Should not apply"},
	)
	assert product_response.status_code == 403
	assert product_response.json()["code"] == "FORBIDDEN"
	assert set(product_response.json()) == {"code", "message"}

	sku_response = await client.patch(
		f"/api/v1/skus/{data.hard_blocked_sku.id}",
		headers=headers,
		json={"name": "Should not apply"},
	)
	assert sku_response.status_code == 403
	assert sku_response.json()["code"] == "FORBIDDEN"
	assert set(sku_response.json()) == {"code", "message"}


async def test_edit_others_product_returns_403(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	data = edit_product_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.patch(
		f"/api/v1/products/{data.other_seller_product.id}",
		headers=headers,
		json={"title": "Stolen edit attempt"},
	)
	assert response.status_code == 403
	assert response.json()["code"] == "NOT_OWNER"
	assert set(response.json()) == {"code", "message"}

	sku_response = await client.patch(
		f"/api/v1/skus/{data.other_seller_sku.id}",
		headers=headers,
		json={"name": "Stolen SKU edit"},
	)
	assert sku_response.status_code == 403
	assert sku_response.json()["code"] == "NOT_OWNER"
	assert set(sku_response.json()) == {"code", "message"}


async def test_product_characteristics_replaced_on_edit(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	data = edit_product_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.patch(
		f"/api/v1/products/{data.moderated_product.id}",
		headers=headers,
		json={
			"characteristics": [
				{"name": "Материал", "value": "Сталь"},
				{"name": "Цвет", "value": "Чёрный"},
			]
		},
	)
	assert response.status_code == 200

	product_response = await client.get(
		f"/api/v1/products/{data.moderated_product.id}",
		headers=headers,
	)
	assert product_response.status_code == 200
	characteristics = product_response.json()["characteristics"]
	assert {(item["name"], item["value"]) for item in characteristics} == {
		("Материал", "Сталь"),
		("Цвет", "Чёрный"),
	}


async def test_sku_characteristics_replaced_on_edit(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	data = edit_product_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.patch(
		f"/api/v1/skus/{data.moderated_sku.id}",
		headers=headers,
		json={"characteristics": [{"name": "Размер", "value": "XL"}]},
	)
	assert response.status_code == 200
	assert [
		(item["name"], item["value"]) for item in response.json()["characteristics"]
	] == [("Размер", "XL")]


async def test_edit_product_with_invalid_category_returns_400(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	data = edit_product_data
	headers = await auth_headers(data.owner.id, db_session)

	response = await client.patch(
		f"/api/v1/products/{data.moderated_product.id}",
		headers=headers,
		json={"category_id": str(uuid.uuid4())},
	)
	assert response.status_code == 400
	assert response.json()["code"] == "INVALID_CATEGORY"
	assert set(response.json()) == {"code", "message"}

	events = await _outbox_events_for_product(db_session, data.moderated_product.id)
	assert events == []
