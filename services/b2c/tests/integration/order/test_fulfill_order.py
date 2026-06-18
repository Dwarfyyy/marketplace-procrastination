import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.catalog.variants import Sku
from database.models.orders.order import Order, OrderStatusEnum
from exceptions.order import B2BUnavailableError
from services import order_service
from tests.integration.events.conftest import PRODUCT_EVENT_SERVICE_KEY_HEADERS
from tests.integration.order.conftest import OrderData

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _post_delivered(client: AsyncClient, order_id: uuid.UUID) -> object:
	return await client.post(
		"/api/v1/events/order-delivered",
		json={"order_id": str(order_id)},
		headers=PRODUCT_EVENT_SERVICE_KEY_HEADERS,
	)


async def _reserved_quantities(
	db_session: AsyncSession, sku_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
	result = await db_session.execute(select(Sku).where(Sku.id.in_(sku_ids)))
	return {sku.id: sku.reserved_quantity for sku in result.scalars().all()}


async def test_delivered_status_triggers_fulfill_to_b2b(
	client: AsyncClient,
	db_session: AsyncSession,
	delivering_order_data: OrderData,
) -> None:
	order = delivering_order_data.order

	response = await _post_delivered(client, order.id)
	assert response.status_code == 200
	body = response.json()
	assert body["id"] == str(order.id)
	assert body["status"] == "DELIVERED"
	assert body["status_history"][-1]["status"] == "DELIVERED"

	await db_session.refresh(order)
	assert order.fulfilled_at is not None


async def test_fulfill_failure_retried_asynchronously(
	client: AsyncClient,
	db_session: AsyncSession,
	delivering_order_data: OrderData,
	monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture,
) -> None:
	order = delivering_order_data.order
	sku_ids = [sku.id for sku in delivering_order_data.skus]

	async def _raise_unavailable(*args, **kwargs):
		raise B2BUnavailableError()

	monkeypatch.setattr(
		"services.order_service.b2b_client.fulfill_inventory",
		_raise_unavailable,
	)

	with caplog.at_level("ERROR"):
		response = await _post_delivered(client, order.id)

	assert response.status_code == 200
	body = response.json()
	assert body["status"] == "DELIVERED"
	assert "Fulfill failed" in caplog.text

	reserved = await _reserved_quantities(db_session, sku_ids)
	for sku_id in sku_ids:
		assert reserved[sku_id] == 2

	result = await db_session.execute(select(Order).where(Order.id == order.id))
	refreshed = result.scalar_one()
	assert refreshed.status == OrderStatusEnum.DELIVERED
	assert refreshed.fulfilled_at is None

	monkeypatch.undo()
	fulfilled_count = await order_service.retry_pending_fulfillments(db_session)
	assert fulfilled_count == 1

	result = await db_session.execute(select(Order).where(Order.id == order.id))
	retried = result.scalar_one()
	assert retried.fulfilled_at is not None


async def test_repeated_fulfill_idempotent(
	client: AsyncClient,
	db_session: AsyncSession,
	delivering_order_data: OrderData,
) -> None:
	order = delivering_order_data.order

	first = await _post_delivered(client, order.id)
	assert first.status_code == 200

	await db_session.refresh(order)
	fulfilled_at_first = order.fulfilled_at
	assert fulfilled_at_first is not None

	second = await _post_delivered(client, order.id)
	assert second.status_code == 200
	body = second.json()
	assert body["status"] == "DELIVERED"

	await db_session.refresh(order)
	assert order.fulfilled_at == fulfilled_at_first


async def test_order_delivered_event_missing_service_key_returns_401(
	client: AsyncClient,
	delivering_order_data: OrderData,
) -> None:
	response = await client.post(
		"/api/v1/events/order-delivered",
		json={"order_id": str(delivering_order_data.order.id)},
	)
	assert response.status_code == 401


async def test_order_delivered_event_unknown_order_returns_404(
	client: AsyncClient,
) -> None:
	response = await _post_delivered(client, uuid.uuid4())
	assert response.status_code == 404
	body = response.json()
	assert body["code"] == "NOT_FOUND"
