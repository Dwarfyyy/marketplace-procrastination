import pytest
from httpx import AsyncClient
from sqlalchemy.exc import OperationalError

from tests.integration.catalog.conftest import (
	CategoriesTreeData,
	CategoryWithProductsData,
	VisibilityProductsData,
)


pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_facets_returns_empty_list_for_empty_category(
	client: AsyncClient,
	categories_tree: CategoriesTreeData,
) -> None:
	response = await client.get(
		"/api/v1/catalog/facets",
		params={"category_id": str(categories_tree.grandchild.id)},
	)
	body = response.json()

	assert response.status_code == 200
	assert body["category_id"] == str(categories_tree.grandchild.id)
	assert body["facets"] == []


async def test_facets_return_counts_per_filter_value(
	client: AsyncClient,
	category_with_products: CategoryWithProductsData,
) -> None:
	response = await client.get(
		"/api/v1/catalog/facets",
		params={"category_id": str(category_with_products.category.id)},
	)
	body = response.json()

	assert response.status_code == 200
	assert body["category_id"] == str(category_with_products.category.id)

	expected_filter_ids = {str(filter.id) for filter in category_with_products.filters}
	actual_filter_ids = {filter["id"] for filter in body["filters"]}
	assert expected_filter_ids == actual_filter_ids

	values = [val for facet in body["facets"] for val in facet.get("values", [])]
	values_by_value = {val["value"]: val["count"] for val in values}

	expected_values = {val.value for val in category_with_products.values}
	assert expected_values.issubset(values_by_value.keys())

	for value in expected_values:
		assert values_by_value[value] == 0


async def test_catalog_returns_filtered_sorted_products(
	client: AsyncClient,
	category_with_products: CategoryWithProductsData,
) -> None:
	response = await client.get(
		"/api/v1/catalog/products",
		params={
			"filter[category_id]": str(category_with_products.category.id),
		},
	)

	assert response.status_code == 200
	body = response.json()
	items = body["items"]
	assert len(items) == 2
	assert body["total_count"] == 2
	assert items[0]["id"] == str(category_with_products.products[0].id)
	assert items[1]["id"] == str(category_with_products.products[1].id)


@pytest.mark.parametrize("sort", ["invalid", "title_asc", "title_desc"])
async def test_invalid_sort_returns_400(
	client: AsyncClient, category_with_products: CategoryWithProductsData, sort: str
) -> None:
	response = await client.get(
		"/api/v1/catalog/products",
		params={
			"filter[category_id]": str(category_with_products.category.id),
			"sort": sort,
		},
	)
	assert response.status_code == 400


async def test_search_description_returns_matching_products(
	client: AsyncClient, category_with_products: CategoryWithProductsData
) -> None:
	response = await client.get(
		"/api/v1/catalog/products",
		params={
			"filter[category_id]": str(category_with_products.category.id),
			"q": "Description 1",
		},
	)
	assert response.status_code == 200
	body = response.json()
	items = body["items"]
	assert len(items) == 2
	assert items[0]["id"] == str(category_with_products.products[0].id)
	assert items[1]["id"] == str(category_with_products.products[1].id)


async def test_search_title_returns_matching_products(
	client: AsyncClient, category_with_products: CategoryWithProductsData
) -> None:
	response = await client.get(
		"/api/v1/catalog/products",
		params={
			"filter[category_id]": str(category_with_products.category.id),
			"q": "Product 1",
		},
	)
	assert response.status_code == 200
	body = response.json()
	items = body["items"]
	assert len(items) == 1
	assert items[0]["id"] == str(category_with_products.products[0].id)


@pytest.mark.parametrize("search", ["t", "te", "tes"])
async def test_short_query_returns_400(
	client: AsyncClient, category_with_products: CategoryWithProductsData, search: str
) -> None:
	response = await client.get(
		"/api/v1/catalog/products",
		params={
			"filter[category_id]": str(category_with_products.category.id),
			"q": search,
		},
	)
	assert response.status_code == 400


async def test_empty_results_returns_200(
	client: AsyncClient, category_with_products: CategoryWithProductsData
) -> None:
	response = await client.get(
		"/api/v1/catalog/products",
		params={
			"filter[category_id]": str(category_with_products.category.id),
			"q": "Not exists",
		},
	)
	assert response.status_code == 200
	body = response.json()
	assert body["items"] == []


async def test_special_chars_do_not_break_query(
	client: AsyncClient, category_with_products: CategoryWithProductsData
) -> None:
	response = await client.get(
		"/api/v1/catalog/products",
		params={
			"filter[category_id]": str(category_with_products.category.id),
			"q": "!@#$%^&*()",
		},
	)
	assert response.status_code == 200
	body = response.json()
	assert body["items"] == []


async def test_products_list_filters_only_visible_products(
	client: AsyncClient,
	visibility_products: VisibilityProductsData,
) -> None:
	response = await client.get(
		"/api/v1/catalog/products",
		params={"filter[category_id]": str(visibility_products.category.id)},
	)
	assert response.status_code == 200
	body = response.json()
	ids = {item["id"] for item in body["items"]}
	assert str(visibility_products.visible_product.id) in ids
	assert str(visibility_products.hidden_by_status_product.id) not in ids
	assert str(visibility_products.hidden_by_stock_product.id) not in ids


async def test_b2b_unavailable_returns_502(
	client: AsyncClient,
	category_with_products: CategoryWithProductsData,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	async def _raise_unavailable(*args, **kwargs):
		raise OperationalError("SELECT 1", {}, Exception("connection refused"))

	monkeypatch.setattr(
		"services.product_service.product_crud.get_products_list",
		_raise_unavailable,
	)

	response = await client.get(
		"/api/v1/catalog/products",
		params={"filter[category_id]": str(category_with_products.category.id)},
	)

	assert response.status_code == 502
	body = response.json()
	assert body["code"] == "B2B_UNAVAILABLE"
	assert "message" in body
