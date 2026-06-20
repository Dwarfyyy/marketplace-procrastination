import uuid

from sqlalchemy.ext.asyncio import AsyncSession

import crud.category as category_crud
import crud.collection as collection_crud
import crud.review as review_crud
from schemas.catalog import CatalogProductCard
from schemas.collection import Collection
from services.schemas_builder import build_catalog_product_cards


async def get_collections(db: AsyncSession) -> list[Collection]:
	"""Активные подборки с товарами внутри, batch-обогащёнными из B2B.

	B2C хранит только UUID товаров каждой подборки; здесь все привязанные id
	обогащаются одним батчем из каталога (B2B). Доступные товары превращаются в
	карточки и попадают в `products`; недоступные (удалённые/заблокированные/на
	модерации/нет в наличии) в выдачу не включаются — подборка не ломается.
	Нет активных подборок → `[]`.
	"""
	total_count = await collection_crud.count_active_collections(db)
	if total_count == 0:
		return []

	collections_db = await collection_crud.get_active_collections(
		db, limit=total_count, offset=0
	)

	product_ids_by_collection: dict[uuid.UUID, list[uuid.UUID]] = {
		collection.id: await collection_crud.get_collection_product_ids(
			db, collection.id
		)
		for collection in collections_db
	}
	all_product_ids = {
		product_id
		for product_ids in product_ids_by_collection.values()
		for product_id in product_ids
	}

	cards_by_id = await _enrich_cards_by_id(db, list(all_product_ids))

	return [
		Collection(
			id=collection.id,
			name=collection.title,
			description=collection.description or "",
			cover_image_url=collection.cover_image_url,
			target_url=collection.target_url,
			products=[
				cards_by_id[product_id]
				for product_id in product_ids_by_collection[collection.id]
				if product_id in cards_by_id
			],
		)
		for collection in collections_db
	]


async def _enrich_cards_by_id(
	db: AsyncSession, product_ids: list[uuid.UUID]
) -> dict[uuid.UUID, CatalogProductCard]:
	"""Batch-обогащение доступных товаров в карточки, индексированные по id."""
	if not product_ids:
		return {}

	products = await collection_crud.get_available_catalog_products_by_ids(
		db, product_ids
	)
	categories_map = await category_crud.get_all_categories_map(db)
	review_stats_by_product = await review_crud.get_reviews_stats_by_product_ids(
		db, [product.id for product in products]
	)
	cards = build_catalog_product_cards(
		products, categories_map, review_stats_by_product
	)
	return {card.id: card for card in cards}
