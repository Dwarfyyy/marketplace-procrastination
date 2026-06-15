import json
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

import crud.product as product_crud
import crud.category as category_crud
import crud.review as review_crud
from database.models import Sku
from exceptions.product import ProductNotFoundError
from schemas.catalog import (
	CatalogProductCard,
	CatalogProductDetail,
	PaginatedCatalogProducts,
)
from services.schemas_builder import (
	build_catalog_product_cards,
	build_catalog_product_detail,
)
from schemas.sku import SkuShort
from schemas.image import Image


async def get_product_skus(db: AsyncSession, product_id: uuid.UUID) -> list[Sku]:
	"""
	Gets a SKU by its ID
	:param db: database session
	:param product_id: SKU ID
	:return: SKU or None if not found
	:raises ProductNotFoundError: if product not found
	"""
	skus = await product_crud.get_product_skus(db, product_id)

	if not skus:
		raise ProductNotFoundError

	return skus


async def get_product_skus_short(
	db: AsyncSession, product_id: uuid.UUID
) -> list[SkuShort]:
	"""
	Gets SKUs in short format by product ID
	:param db: database session
	:param product_id: Product ID
	:return: List of SKUs in short format
	:raises ProductNotFoundError: if product not found
	"""
	skus = await product_crud.get_product_skus(db, product_id)

	if not skus:
		raise ProductNotFoundError

	return [
		SkuShort(
			name=sku.name,
			price=sku.price,
			image=sku.images[0] if sku.images else Image(url="", order=0),
		)
		for sku in skus
	]


async def get_products_list(
	db: AsyncSession,
	limit: int,
	offset: int,
	category_id: Optional[str],
	filters_json: Optional[str],
	sort: str,
	search: Optional[str],
) -> PaginatedCatalogProducts:
	# Валидация sort согласно спецификации
	valid_sorts = [
		"price_asc",
		"price_desc",
		"popularity",
		"new",
	]
	if sort not in valid_sorts:
		raise ValueError(f"Invalid sort parameter. Allowed: {', '.join(valid_sorts)}")

	if search:
		search_stripped = search.strip()

		if 0 < len(search_stripped) < 4:
			raise ValueError("Search query must be at least 4 characters")

		if len(search_stripped) > 255:
			raise ValueError("Search query must be at most 255 characters")

	cat_uuid = uuid.UUID(category_id) if category_id else None
	filter = json.loads(filters_json) if filters_json else {}

	products, total_count = await product_crud.get_products_list(
		db, limit, offset, cat_uuid, filter, sort, search
	)

	categories_map = await category_crud.get_all_categories_map(db)
	review_stats_by_product = await review_crud.get_reviews_stats_by_product_ids(
		db, [product.id for product in products]
	)
	items = build_catalog_product_cards(
		products, categories_map, review_stats_by_product
	)

	return PaginatedCatalogProducts(
		items=items, total_count=total_count, limit=limit, offset=offset
	)


async def get_product_by_id(db: AsyncSession, id: uuid.UUID) -> CatalogProductDetail:
	product = await product_crud.get_product_full(db, id)
	if not product:
		raise ProductNotFoundError("Product not found")
	return build_catalog_product_detail(product)


async def get_similar_products(
	db: AsyncSession, product_id: uuid.UUID, limit: int
) -> list[CatalogProductCard]:
	category_id = await product_crud.get_product_category_id(db, product_id)
	products = await product_crud.get_similar_products(
		db, category_id, product_id, limit
	)
	if not products:
		return []

	categories_map = await category_crud.get_all_categories_map(db)
	review_stats_by_product = await review_crud.get_reviews_stats_by_product_ids(
		db, [product.id for product in products]
	)
	return build_catalog_product_cards(
		products, categories_map, review_stats_by_product
	)
