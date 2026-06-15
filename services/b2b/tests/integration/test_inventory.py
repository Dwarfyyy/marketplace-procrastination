import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.outbox import OutboxEvent
from tests.integration.conftest import (
	PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
	InventoryData,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _reserve_payload(
	idempotency_key: uuid.UUID,
	items: list[tuple[uuid.UUID, int]],
	order_id: uuid.UUID | None = None,
) -> dict:
	return {
		"idempotency_key": str(idempotency_key),
		"order_id": str(order_id or uuid.uuid4()),
		"items": [
			{"sku_id": str(sku_id), "quantity": quantity}
			for sku_id, quantity in items
		],
	}


def _unreserve_payload(
	order_id: uuid.UUID,
	items: list[tuple[uuid.UUID, int]],
) -> dict:
	return {
		"order_id": str(order_id),
		"items": [
			{"sku_id": str(sku_id), "quantity": quantity}
			for sku_id, quantity in items
		],
	}


async def test_reserve_all_skus_succeeds(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	first, second = inventory_data.skus
	order_id = uuid.uuid4()
	response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_reserve_payload(
			uuid.uuid4(), [(first.id, 3), (second.id, 1)], order_id
		),
	)

	assert response.status_code == 200
	assert response.json()["status"] == "RESERVED"
	assert response.json()["order_id"] == str(order_id)
	assert response.json()["reserved_at"]
	await db_session.refresh(first)
	await db_session.refresh(second)
	assert (first.active_quantity, first.reserved_quantity) == (7, 3)
	assert (second.active_quantity, second.reserved_quantity) == (1, 1)
	assert first.active_quantity + first.reserved_quantity == first.stock_quantity
	assert second.active_quantity + second.reserved_quantity == second.stock_quantity


async def test_partial_insufficient_stock_returns_409_all_rollback(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	first, second = inventory_data.skus
	response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_reserve_payload(uuid.uuid4(), [(first.id, 3), (second.id, 3)]),
	)

	assert response.status_code == 409
	assert response.json()["code"] == "INVENTORY_CONFLICT"
	await db_session.refresh(first)
	await db_session.refresh(second)
	assert (first.active_quantity, first.reserved_quantity) == (10, 0)
	assert (second.active_quantity, second.reserved_quantity) == (2, 0)


async def test_idempotent_reserve_returns_200_without_double_deduction(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	sku = inventory_data.skus[0]
	key = uuid.uuid4()
	payload = _reserve_payload(key, [(sku.id, 4)])

	first_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=payload,
	)
	second_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=payload,
	)

	assert first_response.status_code == 200
	assert second_response.status_code == 200
	await db_session.refresh(sku)
	assert (sku.active_quantity, sku.reserved_quantity) == (6, 4)


async def test_idempotent_reserve_returns_original_result_after_unreserve(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	sku = inventory_data.skus[0]
	reserve_key = uuid.uuid4()
	order_id = uuid.uuid4()
	reserve_payload = _reserve_payload(reserve_key, [(sku.id, 4)], order_id)

	first_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=reserve_payload,
	)
	unreserve_response = await client.post(
		"/api/v1/inventory/unreserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_unreserve_payload(order_id, [(sku.id, 4)]),
	)
	retry_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=reserve_payload,
	)

	assert first_response.status_code == 200
	assert unreserve_response.status_code == 200
	assert retry_response.status_code == 200
	assert retry_response.json() == first_response.json()
	await db_session.refresh(sku)
	assert (sku.active_quantity, sku.reserved_quantity) == (10, 0)


async def test_reused_idempotency_key_with_different_payload_returns_409(
	client: AsyncClient,
	inventory_data: InventoryData,
) -> None:
	first, second = inventory_data.skus
	key = uuid.uuid4()
	order_id = uuid.uuid4()
	first_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_reserve_payload(key, [(first.id, 1)], order_id),
	)
	conflict_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_reserve_payload(key, [(second.id, 1)], order_id),
	)

	assert first_response.status_code == 200
	assert conflict_response.status_code == 409
	assert conflict_response.json()["code"] == "INVENTORY_CONFLICT"


