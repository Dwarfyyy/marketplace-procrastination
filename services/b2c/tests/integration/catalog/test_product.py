import pytest
from httpx import AsyncClient

from tests.integration.catalog.conftest import ProductData


pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_product_card_returns_full_data_with_skus(
	client: AsyncClient,
	products_data: ProductData,
) -> None:
	product = products_data.base_product
	skus = products_data.skus
	response = await client.get(f"/api/v1/catalog/products/{product.id}")

	assert response.status_code == 200
	body = response.json()
	assert body["id"] == str(product.id)
	assert body["name"] == product.title
	assert body["description"] == product.description
	assert [image["url"] for image in body["images"]] == [
		image.url for image in product.images
	]
	assert body["min_price"] == min(sku.price for sku in skus)
	assert body["has_stock"] is any(sku.active_quantity > 0 for sku in skus)
	assert [item["name"] for item in body["skus"]] == [sku.name for sku in skus]
	for item, sku in zip(body["skus"], skus):
		assert item["discount"] == sku.discount
		assert item["available_quantity"] == sku.active_quantity
		assert item["in_stock"] is (sku.active_quantity > 0)


async def test_seller_internal_fields_absent_in_response(
	client: AsyncClient,
	products_data: ProductData,
) -> None:
	product = products_data.base_product
	response = await client.get(f"/api/v1/catalog/products/{product.id}")

	assert response.status_code == 200
	body = response.json()
	# Storefront card must not leak the seller-side moderation status (B2B).
	assert "status" not in body
	sku = body["skus"][0]
	assert "cost_price" not in sku
	assert "reserved_quantity" not in sku
	# Contract uses available_quantity, not the raw seller field name.
	assert "quantity" not in sku


async def test_images_serialized_as_image_refs(
	client: AsyncClient,
	products_data: ProductData,
) -> None:
	product = products_data.base_product
	response = await client.get(f"/api/v1/catalog/products/{product.id}")

	assert response.status_code == 200
	body = response.json()
	for image in body["images"]:
		assert isinstance(image, dict)
		assert {"id", "url", "ordering", "is_main"} <= image.keys()


async def test_blocked_product_returns_404(
	client: AsyncClient,
	blocked_product_data: ProductData,
) -> None:
	product = blocked_product_data.base_product
	response = await client.get(f"/api/v1/catalog/products/{product.id}")
	assert response.status_code == 404


async def test_sku_without_stock_is_shown_as_unavailable(
	client: AsyncClient,
	product_skus_out_of_stock_data: ProductData,
) -> None:
	product = product_skus_out_of_stock_data.base_product
	response = await client.get(f"/api/v1/catalog/products/{product.id}")

	assert response.status_code == 200
	body = response.json()
	assert body["id"] == str(product.id)
	assert body["has_stock"] is False
	assert body["skus"][0]["available_quantity"] == 0
	assert not body["skus"][0]["in_stock"]
