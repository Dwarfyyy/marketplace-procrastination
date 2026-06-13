import uuid

from sqlalchemy.ext.asyncio import AsyncSession

import crud.category as category_crud
import crud.collection as collection_crud
import crud.review as review_crud
from exceptions.collection import CollectionNotFoundError
from schemas.collection import CollectionProducts, CollectionSummary
from services.schemas_builder import build_catalog_product_cards


async def get_collection_summaries(db: AsyncSession) -> list[CollectionSummary]:
	"""Список активных подборок — только метаданные, без товаров внутри."""
	total_count = await collection_crud.count_active_collections(db)
	if total_count == 0:
		return []

	collections_db = await collection_crud.get_active_collections(
		db, limit=total_count, offset=0
	)
	return [
		CollectionSummary(
			id=collection.id,
			name=collection.title,
			description=collection.description or "",
			cover_image_url=collection.cover_image_url,
			target_url=collection.target_url,
		)
		for collection in collections_db
	]


async def get_collection_products(
	db: AsyncSession, collection_id: uuid.UUID
) -> CollectionProducts:
	"""Товары конкретной подборки с batch-обогащением из B2B.

	B2C хранит только UUID товаров; здесь все привязанные id обогащаются одним
	батчем из каталога (B2B). Доступные превращаются в карточки (`items`),
	недоступные (удалённые/заблокированные/на модерации/нет в наличии) тихо
	уходят в `unavailable_ids` — подборка при этом не ломается.
	"""
	collection = await collection_crud.get_active_collection_by_id(db, collection_id)
	if collection is None:
		raise CollectionNotFoundError(f"Collection not found: {collection_id}")

	product_ids = await collection_crud.get_collection_product_ids(db, collection_id)
	products = await collection_crud.get_available_catalog_products_by_ids(
		db, product_ids
	)

	categories_map = await category_crud.get_all_categories_map(db)
	review_stats_by_product = await review_crud.get_reviews_stats_by_product_ids(
		db, [product.id for product in products]
	)
	items = build_catalog_product_cards(
		products, categories_map, review_stats_by_product
	)

	available_ids = {product.id for product in products}
	unavailable_ids = [
		product_id for product_id in product_ids if product_id not in available_ids
	]

	return CollectionProducts(
		id=collection.id,
		name=collection.title,
		items=items,
		unavailable_ids=unavailable_ids,
	)