async def test_sku_out_of_stock_event_emitted(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	sku = inventory_data.skus[1]
	key = uuid.uuid4()
	payload = _reserve_payload(key, [(sku.id, 2)])
	first_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=payload,
	)
	retry_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=payload,
	)

	assert first_response.status_code == 200
	assert retry_response.status_code == 200
	result = await db_session.execute(
		select(OutboxEvent).where(OutboxEvent.event_type == "SKU_OUT_OF_STOCK")
	)
	event = result.scalar_one()
	assert event.routing_key == "b2c.sku.out_of_stock"
	assert event.payload["payload"]["sku_id"] == str(sku.id)
	assert event.payload["payload"]["available_quantity"] == 0


async def test_unreserve_restores_quantities(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	sku = inventory_data.skus[0]
	order_id = uuid.uuid4()
	reserve_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_reserve_payload(uuid.uuid4(), [(sku.id, 5)], order_id),
	)
	assert reserve_response.status_code == 200

	unreserve_response = await client.post(
		"/api/v1/inventory/unreserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_unreserve_payload(order_id, [(sku.id, 5)]),
	)

	assert unreserve_response.status_code == 200
	assert unreserve_response.json()["status"] == "UNRESERVED"
	assert unreserve_response.json()["order_id"] == str(order_id)
	assert unreserve_response.json()["processed_at"]
	await db_session.refresh(sku)
	assert (sku.active_quantity, sku.reserved_quantity) == (10, 0)
	assert sku.active_quantity + sku.reserved_quantity == sku.stock_quantity


async def test_idempotent_unreserve_returns_200_without_double_restore(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	sku = inventory_data.skus[0]
	order_id = uuid.uuid4()
	reserve_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_reserve_payload(uuid.uuid4(), [(sku.id, 5)], order_id),
	)
	payload = _unreserve_payload(order_id, [(sku.id, 5)])
	first_response = await client.post(
		"/api/v1/inventory/unreserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=payload,
	)
	second_response = await client.post(
		"/api/v1/inventory/unreserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=payload,
	)

	assert reserve_response.status_code == 200
	assert first_response.status_code == 200
	assert second_response.status_code == 200
	assert second_response.json() == first_response.json()
	await db_session.refresh(sku)
	assert (sku.active_quantity, sku.reserved_quantity) == (10, 0)


async def test_partial_unreserve_conflict_returns_409_all_rollback(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	first, second = inventory_data.skus
	order_id = uuid.uuid4()
	reserve_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_reserve_payload(
			uuid.uuid4(), [(first.id, 3), (second.id, 1)], order_id
		),
	)
	response = await client.post(
		"/api/v1/inventory/unreserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_unreserve_payload(order_id, [(first.id, 2), (second.id, 2)]),
	)

	assert reserve_response.status_code == 200
	assert response.status_code == 409
	assert response.json()["code"] == "INVENTORY_CONFLICT"
	await db_session.refresh(first)
	await db_session.refresh(second)
	assert (first.active_quantity, first.reserved_quantity) == (7, 3)
	assert (second.active_quantity, second.reserved_quantity) == (1, 1)


async def test_reused_unreserve_order_id_with_different_payload_returns_409(
	client: AsyncClient,
	inventory_data: InventoryData,
) -> None:
	first, second = inventory_data.skus
	order_id = uuid.uuid4()
	reserve_response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_reserve_payload(
			uuid.uuid4(), [(first.id, 1), (second.id, 1)], order_id
		),
	)
	first_response = await client.post(
		"/api/v1/inventory/unreserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_unreserve_payload(order_id, [(first.id, 1)]),
	)
	conflict_response = await client.post(
		"/api/v1/inventory/unreserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_unreserve_payload(order_id, [(second.id, 1)]),
	)

	assert reserve_response.status_code == 200
	assert first_response.status_code == 200
	assert conflict_response.status_code == 409
	assert conflict_response.json()["code"] == "INVENTORY_CONFLICT"


async def test_reserve_missing_service_key_returns_401(client: AsyncClient) -> None:
	response = await client.post(
		"/api/v1/inventory/reserve",
		json=_reserve_payload(uuid.uuid4(), [(uuid.uuid4(), 1)]),
	)

	assert response.status_code == 401
	assert response.json()["code"] == "UNAUTHORIZED"


async def test_empty_items_returns_flat_validation_error(client: AsyncClient) -> None:
	response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_reserve_payload(uuid.uuid4(), []),
	)

	assert response.status_code == 400
	assert set(response.json()) == {"code", "message"}
	assert response.json()["code"] == "VALIDATION_ERROR"
