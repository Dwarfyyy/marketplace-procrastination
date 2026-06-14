import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.cart.conftest import CartItemsData, auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_test_get_cart_enriched_with_b2b_data_user(
	client: AsyncClient,
	db_session: AsyncSession,
	cart_user_data: CartItemsData,
) -> None:
	response = await client.get(
		"/api/v1/cart",
		headers=await auth_headers(cart_user_data.user.id, db_session),
	)
	assert response.status_code == 200
	body = response.json()
	assert len(body["items"]) == len(cart_user_data.items)
	assert body["items"][0]["quantity"] == cart_user_data.items[0].quantity
	assert body["items"][0]["product_id"] == str(cart_user_data.product.id)
	assert (
		body["items"][0]["name"]
		== f"{cart_user_data.product.title} — {cart_user_data.sku.name}"
	)
	assert body["items"][0]["sku_code"] == str(cart_user_data.sku.id)
	assert body["items"][0]["unit_price"] == cart_user_data.sku.price
	assert (
		body["items"][0]["unit_price_at_add"]
		== cart_user_data.items[0].unit_price_at_add
	)
	assert (
		body["items"][0]["line_total"]
		== cart_user_data.sku.price * cart_user_data.items[0].quantity
	)
	assert body["items"][0]["available_quantity"] == cart_user_data.sku.active_quantity
	assert body["items"][0]["image"]["url"] == cart_user_data.sku.images[0].url


async def test_test_get_cart_enriched_with_b2b_data_session(
	client: AsyncClient,
	cart_session_data: CartItemsData,
) -> None:
	response = await client.get(
		"/api/v1/cart",
		headers={"X-Session-Id": cart_session_data.session_id},
	)
	assert response.status_code == 200
	body = response.json()
	assert len(body["items"]) == len(cart_session_data.items)
	assert body["items"][0]["quantity"] == cart_session_data.items[0].quantity
	assert body["items"][0]["product_id"] == str(cart_session_data.product.id)
	assert (
		body["items"][0]["name"]
		== f"{cart_session_data.product.title} — {cart_session_data.sku.name}"
	)
	assert body["items"][0]["sku_code"] == str(cart_session_data.sku.id)
	assert body["items"][0]["unit_price"] == cart_session_data.sku.price
	assert (
		body["items"][0]["unit_price_at_add"]
		== cart_session_data.items[0].unit_price_at_add
	)
	assert (
		body["items"][0]["line_total"]
		== cart_session_data.sku.price * cart_session_data.items[0].quantity
	)
	assert (
		body["items"][0]["available_quantity"] == cart_session_data.sku.active_quantity
	)
	assert body["items"][0]["image"]["url"] == cart_session_data.sku.images[0].url


async def test_success_cart_validation(
	client: AsyncClient,
	db_session: AsyncSession,
	cart_user_data: CartItemsData,
) -> None:
	response = await client.post(
		"/api/v1/cart/validate",
		headers=await auth_headers(cart_user_data.user.id, db_session),
	)
	assert response.status_code == 200
	assert response.json()["is_valid"]
	assert response.json()["issues"] == []


async def test_validate_reports_price_changed(
	client: AsyncClient,
	db_session: AsyncSession,
	cart_user_data: CartItemsData,
) -> None:
	sku = cart_user_data.sku
	sku.price = sku.price + 500
	await db_session.commit()

	response = await client.post(
		"/api/v1/cart/validate",
		headers=await auth_headers(cart_user_data.user.id, db_session),
	)
	assert response.status_code == 200
	body = response.json()
	assert not body["is_valid"]
	assert body["issues"][0]["type"] == "PRICE_CHANGED"
	assert body["issues"][0]["old_value"] == cart_user_data.items[0].unit_price_at_add
	assert body["issues"][0]["new_value"] == sku.price
	assert (
		body["cart"]["items"][0]["unit_price_at_add"]
		== cart_user_data.items[0].unit_price_at_add
	)
	assert body["cart"]["items"][0]["unit_price"] == sku.price


