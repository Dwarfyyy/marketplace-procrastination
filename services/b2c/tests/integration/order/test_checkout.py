import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import pytest
from tests.integration.cart.conftest import auth_headers
from tests.integration.order.conftest import OrderData
import uuid
import hashlib
import json

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_checkout_creates_paid_order_with_fixed_prices(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
) -> None:
	response = await client.post(
		"/api/v1/orders",
		headers={
			**await auth_headers(order_data.order.buyer_id, db_session),
			"Idempotency-Key": str(uuid.uuid4()),
		},
		json={
			"address_id": str(order_data.address.id),
			"payment_method_id": str(order_data.payment_method.id),
			"comment": "Test comment",
		},
	)
	assert response.status_code == 201
	body = response.json()
	assert body["status"] == "PAID"
	assert body["buyer_id"] == str(order_data.order.buyer_id)
	expected_total = sum(
		cart_item.quantity
		* next(sku.price for sku in order_data.skus if sku.id == cart_item.sku_id)
		for cart_item in order_data.cart_items
	)
	assert body["subtotal"] == expected_total
	assert body["delivery_cost"] == 0
	assert body["total"] == expected_total
	assert len(body["items"]) == len(order_data.cart_items)
	for item in body["items"]:
		sku_id = item["sku_id"]
		assert item["product_id"] == str(order_data.product.id)
		assert item["quantity"] == next(
			cart_item.quantity
			for cart_item in order_data.cart_items
			if cart_item.sku_id == uuid.UUID(sku_id)
		)
		assert item["unit_price"] == next(
			sku.price for sku in order_data.skus if sku.id == uuid.UUID(sku_id)
		)
		assert item["line_total"] == next(
			cart_item.unit_price_at_add * cart_item.quantity
			for cart_item in order_data.cart_items
			if cart_item.sku_id == uuid.UUID(sku_id)
		)


async def test_partial_reserve_failure_returns_409(
	client: AsyncClient,
	db_session: AsyncSession,
	partial_reserve_failure_data: OrderData,
) -> None:
	response = await client.post(
		"/api/v1/orders",
		headers={
			"Idempotency-Key": str(uuid.uuid4()),
			**await auth_headers(
				partial_reserve_failure_data.order.buyer_id, db_session
			),
		},
		json={
			"address_id": str(partial_reserve_failure_data.address.id),
			"payment_method_id": str(partial_reserve_failure_data.payment_method.id),
		},
	)
	assert response.status_code == 409
	body = response.json()
	assert body["code"] == "RESERVE_FAILED"
	assert body["message"] == "Partial reserve failed"
	assert body["details"] == [
		{
			"sku_id": str(partial_reserve_failure_data.skus[0].id),
			"requested": 2,
			"reason": "PRODUCT_BLOCKED",
		}
	]


async def test_cart_validation_error_returns_422(
	client: AsyncClient,
	db_session: AsyncSession,
	cart_validation_error_data: OrderData,
) -> None:
	response = await client.post(
		"/api/v1/orders",
		headers={
			"Idempotency-Key": str(uuid.uuid4()),
			**await auth_headers(cart_validation_error_data.order.buyer_id, db_session),
		},
		json={
			"address_id": str(cart_validation_error_data.address.id),
			"payment_method_id": str(cart_validation_error_data.payment_method.id),
		},
	)
	assert response.status_code == 422


async def test_idempotency_returns_existing_order(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
) -> None:
	payload = {
		"address_id": str(order_data.address.id),
		"payment_method_id": str(order_data.payment_method.id),
		"comment": None,
		"items_snapshot": None,
	}
	order_data.order.idempotency_request_hash = hashlib.sha256(
		json.dumps(
			payload,
			sort_keys=True,
			separators=(",", ":"),
			ensure_ascii=False,
		).encode("utf-8")
	).hexdigest()
	await db_session.commit()

	response = await client.post(
		"/api/v1/orders",
		headers={
			"Idempotency-Key": str(order_data.order.idempotency_key),
			**await auth_headers(order_data.order.buyer_id, db_session),
		},
		json=payload,
	)
	assert response.status_code == 201
	body = response.json()
	assert body["id"] == str(order_data.order.id)
	assert body["status"] == order_data.order.status.value
	assert body["buyer_id"] == str(order_data.order.buyer_id)


async def test_b2b_unavailable_returns_503(
	client: AsyncClient,
	db_session: AsyncSession,
	order_data: OrderData,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	async def _raise_unavailable(*args, **kwargs):
		raise httpx.ConnectError("Connection refused")

	monkeypatch.setattr(
		"clients.b2b_client.reserve_inventory",
		_raise_unavailable,
	)

	response = await client.post(
		"/api/v1/orders",
		headers={
			**await auth_headers(order_data.order.buyer_id, db_session),
			"Idempotency-Key": str(uuid.uuid4()),
		},
		json={
			"address_id": str(order_data.address.id),
			"payment_method_id": str(order_data.payment_method.id),
		},
	)
	assert response.status_code == 503
	body = response.json()
	assert body["code"] == "B2B_UNAVAILABLE"
	assert "message" in body


async def test_order_not_authorized_returns_401(
	client: AsyncClient,
) -> None:
	response = await client.post(
		"/api/v1/orders",
		headers={
			"Idempotency-Key": str(uuid.uuid4()),
		},
	)
	assert response.status_code == 401
