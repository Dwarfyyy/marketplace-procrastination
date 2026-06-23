import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.cart.item import CartItem
from database.models.orders.order_item import OrderItem
from tests.integration.events.conftest import (
	PRODUCT_EVENT_SERVICE_KEY_HEADERS,
	ProductEventData,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _body(
	event_type: str,
	sku_ids: list[uuid.UUID],
	product_id: uuid.UUID,
	*,
	idempotency_key: uuid.UUID | None = None,
	hard_block: bool = False,
) -> dict:
	return {
		"event_type": event_type,
		"idempotency_key": str(idempotency_key or uuid.uuid4()),
		"occurred_at": datetime.now(timezone.utc).isoformat(),
		"payload": {
			"product_id": str(product_id),
			"sku_ids": [str(sku_id) for sku_id in sku_ids],
			"hard_block": hard_block,
		},
	}


async def _post(client: AsyncClient, body: dict) -> object:
	return await client.post(
		"/api/v1/b2b/events",
		headers=PRODUCT_EVENT_SERVICE_KEY_HEADERS,
		json=body,
	)


async def _reload_cart_items(
	db: AsyncSession, cart_item_ids: list[uuid.UUID]
) -> list[CartItem]:
	result = await db.execute(
		select(CartItem)
		.where(CartItem.id.in_(cart_item_ids))
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def _reload_order_items(
	db: AsyncSession, order_item_ids: list[uuid.UUID]
) -> list[OrderItem]:
	result = await db.execute(
		select(OrderItem)
		.where(OrderItem.id.in_(order_item_ids))
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def test_product_blocked_marks_cart_items_unavailable(
	client: AsyncClient,
	product_event_data: ProductEventData,
	db_session: AsyncSession,
) -> None:
	sku_ids = [sku.id for sku in product_event_data.skus]
	response = await _post(
		client,
		_body("PRODUCT_BLOCKED", sku_ids, product_event_data.product.id),
	)

	assert response.status_code == 202
	body = response.json()
	assert body["processed"] is True
	assert body["updated_count"] == len(product_event_data.cart_items)

	cart_items = await _reload_cart_items(
		db_session, [item.id for item in product_event_data.cart_items]
	)
	assert len(cart_items) == len(product_event_data.cart_items)
	for cart_item in cart_items:
		assert cart_item.unavailable_reason == "PRODUCT_BLOCKED"


async def test_orders_not_affected_by_product_blocked(
	client: AsyncClient,
	product_event_data: ProductEventData,
	db_session: AsyncSession,
) -> None:
	sku_ids = [sku.id for sku in product_event_data.skus]
	original_prices = {
		item.id: (item.unit_price, item.line_total)
		for item in product_event_data.order_items
	}

	response = await _post(
		client,
		_body("PRODUCT_BLOCKED", sku_ids, product_event_data.product.id),
	)
	assert response.status_code == 202

	order_items = await _reload_order_items(
		db_session, [item.id for item in product_event_data.order_items]
	)
	assert len(order_items) == len(product_event_data.order_items)
	for order_item in order_items:
		unit_price, line_total = original_prices[order_item.id]
		assert order_item.unit_price == unit_price
		assert order_item.line_total == line_total


async def test_idempotent_event_no_side_effects(
	client: AsyncClient,
	product_event_data: ProductEventData,
	db_session: AsyncSession,
) -> None:
	key = uuid.uuid4()
	sku_ids = [sku.id for sku in product_event_data.skus]
	body = _body(
		"PRODUCT_BLOCKED", sku_ids, product_event_data.product.id, idempotency_key=key
	)

	first = await _post(client, body)
	second = await _post(client, body)

	assert first.status_code == 202
	assert first.json()["processed"] is True
	assert first.json()["updated_count"] == len(product_event_data.cart_items)

	assert second.status_code == 202
	assert second.json()["processed"] is False
	assert second.json()["updated_count"] == 0

	cart_items = await _reload_cart_items(
		db_session, [item.id for item in product_event_data.cart_items]
	)
	for cart_item in cart_items:
		assert cart_item.unavailable_reason == "PRODUCT_BLOCKED"


async def test_missing_service_key_returns_401(
	client: AsyncClient,
	product_event_data: ProductEventData,
) -> None:
	sku_ids = [sku.id for sku in product_event_data.skus]
	response = await client.post(
		"/api/v1/b2b/events",
		json=_body("PRODUCT_BLOCKED", sku_ids, product_event_data.product.id),
	)

	assert response.status_code == 401
	assert set(response.json()) == {"code", "message"}
	assert response.json()["code"] == "UNAUTHORIZED"


async def test_product_blocked_without_sku_ids_resolves_via_catalog(
	client: AsyncClient,
	product_event_data: ProductEventData,
	db_session: AsyncSession,
) -> None:
	# Spec-compliant payload: product-level event carries only product_id.
	response = await _post(
		client,
		_body("PRODUCT_BLOCKED", [], product_event_data.product.id),
	)

	assert response.status_code == 202
	assert response.json()["processed"] is True
	assert response.json()["updated_count"] == len(product_event_data.cart_items)

	cart_items = await _reload_cart_items(
		db_session, [item.id for item in product_event_data.cart_items]
	)
	for cart_item in cart_items:
		assert cart_item.unavailable_reason == "PRODUCT_BLOCKED"


async def test_sku_back_in_stock_clears_out_of_stock(
	client: AsyncClient,
	product_event_data: ProductEventData,
	db_session: AsyncSession,
) -> None:
	sku_ids = [sku.id for sku in product_event_data.skus]
	out = await _post(client, _body("SKU_OUT_OF_STOCK", sku_ids, product_event_data.product.id))
	assert out.status_code == 202

	back = await _post(
		client, _body("SKU_BACK_IN_STOCK", sku_ids, product_event_data.product.id)
	)
	assert back.status_code == 202
	assert back.json()["updated_count"] == len(product_event_data.cart_items)

	cart_items = await _reload_cart_items(
		db_session, [item.id for item in product_event_data.cart_items]
	)
	for cart_item in cart_items:
		assert cart_item.unavailable_reason is None


async def test_price_changed_does_not_change_cart_availability(
	client: AsyncClient,
	product_event_data: ProductEventData,
	db_session: AsyncSession,
) -> None:
	sku_ids = [sku.id for sku in product_event_data.skus]
	response = await _post(
		client, _body("PRICE_CHANGED", sku_ids, product_event_data.product.id)
	)

	assert response.status_code == 202
	assert response.json()["processed"] is True
	assert response.json()["updated_count"] == 0

	cart_items = await _reload_cart_items(
		db_session, [item.id for item in product_event_data.cart_items]
	)
	for cart_item in cart_items:
		assert cart_item.unavailable_reason is None
