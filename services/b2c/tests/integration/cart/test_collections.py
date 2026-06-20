import uuid

from httpx import AsyncClient
import pytest

from database.models.catalog.base import ProductStatusEnum
from tests.integration.cart.conftest import CollectionsData

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_collections_list_returns_metadata_with_products(
	client: AsyncClient,
	collections_data: CollectionsData,
) -> None:
	"""Список подборок отдаёт метаданные и товары внутри (`products`)."""
	response = await client.get("/api/v1/catalog/collections")
	assert response.status_code == 200
	body = response.json()

	expected_ids = {str(collection.id) for collection in collections_data.collections}
	assert len(body) == len(collections_data.collections)
	assert {collection["id"] for collection in body} == expected_ids
	for collection in body:
		assert "name" in collection
		assert isinstance(collection["products"], list)


async def test_collection_products_enriched_from_b2b(
	client: AsyncClient,
	collections_data: CollectionsData,
) -> None:
	"""Товары подборки обогащены данными из B2B (категория, продавец)."""
	products_by_id = {product.id: product for product in collections_data.products}
	categories_by_id = {
		category.id: category for category in collections_data.categories
	}
	moderated_ids = {
		str(product.id)
		for product in collections_data.products
		if product.status == ProductStatusEnum.MODERATED
	}

	response = await client.get("/api/v1/catalog/collections")
	assert response.status_code == 200
	body = response.json()

	collection = body[0]
	assert {item["id"] for item in collection["products"]} == moderated_ids
	for item in collection["products"]:
		db_product = products_by_id[uuid.UUID(item["id"])]
		category = categories_by_id[uuid.UUID(item["category"]["id"])]
		assert item["category"]["name"] == category.name
		assert item["seller"]["id"] == str(db_product.seller.id)
		assert item["seller"]["display_name"] == db_product.seller.company_name


async def test_unavailable_products_excluded_from_products(
	client: AsyncClient,
	blocked_collections_data: CollectionsData,
) -> None:
	"""Удалённые/заблокированные в B2B не попадают в `products`."""
	moderated_ids = {
		str(product.id)
		for product in blocked_collections_data.products
		if product.status == ProductStatusEnum.MODERATED
	}
	blocked_ids = {
		str(product.id)
		for product in blocked_collections_data.products
		if product.status == ProductStatusEnum.BLOCKED
	}

	response = await client.get("/api/v1/catalog/collections")
	assert response.status_code == 200
	body = response.json()

	collection = body[0]
	product_ids = {item["id"] for item in collection["products"]}

	assert product_ids == moderated_ids
	assert product_ids.isdisjoint(blocked_ids)


async def test_no_active_collections_returns_empty_list(
	client: AsyncClient,
) -> None:
	"""Нет активных подборок → `200` с пустым массивом."""
	response = await client.get("/api/v1/catalog/collections")
	assert response.status_code == 200
	assert response.json() == []
