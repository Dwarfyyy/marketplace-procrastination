import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from database.models.orders.order import OrderStatusEnum
from tests.integration.order.conftest import OrderData
from tests.integration.cart.conftest import auth_headers
import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_order_detail_shows_fixed_prices(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
) -> None:
	ordered_sku = order_data.skus[0]
	old_price = ordered_sku.price
	ordered_sku.price *= 2
	await db_session.commit()
	response = await client.get(
		f"/api/v1/orders/{order_data.order.id}",
		headers=await auth_headers(order_data.order.buyer_id, db_session),
	)

	assert response.status_code == 200
	body = response.json()
	sku_response = next(
		item for item in body["items"] if item["sku_id"] == str(ordered_sku.id)
	)
	assert sku_response["unit_price"] == old_price


async def test_other_user_order_returns_404_not_403(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
) -> None:
	response = await client.get(
		f"/api/v1/orders/{order_data.order.id}",
		headers=await auth_headers(uuid.uuid4(), db_session),
	)
	assert response.status_code != 403
	assert response.status_code == 404
	body = response.json()
	assert body["code"] == "NOT_FOUND"
	assert body["message"] == "Order not found"


async def test_order_detail_not_authorized_returns_401(
	client: AsyncClient,
	order_data: OrderData,
) -> None:
	response = await client.get(
		f"/api/v1/orders/{order_data.order.id}",
	)
	assert response.status_code == 401


async def test_orders_list_returns_own_orders_paginated(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
) -> None:
	response = await client.get(
		"/api/v1/orders",
		params={"limit": 1, "offset": 0},
		headers=await auth_headers(order_data.order.buyer_id, db_session),
	)
	assert response.status_code == 200
	body = response.json()
	assert body["limit"] == 1
	assert body["offset"] == 0
	assert len(body["items"]) == 1
	assert body["items"][0]["id"] == str(order_data.order.id)


async def test_orders_list_empty_with_status_filter(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
) -> None:
	response = await client.get(
		"/api/v1/orders",
		params={
			"limit": 1,
			"offset": 0,
			"status": OrderStatusEnum.CANCEL_PENDING.value,
		},
		headers=await auth_headers(order_data.order.buyer_id, db_session),
	)
	assert response.status_code == 200
	body = response.json()
	assert body["items"] == []
	assert body["total_count"] == 0


async def test_orders_list_not_authorized_returns_401(
	client: AsyncClient,
) -> None:
	response = await client.get(
		"/api/v1/orders",
		params={"limit": 1, "offset": 0},
	)
	assert response.status_code == 401
