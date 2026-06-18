import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.catalog.variants import Characteristic, Image, ImageEntityTypeEnum
from database.models.outbox import OutboxEvent
from tests.integration.conftest import (
	CreateProductData,
	auth_headers,
)


pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_create_product_returns_201_with_created_status(
	client: AsyncClient,
	create_product_data: CreateProductData,
	db_session: AsyncSession,
) -> None:
	outbox_count_before = await db_session.scalar(select(func.count(OutboxEvent.id)))
	response = await client.post(
		"/api/v1/products",
		headers=await auth_headers(create_product_data.seller.id, db_session),
		json={
			"category_id": str(create_product_data.category.id),
			"title": "Test product",
			"description": "Some smart words",
			"slug": "some-product",
			"images": [{"url": "/products/some-product.jpg", "ordering": 0}],
			"characteristics": [{"name": "Brand", "value": "NeoMarket"}],
		},
	)

	assert response.status_code == 201
	body = response.json()
	assert body["status"] == "CREATED"
	assert body["skus"] == []
	assert body["images"][0]["url"] == "/products/some-product.jpg"
	assert body["characteristics"][0] == {
		"id": body["characteristics"][0]["id"],
		"name": "Brand",
		"value": "NeoMarket",
	}

	images = await db_session.scalars(
		select(Image).where(
			Image.entity_type == ImageEntityTypeEnum.PRODUCT,
			Image.entity_id == uuid.UUID(body["id"]),
		)
	)
	characteristics = await db_session.scalars(
		select(Characteristic).where(
			Characteristic.product_id == uuid.UUID(body["id"])
		)
	)
	assert len(images.all()) == 1
	assert len(characteristics.all()) == 1
	outbox_count_after = await db_session.scalar(select(func.count(OutboxEvent.id)))
	assert outbox_count_after == outbox_count_before


async def test_seller_id_taken_from_jwt(
	client: AsyncClient,
	create_product_data: CreateProductData,
	db_session: AsyncSession,
) -> None:
	response = await client.post(
		"/api/v1/products",
		headers=await auth_headers(create_product_data.seller.id, db_session),
		json={
			"category_id": str(create_product_data.category.id),
			"title": "Test product",
			"description": "Some smart words",
			"slug": "some-product",
			"seller_id": "00000000-0000-0000-0000-000000000001",
			"images": [{"url": "/products/some-product.jpg"}],
		},
	)

	assert response.status_code == 201
	assert response.json()["seller_id"] == str(create_product_data.seller.id)


async def test_optional_slug_and_images_can_be_omitted(
	client: AsyncClient,
	create_product_data: CreateProductData,
	db_session: AsyncSession,
) -> None:
	response = await client.post(
		"/api/v1/products",
		headers=await auth_headers(create_product_data.seller.id, db_session),
		json={
			"category_id": str(create_product_data.category.id),
			"title": "Test product",
			"description": "Some smart words",
		},
	)

	assert response.status_code == 201
	body = response.json()
	assert body["slug"].startswith("product-")
	assert body["images"] == []


async def test_missing_category_returns_400(
	client: AsyncClient,
	create_product_data: CreateProductData,
	db_session: AsyncSession,
) -> None:
	response = await client.post(
		"/api/v1/products",
		headers=await auth_headers(create_product_data.seller.id, db_session),
		json={
			"title": "Test product",
			"description": "Some smart words",
			"slug": "some-product",
			"images": [{"url": "/products/some-product.jpg"}],
		},
	)

	assert response.status_code == 400
	assert response.json()["code"] == "VALIDATION_ERROR"
	assert "category_id" in response.json()["message"]
	assert set(response.json()) == {"code", "message"}


async def test_invalid_category_id_returns_400(
	client: AsyncClient,
	create_product_data: CreateProductData,
	db_session: AsyncSession,
) -> None:
	response = await client.post(
		"/api/v1/products",
		headers=await auth_headers(create_product_data.seller.id, db_session),
		json={
			"category_id": "00000000-0000-0000-0000-000000000001",
			"title": "Test product",
			"description": "Some smart words",
			"slug": "some-product",
			"images": [{"url": "/products/some-product.jpg"}],
		},
	)

	assert response.status_code == 400
	assert response.json() == {
		"code": "INVALID_CATEGORY",
		"message": "Category not found",
	}
