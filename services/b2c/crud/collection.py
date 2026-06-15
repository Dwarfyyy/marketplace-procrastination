import uuid
from datetime import date
from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Collection, CollectionProduct, Product, Sku
from database.models.catalog.base import ProductStatusEnum


def _moderated_available_product_ids(
	product_ids: list[uuid.UUID] | None = None,
) -> Product:
	conditions = [
		Product.deleted == False,  # noqa: E712
		Product.status == ProductStatusEnum.MODERATED,
		Product.id.in_(select(Sku.product_id).where(Sku.active_quantity > 0)),
	]
	if product_ids is not None:
		conditions.append(Product.id.in_(product_ids))
	return select(Product.id).where(*conditions)


async def get_active_collections(
	db: AsyncSession, limit: int = 10, offset: int = 0
) -> Sequence[Collection]:
	"""Получить список активных подборок"""
	today = date.today()

	query = (
		select(Collection)
		.where(
			Collection.is_active == True,  # noqa
			(Collection.start_date <= today) | (Collection.start_date.is_(None)),
		)
		.order_by(Collection.priority)
		.offset(offset)
		.limit(limit)
	)
	result = await db.execute(query)
	return result.scalars().all()


async def count_active_collections(db: AsyncSession) -> int:
	"""Получить общее количество активных подборок"""
	today = date.today()

	query = select(func.count(Collection.id)).where(
		Collection.is_active == True,  # noqa
		(Collection.start_date <= today) | (Collection.start_date.is_(None)),
	)
	result = await db.execute(query)
	return result.scalar() or 0


async def get_collection_product_ids(
	db: AsyncSession, collection_id: uuid.UUID
) -> list[uuid.UUID]:
	"""Все UUID товаров, привязанных к подборке (без фильтра доступности).

	B2C хранит только связь подборка→UUID; актуальность товара определяется
	позже обогащением из B2B. Поэтому здесь возвращаются все привязанные id,
	а недоступные затем отбрасываются при сборке `products`.
	"""
	query = (
		select(CollectionProduct.product_id)
		.where(CollectionProduct.collection_id == collection_id)
		.order_by(CollectionProduct.product_id)
	)
	result = await db.execute(query)
	return [product_id for (product_id,) in result.all()]


async def get_available_catalog_products_by_ids(
	db: AsyncSession, product_ids: list[uuid.UUID]
) -> list[Product]:
	if not product_ids:
		return []

	query = (
		select(Product)
		.where(Product.id.in_(_moderated_available_product_ids(product_ids)))
		.options(
			selectinload(Product.images),
			selectinload(Product.skus),
			selectinload(Product.seller),
		)
	)
	result = await db.execute(query)
	products_by_id = {product.id: product for product in result.scalars().all()}
	return [
		products_by_id[product_id]
		for product_id in product_ids
		if product_id in products_by_id
	]
