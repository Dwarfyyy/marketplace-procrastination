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
	response = await client.get(f"/api/v1/products/{product.id}")

	assert response.status_code == 200
	body = response.json()
	assert body["id"] == str(product.id)
	assert body["title"] == product.title
	assert body["description"] == product.description
	assert body["images"] == [image.url for image in product.images]
	assert [item["name"] for item in body["skus"]] == [sku.name for sku in skus]
	for item, sku in zip(body["skus"], skus):
		assert item["discount"] == sku.discount
		assert item["in_stock"] is (sku.active_quantity > 0)


async def test_cost_price_absent_in_response(
	client: AsyncClient,
	products_data: ProductData,
) -> None:
	product = products_data.base_product
	response = await client.get(f"/api/v1/products/{product.id}")

	assert response.status_code == 200
	body = response.json()
	assert "cost_price" not in body["skus"][0]
	assert "reserved_quantity" not in body["skus"][0]


async def test_blocked_product_returns_404(
	client: AsyncClient,
	blocked_product_data: ProductData,
) -> None:
	product = blocked_product_data.base_product
	response = await client.get(f"/api/v1/products/{product.id}")
	assert response.status_code == 404


async def test_sku_without_stock_is_shown_as_unavailable(
	client: AsyncClient,
	product_skus_out_of_stock_data: ProductData,
) -> None:
	product = product_skus_out_of_stock_data.base_product
	response = await client.get(f"/api/v1/products/{product.id}")

	assert response.status_code == 200
	body = response.json()
	assert body["id"] == str(product.id)
	assert not body["skus"][0]["in_stock"]
