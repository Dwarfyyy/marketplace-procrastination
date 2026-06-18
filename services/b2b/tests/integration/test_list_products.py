from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.catalog.base import Product, ProductStatusEnum
from database.models.catalog.variants import Sku
from database.models.identity.identity import Seller
from tests.factories.catalog import CategoryFactory, ProductFactory, SkuFactory
from tests.factories.seller import SellerFactory
from tests.integration.conftest import auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


@dataclass(frozen=True, slots=True)
class SellerListData:
	owner: Seller
	other_seller: Seller
	own_moderated: Product
	own_blocked: Product
	own_deleted: Product
	other_product: Product
	moderated_skus: list[Sku]


@pytest.fixture()
async def seller_list_data(db_session: AsyncSession) -> SellerListData:
	owner = SellerFactory.build()
	other_seller = SellerFactory.build()
	category = CategoryFactory.build()
	db_session.add_all([owner, other_seller, category])
	await db_session.flush()

	own_moderated = ProductFactory.build(
		seller_id=owner.id,
		category_id=category.id,
		title="Premium Mechanical Keyboard",
		status=ProductStatusEnum.MODERATED,
	)
	own_blocked = ProductFactory.build(
		seller_id=owner.id,
		category_id=category.id,
		title="Blocked headset",
		status=ProductStatusEnum.BLOCKED,
	)
	own_deleted = ProductFactory.build(
		seller_id=owner.id,
		category_id=category.id,
		title="Deleted mouse",
		status=ProductStatusEnum.MODERATED,
		deleted=True,
	)
	other_product = ProductFactory.build(
		seller_id=other_seller.id,
		category_id=category.id,
		title="Competitor keyboard",
		status=ProductStatusEnum.MODERATED,
	)
	db_session.add_all([own_moderated, own_blocked, own_deleted, other_product])
	await db_session.flush()

	moderated_skus = [
		SkuFactory.build(product_id=own_moderated.id, active_quantity=4),
		SkuFactory.build(product_id=own_moderated.id, active_quantity=7),
	]
	db_session.add_all(
		[
			*moderated_skus,
			SkuFactory.build(product_id=own_blocked.id, active_quantity=3),
			SkuFactory.build(product_id=other_product.id, active_quantity=100),
		]
	)
	await db_session.commit()
	return SellerListData(
		owner=owner,
		other_seller=other_seller,
		own_moderated=own_moderated,
		own_blocked=own_blocked,
		own_deleted=own_deleted,
		other_product=other_product,
		moderated_skus=moderated_skus,
	)


async def test_list_returns_only_own_products(
	client: AsyncClient,
	seller_list_data: SellerListData,
	db_session: AsyncSession,
) -> None:
	headers = await auth_headers(seller_list_data.owner.id, db_session)

	response = await client.get("/api/v1/products", headers=headers)

	assert response.status_code == 200
	body = response.json()
	items = body["items"]
	assert body["total_count"] == 3
	assert body["limit"] == 20
	assert body["offset"] == 0
	assert {item["id"] for item in items} == {
		str(seller_list_data.own_moderated.id),
		str(seller_list_data.own_blocked.id),
		str(seller_list_data.own_deleted.id),
	}
	assert {item["seller_id"] for item in items} == {str(seller_list_data.owner.id)}
	moderated = next(
		item for item in items if item["id"] == str(seller_list_data.own_moderated.id)
	)
	assert moderated["skus_count"] == 2
	assert moderated["total_active_quantity"] == 11


async def test_idor_query_param_seller_id_ignored(
	client: AsyncClient,
	seller_list_data: SellerListData,
	db_session: AsyncSession,
) -> None:
	headers = await auth_headers(seller_list_data.owner.id, db_session)

	response = await client.get(
		"/api/v1/products",
		headers=headers,
		params={"seller_id": str(seller_list_data.other_seller.id)},
	)

	assert response.status_code == 200
	ids = {item["id"] for item in response.json()["items"]}
	assert str(seller_list_data.other_product.id) not in ids
	assert str(seller_list_data.own_moderated.id) in ids

	invalid_response = await client.get(
		"/api/v1/products",
		headers=headers,
		params={"seller_id": "not-a-uuid"},
	)
	assert invalid_response.status_code == 200


async def test_deleted_products_visible_with_deleted_flag(
	client: AsyncClient,
	seller_list_data: SellerListData,
	db_session: AsyncSession,
) -> None:
	headers = await auth_headers(seller_list_data.owner.id, db_session)

	response = await client.get("/api/v1/products", headers=headers)

	assert response.status_code == 200
	deleted = next(
		item
		for item in response.json()["items"]
		if item["id"] == str(seller_list_data.own_deleted.id)
	)
	assert deleted["deleted"] is True


async def test_status_filter_works_correctly(
	client: AsyncClient,
	seller_list_data: SellerListData,
	db_session: AsyncSession,
) -> None:
	headers = await auth_headers(seller_list_data.owner.id, db_session)

	response = await client.get(
		"/api/v1/products",
		headers=headers,
		params={"status": "BLOCKED"},
	)

	assert response.status_code == 200
	assert [item["id"] for item in response.json()["items"]] == [
		str(seller_list_data.own_blocked.id)
	]


async def test_search_by_title_case_insensitive(
	client: AsyncClient,
	seller_list_data: SellerListData,
	db_session: AsyncSession,
) -> None:
	headers = await auth_headers(seller_list_data.owner.id, db_session)

	response = await client.get(
		"/api/v1/products",
		headers=headers,
		params={"search": "mEcHaNiCaL"},
	)

	assert response.status_code == 200
	assert [item["id"] for item in response.json()["items"]] == [
		str(seller_list_data.own_moderated.id)
	]


async def test_pagination_and_include_deleted_filter(
	client: AsyncClient,
	seller_list_data: SellerListData,
	db_session: AsyncSession,
) -> None:
	headers = await auth_headers(seller_list_data.owner.id, db_session)

	response = await client.get(
		"/api/v1/products",
		headers=headers,
		params={"limit": 1, "offset": 1, "include_deleted": False},
	)

	assert response.status_code == 200
	body = response.json()
	assert body["total_count"] == 2
	assert body["limit"] == 1
	assert body["offset"] == 1
	assert len(body["items"]) == 1
	assert body["items"][0]["deleted"] is False
