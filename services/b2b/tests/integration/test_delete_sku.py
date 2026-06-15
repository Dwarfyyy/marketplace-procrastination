import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.catalog.base import Product, ProductStatusEnum
from database.models.catalog.variants import Sku
from database.models.identity.identity import Seller
from database.models.outbox import OutboxEvent, OutboxEventStatus
from tests.factories.catalog import CategoryFactory, ProductFactory, SkuFactory
from tests.factories.seller import SellerFactory
from tests.integration.conftest import auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_product_with_skus(
	db: AsyncSession,
	*,
	status: ProductStatusEnum,
	sku_quantities: list[tuple[int, int]],
) -> tuple[Seller, Product, list[Sku]]:
	seller = SellerFactory.build()
	category = CategoryFactory.build()
	db.add_all([seller, category])
	await db.flush()

	product = ProductFactory.build(
		category_id=category.id,
		seller_id=seller.id,
		status=status,
	)
	db.add(product)
	await db.flush()

	skus = [
		SkuFactory.build(
			product_id=product.id,
			active_quantity=active_quantity,
			reserved_quantity=reserved_quantity,
			stock_quantity=active_quantity + reserved_quantity,
		)
		for active_quantity, reserved_quantity in sku_quantities
	]
	db.add_all(skus)
	await db.commit()
	return seller, product, skus


async def _events_for_sku(db: AsyncSession, sku_id: uuid.UUID) -> list[OutboxEvent]:
	result = await db.execute(
		select(OutboxEvent).where(
			OutboxEvent.payload["payload"]["sku_id"].astext == str(sku_id)
		)
	)
	return list(result.scalars().all())


async def _events_for_product(
	db: AsyncSession, product_id: uuid.UUID
) -> list[OutboxEvent]:
	result = await db.execute(
		select(OutboxEvent).where(
			OutboxEvent.payload["payload"]["product_id"].astext == str(product_id)
		)
	)
	return list(result.scalars().all())


async def test_delete_sku_succeeds(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	seller, _, skus = await _create_product_with_skus(
		db_session,
		status=ProductStatusEnum.CREATED,
		sku_quantities=[(0, 0), (0, 0)],
	)
	headers = await auth_headers(seller.id, db_session)

	response = await client.delete(f"/api/v1/skus/{skus[0].id}", headers=headers)

	assert response.status_code == 204
	assert response.content == b""
	db_session.expire_all()
	assert await db_session.get(Sku, skus[0].id) is None
	assert await db_session.get(Sku, skus[1].id) is not None


async def test_delete_sku_with_active_reserves_returns_409(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	seller, _, skus = await _create_product_with_skus(
		db_session,
		status=ProductStatusEnum.MODERATED,
		sku_quantities=[(5, 2)],
	)
	headers = await auth_headers(seller.id, db_session)

	response = await client.delete(f"/api/v1/skus/{skus[0].id}", headers=headers)

	assert response.status_code == 409
	assert response.json()["code"] == "ACTIVE_RESERVES"
	assert set(response.json()) == {"code", "message"}
	db_session.expire_all()
	assert await db_session.get(Sku, skus[0].id) is not None


async def test_last_sku_on_moderation_transitions_product_to_created(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	seller, product, skus = await _create_product_with_skus(
		db_session,
		status=ProductStatusEnum.ON_MODERATION,
		sku_quantities=[(0, 0)],
	)
	headers = await auth_headers(seller.id, db_session)

	response = await client.delete(f"/api/v1/skus/{skus[0].id}", headers=headers)

	assert response.status_code == 204
	await db_session.refresh(product)
	assert product.status == ProductStatusEnum.CREATED
	events = await _events_for_product(db_session, product.id)
	assert len(events) == 1
	assert events[0].event_type == "PRODUCT_DELETED"
	assert events[0].routing_key == "moderation.product.deleted"
	assert events[0].status == OutboxEventStatus.PENDING


async def test_delete_sku_hard_blocked_product_returns_403(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	seller, _, skus = await _create_product_with_skus(
		db_session,
		status=ProductStatusEnum.HARD_BLOCKED,
		sku_quantities=[(5, 2)],
	)
	headers = await auth_headers(seller.id, db_session)

	response = await client.delete(f"/api/v1/skus/{skus[0].id}", headers=headers)

	assert response.status_code == 403
	assert response.json()["code"] == "FORBIDDEN"
	assert set(response.json()) == {"code", "message"}
	db_session.expire_all()
	assert await db_session.get(Sku, skus[0].id) is not None


async def test_delete_other_sellers_sku_returns_403(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	_, _, skus = await _create_product_with_skus(
		db_session,
		status=ProductStatusEnum.MODERATED,
		sku_quantities=[(0, 0)],
	)
	other_seller = SellerFactory.build()
	db_session.add(other_seller)
	await db_session.commit()
	headers = await auth_headers(other_seller.id, db_session)

	response = await client.delete(f"/api/v1/skus/{skus[0].id}", headers=headers)

	assert response.status_code == 403
	assert response.json()["code"] == "NOT_OWNER"
	assert set(response.json()) == {"code", "message"}
	db_session.expire_all()
	assert await db_session.get(Sku, skus[0].id) is not None


async def test_sku_out_of_stock_event_on_moderated_product(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	seller, product, skus = await _create_product_with_skus(
		db_session,
		status=ProductStatusEnum.MODERATED,
		sku_quantities=[(5, 0)],
	)
	headers = await auth_headers(seller.id, db_session)

	response = await client.delete(f"/api/v1/skus/{skus[0].id}", headers=headers)

	assert response.status_code == 204
	events = await _events_for_sku(db_session, skus[0].id)
	assert len(events) == 1
	assert events[0].event_type == "SKU_OUT_OF_STOCK"
	assert events[0].routing_key == "b2c.sku.out_of_stock"
	assert events[0].payload["payload"]["product_id"] == str(product.id)
	assert events[0].payload["payload"]["available_quantity"] == 5
	assert events[0].status == OutboxEventStatus.PENDING
