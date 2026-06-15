import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import (
	PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
	InventoryData,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _payload(order_id: uuid.UUID, items: list[tuple[uuid.UUID, int]]) -> dict:
	return {
		"order_id": str(order_id),
		"items": [
			{"sku_id": str(sku_id), "quantity": quantity} for sku_id, quantity in items
		],
	}


async def _reserve(client: AsyncClient, items: list[tuple[uuid.UUID, int]]) -> None:
	response = await client.post(
		"/api/v1/inventory/reserve",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json={
			"idempotency_key": str(uuid.uuid4()),
			"order_id": str(uuid.uuid4()),
			"items": [
				{"sku_id": str(sku_id), "quantity": quantity}
				for sku_id, quantity in items
			],
		},
	)
	assert response.status_code == 200


async def test_fulfill_decreases_reserved_quantity(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	sku = inventory_data.skus[0]
	await _reserve(client, [(sku.id, 5)])

	response = await client.post(
		"/api/v1/inventory/fulfill",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_payload(uuid.uuid4(), [(sku.id, 3)]),
	)

	assert response.status_code == 200
	assert set(response.json()) == {"order_id", "status", "processed_at"}
	assert response.json()["status"] == "FULFILLED"
	await db_session.refresh(sku)
	assert sku.reserved_quantity == 2


async def test_active_quantity_unchanged(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	sku = inventory_data.skus[0]
	await _reserve(client, [(sku.id, 4)])
	await db_session.refresh(sku)
	active_quantity = sku.active_quantity

	response = await client.post(
		"/api/v1/inventory/fulfill",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_payload(uuid.uuid4(), [(sku.id, 4)]),
	)

	assert response.status_code == 200
	await db_session.refresh(sku)
	assert sku.active_quantity == active_quantity
	assert sku.reserved_quantity == 0


async def test_idempotent_fulfill_no_double_deduction(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	sku = inventory_data.skus[0]
	await _reserve(client, [(sku.id, 5)])
	payload = _payload(uuid.uuid4(), [(sku.id, 3)])

	first_response = await client.post(
		"/api/v1/inventory/fulfill",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=payload,
	)
	second_response = await client.post(
		"/api/v1/inventory/fulfill",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=payload,
	)

	assert first_response.status_code == 200
	assert second_response.status_code == 200
	assert second_response.json() == first_response.json()
	await db_session.refresh(sku)
	assert sku.reserved_quantity == 2


async def test_missing_service_key_returns_401(client: AsyncClient) -> None:
	response = await client.post(
		"/api/v1/inventory/fulfill",
		json=_payload(uuid.uuid4(), [(uuid.uuid4(), 1)]),
	)

	assert response.status_code == 401
	assert response.json() == {
		"code": "UNAUTHORIZED",
		"message": "Invalid or missing service key",
	}


async def test_fulfill_insufficient_reserved_quantity_rolls_back_all(
	client: AsyncClient,
	inventory_data: InventoryData,
	db_session: AsyncSession,
) -> None:
	first, second = inventory_data.skus
	await _reserve(client, [(first.id, 3), (second.id, 1)])

	response = await client.post(
		"/api/v1/inventory/fulfill",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_payload(uuid.uuid4(), [(first.id, 2), (second.id, 2)]),
	)

	assert response.status_code == 409
	assert response.json()["code"] == "INVENTORY_CONFLICT"
	await db_session.refresh(first)
	await db_session.refresh(second)
	assert first.reserved_quantity == 3
	assert second.reserved_quantity == 1


async def test_fulfill_reused_order_id_with_different_payload_returns_409(
	client: AsyncClient,
	inventory_data: InventoryData,
) -> None:
	first, second = inventory_data.skus
	await _reserve(client, [(first.id, 1), (second.id, 1)])
	order_id = uuid.uuid4()
	first_response = await client.post(
		"/api/v1/inventory/fulfill",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_payload(order_id, [(first.id, 1)]),
	)
	conflict_response = await client.post(
		"/api/v1/inventory/fulfill",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_payload(order_id, [(second.id, 1)]),
	)

	assert first_response.status_code == 200
	assert conflict_response.status_code == 409
	assert conflict_response.json()["code"] == "INVENTORY_CONFLICT"


async def test_fulfill_empty_items_returns_flat_validation_error(
	client: AsyncClient,
) -> None:
	response = await client.post(
		"/api/v1/inventory/fulfill",
		headers=PUBLIC_CATALOG_SERVICE_KEY_HEADERS,
		json=_payload(uuid.uuid4(), []),
	)

	assert response.status_code == 400
	assert set(response.json()) == {"code", "message"}
	assert response.json()["code"] == "VALIDATION_ERROR"
