import uuid

from httpx import AsyncClient
import pytest

from database.models.catalog.base import ProductStatusEnum
from tests.integration.cart.conftest import CollectionsData

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_collections_list_returns_metadata_without_products(
	client: AsyncClient,
	collections_data: CollectionsData,
) -> None:
	"""Список подборок отдаёт только метаданные, без товаров внутри."""
	response = await client.get("/api/v1/catalog/collections")
	assert response.status_code == 200
	body = response.json()

	expected_ids = {str(collection.id) for collection in collections_data.collections}
	assert len(body) == len(collections_data.collections)
	assert {collection["id"] for collection in body} == expected_ids
	for collection in body:
		assert "name" in collection
		assert "products" not in collection
		assert "items" not in collection
		assert "unavailable_ids" not in collection


async def test_collection_products_enriched_from_b2b(
	client: AsyncClient,
	collections_data: CollectionsData,
) -> None:
	"""Товары подборки обогащены данными из B2B (категория, продавец)."""
	collection_id = str(collections_data.collections[0].id)
	products_by_id = {product.id: product for product in collections_data.products}
	categories_by_id = {
		category.id: category for category in collections_data.categories
	}
	moderated_ids = {
		str(product.id)
		for product in collections_data.products
		if product.status == ProductStatusEnum.MODERATED
	}

	response = await client.get(f"/api/v1/catalog/collections/{collection_id}")
	assert response.status_code == 200
	body = response.json()

	assert body["id"] == collection_id
	assert {item["id"] for item in body["items"]} == moderated_ids
	for item in body["items"]:
		db_product = products_by_id[uuid.UUID(item["id"])]
		category = categories_by_id[uuid.UUID(item["category"]["id"])]
		assert item["category"]["name"] == category.name
		assert item["seller"]["id"] == str(db_product.seller.id)
		assert item["seller"]["display_name"] == db_product.seller.company_name


async def test_unavailable_products_in_unavailable_ids(
	client: AsyncClient,
	blocked_collections_data: CollectionsData,
) -> None:
	"""Удалённые/заблокированные в B2B → unavailable_ids, не в items."""
	collection_id = str(blocked_collections_data.collections[0].id)
	blocked_ids = {
		str(product.id)
		for product in blocked_collections_data.products
		if product.status == ProductStatusEnum.BLOCKED
	}
	moderated_ids = {
		str(product.id)
		for product in blocked_collections_data.products
		if product.status == ProductStatusEnum.MODERATED
	}

	response = await client.get(f"/api/v1/catalog/collections/{collection_id}")
	assert response.status_code == 200
	body = response.json()

	item_ids = {item["id"] for item in body["items"]}
	unavailable_ids = set(body["unavailable_ids"])

	assert item_ids == moderated_ids
	assert unavailable_ids == blocked_ids
	assert item_ids.isdisjoint(unavailable_ids)


async def test_unknown_collection_returns_404(
	client: AsyncClient,
) -> None:
	"""Несуществующая подборка → 404."""
	response = await client.get(f"/api/v1/catalog/collections/{uuid.uuid4()}")
	assert response.status_code == 404
	assert response.json()["detail"]["code"] == "NOT_FOUND"
