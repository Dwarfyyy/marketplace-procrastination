import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.outbox import OutboxEvent, OutboxEventStatus
from tests.integration.conftest import DeleteProductData, auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _events_for_product(
	db: AsyncSession, product_id: uuid.UUID
) -> list[OutboxEvent]:
	result = await db.execute(
		select(OutboxEvent).where(
			OutboxEvent.payload["payload"]["product_id"].astext == str(product_id)
		)
	)
	return list(result.scalars().all())


async def _delete_owned_product(
	client: AsyncClient,
	db: AsyncSession,
	data: DeleteProductData,
) -> None:
	headers = await auth_headers(data.owner.id, db)
	response = await client.delete(
		f"/api/v1/products/{data.product.id}",
		headers=headers,
	)
	assert response.status_code == 200
	assert response.json() == {"message": "Product deleted successfully"}


async def test_delete_sets_deleted_true(
	client: AsyncClient,
	delete_product_data: DeleteProductData,
	db_session: AsyncSession,
) -> None:
	await _delete_owned_product(client, db_session, delete_product_data)

	await db_session.refresh(delete_product_data.product)
	assert delete_product_data.product.deleted is True
	assert delete_product_data.product.status.value == "MODERATED"


async def test_delete_emits_event_to_moderation(
	client: AsyncClient,
	delete_product_data: DeleteProductData,
	db_session: AsyncSession,
) -> None:
	await _delete_owned_product(client, db_session, delete_product_data)

	events = await _events_for_product(db_session, delete_product_data.product.id)
	moderation_events = [
		event for event in events if event.routing_key == "moderation.product.deleted"
	]
	assert len(moderation_events) == 1
	event = moderation_events[0]
	assert event.event_type == "PRODUCT_DELETED"
	assert event.payload["event_type"] == "PRODUCT_DELETED"
	assert event.payload["payload"]["seller_id"] == str(delete_product_data.owner.id)
	assert event.status == OutboxEventStatus.PENDING


async def test_delete_emits_product_deleted_to_b2c(
	client: AsyncClient,
	delete_product_data: DeleteProductData,
	db_session: AsyncSession,
) -> None:
	await _delete_owned_product(client, db_session, delete_product_data)

	events = await _events_for_product(db_session, delete_product_data.product.id)
	b2c_events = [
		event for event in events if event.routing_key == "b2c.product.deleted"
	]
	assert len(b2c_events) == 1
	event = b2c_events[0]
	assert event.event_type == "PRODUCT_DELETED"
	assert set(event.payload["payload"]["sku_ids"]) == {
		str(sku.id) for sku in delete_product_data.skus
	}
	assert event.status == OutboxEventStatus.PENDING


async def test_delete_already_deleted_returns_400(
	client: AsyncClient,
	delete_product_data: DeleteProductData,
	db_session: AsyncSession,
) -> None:
	await _delete_owned_product(client, db_session, delete_product_data)
	headers = await auth_headers(delete_product_data.owner.id, db_session)

	response = await client.delete(
		f"/api/v1/products/{delete_product_data.product.id}",
		headers=headers,
	)

	assert response.status_code == 400
	assert response.json()["code"] == "ALREADY_DELETED"
	assert set(response.json()) == {"code", "message"}
	assert (
		len(await _events_for_product(db_session, delete_product_data.product.id)) == 2
	)


async def test_deleted_product_visible_in_seller_list(
	client: AsyncClient,
	delete_product_data: DeleteProductData,
	db_session: AsyncSession,
) -> None:
	await _delete_owned_product(client, db_session, delete_product_data)
	headers = await auth_headers(delete_product_data.owner.id, db_session)

	response = await client.get("/api/v1/products/", headers=headers)

	assert response.status_code == 200
	deleted = next(
		product
		for product in response.json()["items"]
		if product["id"] == str(delete_product_data.product.id)
	)
	assert deleted["deleted"] is True


async def test_delete_others_product_returns_403(
	client: AsyncClient,
	delete_product_data: DeleteProductData,
	db_session: AsyncSession,
) -> None:
	headers = await auth_headers(delete_product_data.owner.id, db_session)

	response = await client.delete(
		f"/api/v1/products/{delete_product_data.other_seller_product.id}",
		headers=headers,
	)

	assert response.status_code == 403
	assert response.json()["code"] == "NOT_OWNER"
	assert set(response.json()) == {"code", "message"}