async def test_unavailable_sku_shown_with_reason(
	client: AsyncClient,
	db_session: AsyncSession,
	unavailable_sku_in_cart_data: CartItemsData,
) -> None:
	response = await client.post(
		"/api/v1/cart/validate",
		headers=await auth_headers(unavailable_sku_in_cart_data.user.id, db_session),
	)
	assert response.status_code == 200
	body = response.json()
	assert not body["is_valid"]
	assert body["issues"][0]["type"] == "OUT_OF_STOCK"

	cart_item = body["cart"]["items"][0]
	assert cart_item["is_available"] is False
	assert cart_item["unavailable_reason"] == "OUT_OF_STOCK"
	assert cart_item["line_total"] == 0
	assert body["cart"]["subtotal"] == 0


async def test_add_sku_increments_quantity_if_already_in_cart(
	client: AsyncClient,
	db_session: AsyncSession,
	cart_user_data: CartItemsData,
) -> None:
	sku = cart_user_data.sku
	response = await client.post(
		"/api/v1/cart/items",
		json={"sku_id": str(sku.id), "quantity": 1},
		headers=await auth_headers(cart_user_data.user.id, db_session),
	)
	assert response.status_code == 200
	assert (
		response.json()["items"][0]["quantity"] == cart_user_data.items[0].quantity + 1
	)


async def test_clear_cart_returns_204(
	client: AsyncClient,
	db_session: AsyncSession,
	cart_user_data: CartItemsData,
) -> None:
	response = await client.delete(
		"/api/v1/cart",
		headers=await auth_headers(cart_user_data.user.id, db_session),
	)
	assert response.status_code == 204
	response = await client.get(
		"/api/v1/cart",
		headers=await auth_headers(cart_user_data.user.id, db_session),
	)
	assert response.status_code == 200
	assert response.json()["items"] == []


async def test_delete_cart_item_returns_updated_cart(
	client: AsyncClient,
	db_session: AsyncSession,
	cart_user_data: CartItemsData,
) -> None:
	sku = cart_user_data.sku
	response = await client.delete(
		f"/api/v1/cart/items/{sku.id}",
		headers=await auth_headers(cart_user_data.user.id, db_session),
	)
	assert response.status_code == 200
	assert response.json()["items"] == []


async def test_update_cart_item_quantity_returns_updated_cart(
	client: AsyncClient,
	db_session: AsyncSession,
	cart_user_data: CartItemsData,
) -> None:
	sku = cart_user_data.sku
	new_quantity = sku.active_quantity - 1
	response = await client.patch(
		f"/api/v1/cart/items/{sku.id}",
		json={"quantity": new_quantity},
		headers=await auth_headers(cart_user_data.user.id, db_session),
	)
	assert response.status_code == 200
	assert response.json()["items"][0]["quantity"] == new_quantity


async def test_merge_without_auth_returns_401(
	client: AsyncClient,
	cart_session_data: CartItemsData,
) -> None:
	response = await client.post(
		"/api/v1/cart/merge",
		headers={"X-Session-Id": cart_session_data.session_id},
	)
	assert response.status_code == 401
	assert response.json()["code"] == "UNAUTHORIZED"


async def test_guest_cart_merged_on_login(
	client: AsyncClient,
	db_session: AsyncSession,
	cart_user_data_with_conflict: tuple[CartItemsData, CartItemsData],
) -> None:
	user_data, guest_data = cart_user_data_with_conflict
	headers = await auth_headers(user_data.user.id, db_session)
	headers["X-Session-Id"] = guest_data.session_id
	response = await client.post(
		"/api/v1/cart/merge",
		headers=headers,
	)
	assert response.status_code == 200
	body = response.json()
	assert len(body["items"]) == 1
	assert body["items"][0]["quantity"] == 2
	assert body["items"][0]["sku_id"] == str(user_data.sku.id)
