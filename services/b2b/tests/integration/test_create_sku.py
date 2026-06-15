import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.outbox import OutboxEvent, OutboxEventStatus
from tests.integration.conftest import (
	CategoryWithProductsData,
	EditProductData,
	auth_headers,
)

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


async def _create_sku(
	client: AsyncClient,
	headers: dict,
	product_id: str,
	with_images: bool = False,
) -> dict:
	body = {"product_id": product_id, "name": "Test SKU", "price": 100}
	if with_images:
		body["images"] = [{"url": "/s3/test-sku.jpg", "ordering": 0}]
	response = await client.post("/api/v1/skus", headers=headers, json=body)
	assert response.status_code == 201
	return response.json()


async def test_first_sku_transitions_product_to_on_moderation(
	client: AsyncClient,
	product_no_skus: CategoryWithProductsData,
	db_session: AsyncSession,
) -> None:
	product = product_no_skus.products[0]
	headers = await auth_headers(product.seller_id, db_session)

	sku = await _create_sku(client, headers, str(product.id), with_images=True)
	assert len(sku["images"]) == 1
	assert sku["images"][0]["url"] == "/s3/test-sku.jpg"

	product_response = await client.get(
		f"/api/v1/products/{product.id}",
		headers=headers,
	)
	assert product_response.status_code == 200
	assert product_response.json()["status"] == "ON_MODERATION"


async def test_first_sku_emits_created_event_to_moderation(
	client: AsyncClient,
	product_no_skus: CategoryWithProductsData,
	db_session: AsyncSession,
) -> None:
	product = product_no_skus.products[1]
	headers = await auth_headers(product.seller_id, db_session)

	await _create_sku(client, headers, str(product.id), with_images=True)

	events = await _outbox_events_for_product(db_session, product.id)
	assert len(events) == 1
	assert events[0].event_type == "PRODUCT_CREATED"
	assert events[0].routing_key == "moderation.product.created"
	assert events[0].payload["event_type"] == "PRODUCT_CREATED"
	assert events[0].payload["payload"]["product_id"] == str(product.id)
	assert events[0].payload["payload"]["seller_id"] == str(product.seller_id)
	json_after = events[0].payload["payload"]["json_after"]
	assert json_after["id"] == str(product.id)
	assert json_after["status"] == "ON_MODERATION"
	assert len(json_after["skus"]) == 1
	assert json_after["skus"][0]["images"] == [
		{"url": "/s3/test-sku.jpg", "ordering": 0}
	]
	assert uuid.UUID(events[0].payload["idempotency_key"]) == events[0].idempotency_key
	assert events[0].payload["occurred_at"].endswith("Z")
	assert events[0].status == OutboxEventStatus.PENDING


async def test_second_sku_no_state_change(
	client: AsyncClient,
	product_on_moderation_with_one_sku: CategoryWithProductsData,
	db_session: AsyncSession,
) -> None:
	product = product_on_moderation_with_one_sku.products[0]
	headers = await auth_headers(product.seller_id, db_session)

	await _create_sku(client, headers, str(product.id))

	product_response = await client.get(
		f"/api/v1/products/{product.id}",
		headers=headers,
	)
	assert product_response.status_code == 200
	assert product_response.json()["status"] == "ON_MODERATION"

	events = await _outbox_events_for_product(db_session, product.id)
	assert events == []


async def test_subsequent_sku_on_moderated_product_returns_to_on_moderation(
	client: AsyncClient,
	edit_product_data: EditProductData,
	db_session: AsyncSession,
) -> None:
	product = edit_product_data.moderated_product
	headers = await auth_headers(edit_product_data.owner.id, db_session)

	await _create_sku(client, headers, str(product.id))

	product_response = await client.get(
		f"/api/v1/products/{product.id}",
		headers=headers,
	)
	assert product_response.status_code == 200
	assert product_response.json()["status"] == "ON_MODERATION"

	events = await _outbox_events_for_product(db_session, product.id)
	assert len(events) == 1
	assert events[0].event_type == "PRODUCT_EDITED"
	assert events[0].routing_key == "moderation.product.edited"
	assert events[0].payload["event_type"] == "PRODUCT_EDITED"
	assert events[0].payload["payload"]["json_before"]["status"] == "MODERATED"
	assert events[0].payload["payload"]["json_after"]["status"] == "ON_MODERATION"
	assert len(events[0].payload["payload"]["json_after"]["skus"]) == (
		len(events[0].payload["payload"]["json_before"]["skus"]) + 1
	)


async def test_subsequent_sku_on_blocked_product_returns_to_on_moderation(
	client: AsyncClient,
	blocked_product: CategoryWithProductsData,
	db_session: AsyncSession,
) -> None:
	product = blocked_product.products[0]
	headers = await auth_headers(product.seller_id, db_session)

	await _create_sku(client, headers, str(product.id))

	product_response = await client.get(
		f"/api/v1/products/{product.id}",
		headers=headers,
	)
	assert product_response.status_code == 200
	assert product_response.json()["status"] == "ON_MODERATION"

	events = await _outbox_events_for_product(db_session, product.id)
	assert len(events) == 1
	assert events[0].event_type == "PRODUCT_EDITED"
	assert events[0].payload["event_type"] == "PRODUCT_EDITED"
	assert events[0].payload["payload"]["json_before"]["status"] == "BLOCKED"
	assert events[0].payload["payload"]["json_after"]["status"] == "ON_MODERATION"


async def test_add_sku_to_hard_blocked_returns_403(
	client: AsyncClient,
	hard_blocked_product: CategoryWithProductsData,
	db_session: AsyncSession,
) -> None:
	product = hard_blocked_product.products[0]
	headers = await auth_headers(product.seller_id, db_session)

	response = await client.post(
		"/api/v1/skus",
		headers=headers,
		json={"product_id": str(product.id), "name": "Test SKU", "price": 100},
	)
	assert response.status_code == 403
	assert response.json()["code"] == "FORBIDDEN"
	assert set(response.json()) == {"code", "message"}


async def test_missing_image_returns_400(
	client: AsyncClient,
	product_no_skus: CategoryWithProductsData,
	db_session: AsyncSession,
) -> None:
	product = product_no_skus.products[2]
	headers = await auth_headers(product.seller_id, db_session)

	response = await client.post(
		"/api/v1/skus",
		headers=headers,
		json={"product_id": str(product.id), "name": "Test SKU", "price": 100},
	)
	assert response.status_code == 400
	assert response.json()["code"] == "INVALID_REQUEST"
	assert set(response.json()) == {"code", "message"}


async def test_missing_image_url_on_attach_returns_400(
	client: AsyncClient,
	category_with_products: CategoryWithProductsData,
	db_session: AsyncSession,
) -> None:
	product = category_with_products.products[0]
	headers = await auth_headers(product.seller_id, db_session)

	sku = await _create_sku(client, headers, str(product.id))

	response = await client.post(
		f"/api/v1/skus/{sku['id']}/images",
		headers=headers,
		json={"ordering": 0},
	)
	assert response.status_code == 400
	assert response.json()["code"] == "VALIDATION_ERROR"
	assert set(response.json()) == {"code", "message"}
