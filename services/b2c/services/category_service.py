import uuid
import json
import os
import asyncio
from pathlib import Path
from pydantic import TypeAdapter

from schemas.catalog import CategoryRef, CategoryTreeNode
from schemas.category import (
	BreadcrumbItem,
	BreadcrumbMeta,
	BreadcrumbResponse,
	CategoryInfoResponse,
	CategoryParent,
	FacetsResponse,
	Facet,
	FacetValue,
	FilterResponse,
	ResolveViaEnum,
	Filter,
)
from exceptions.category import CategoryHierarchyError, CategoryNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

import crud.category as category_crud
import crud.product as product_crud
from database.models.catalog.base import Category
from services.schemas_builder import build_category_ref

# Cache file path
CACHE_DIR = Path("cache")
CATEGORIES_TREE_CACHE_FILE = CACHE_DIR / "categories_tree.json"

_category_tree_list_adapter = TypeAdapter(list[CategoryTreeNode])

# Lock to prevent concurrent cache rebuilds - created lazily
_cache_rebuild_lock = None


def _get_cache_lock() -> asyncio.Lock:
	"""Get or create the cache rebuild lock for the current event loop."""
	global _cache_rebuild_lock
	if _cache_rebuild_lock is None:
		_cache_rebuild_lock = asyncio.Lock()
	return _cache_rebuild_lock


def _load_tree_cache() -> list[CategoryTreeNode] | None:
	if not CATEGORIES_TREE_CACHE_FILE.exists():
		return None
	try:
		with open(CATEGORIES_TREE_CACHE_FILE, "r", encoding="utf-8") as f:  # noqa
			cache_data = json.load(f)
		if isinstance(cache_data, dict) and "items" in cache_data:
			return None
		return _category_tree_list_adapter.validate_python(cache_data)
	except Exception as e:  # noqa
		print(f"Failed to load cache: {e}")
		return None


def _save_tree_cache(tree: list[CategoryTreeNode]) -> None:
	try:
		CACHE_DIR.mkdir(exist_ok=True)
		with open(CATEGORIES_TREE_CACHE_FILE, "w", encoding="utf-8") as f:  # noqa
			json.dump(
				[n.model_dump(mode="json") for n in tree],
				f,
				ensure_ascii=False,
				indent=2,
			)
	except Exception as e:  # noqa
		print(f"Failed to save cache: {e}")


async def get_category_info(
	db: AsyncSession, id: str, include_product_count: bool
) -> CategoryInfoResponse:
	id: uuid.UUID = uuid.UUID(id)  # Raises ValueError if invalid

	category = await category_crud.get_category_by_id(db, id)
	if not category:
		raise CategoryNotFoundError(f"Category with id {id} not found")

	parent_info = None
	if category.parent_id:
		parent_category = await category_crud.get_category_by_id(db, category.parent_id)
		parent_info = CategoryParent(
			id=parent_category.id, name=parent_category.name, slug=parent_category.slug
		)

	return CategoryInfoResponse(
		id=category.id,
		name=category.name,
		slug=category.slug,
		description=category.description,
		parent=parent_info if category.parent_id else None,
		product_count=await category_product_count(db, id)
		if include_product_count
		else None,
		seo=None,  # TODO implement  # noqa
		meta_tags=None,  # TODO implement # noqa
		image_url=category.image_url,
		is_active=category.is_active,
		created_at=category.created_at.isoformat(),
		updated_at=category.updated_at.isoformat(),
	)


async def category_product_count(db: AsyncSession, category_id: uuid.UUID) -> int:
	category_ids: list[uuid.UUID] = [category_id]
	queue: list[uuid.UUID] = [category_id]
	while queue:
		current_id = queue.pop(0)
		subcategories = await category_crud.get_categories_by_parent_id(db, current_id)
		for subcategory in subcategories:
			category_ids.append(subcategory.id)
			queue.append(subcategory.id)

	count = 0
	for cat_id in category_ids:
		count += await product_crud.count_products_in_category(db, cat_id)
	return count


async def get_categories_flat(db: AsyncSession) -> list[CategoryRef]:
	categories_map = await category_crud.get_all_categories_map(db)
	return [
		build_category_ref(category.id, categories_map)
		for category in categories_map.values()
	]


async def get_categories_tree(db: AsyncSession) -> list[CategoryTreeNode]:
	cached = _load_tree_cache()
	if cached is not None:
		return cached

	async with _get_cache_lock():
		cached = _load_tree_cache()
		if cached is not None:
			return cached

		result = await _build_categories_tree(db)
		_save_tree_cache(result)
		return result


async def _build_categories_tree(db: AsyncSession) -> list[CategoryTreeNode]:
	root_categories = await category_crud.get_categories_by_parent_id(db, None)
	if not root_categories:
		raise CategoryNotFoundError("No root category found")

	return [
		await _build_tree_node(db, root, path=[root.name], level=0)
		for root in root_categories
	]


async def _build_tree_node(
	db: AsyncSession,
	category: Category,
	*,
	path: list[str],
	level: int,
) -> CategoryTreeNode:
	subcategories = await category_crud.get_categories_by_parent_id(db, category.id)
	children: list[CategoryTreeNode] = []
	for subcategory in subcategories:
		child_path = [*path, subcategory.name]
		children.append(
			await _build_tree_node(
				db,
				subcategory,
				path=child_path,
				level=level + 1,
			)
		)

	return CategoryTreeNode(
		id=category.id,
		name=category.name,
		parent_id=category.parent_id,
		level=level,
		path=path,
		children=children,
	)


async def invalidate_categories_tree_cache(db: AsyncSession) -> None:
	"""Invalidate and rebuild the categories tree cache. Call this when categories are modified."""
	async with _get_cache_lock():
		if CATEGORIES_TREE_CACHE_FILE.exists():
			try:
				os.remove(CATEGORIES_TREE_CACHE_FILE)  # noqa
			except Exception as e:  # noqa
				print(f"Failed to remove cache file: {e}")

		try:
			result = await _build_categories_tree(db)
			_save_tree_cache(result)
			print("Categories tree cache rebuilt successfully")
		except Exception as e:  # noqa
			print(f"Failed to rebuild cache: {e}")


async def get_category_filters(db: AsyncSession, category_id: str) -> FilterResponse:
	id: uuid.UUID = uuid.UUID(category_id)

	category = await category_crud.get_category_by_id(db, id)
	if not category:
		raise CategoryNotFoundError(f"Category with id {id} not found")

	filters = await category_crud.get_category_filters(db, id)

	filters_schemas = [
		Filter(
			id=filter.id,
			slug=filter.slug,
			name=filter.name,
			type=filter.type,
			value=await category_crud.get_filter_values(db, filter.id)
			if filter.type == "LIST"
			else None,
			min=filter.min,
			max=filter.max,
		)
		for filter in filters
	]

	return FilterResponse(items=filters_schemas)


async def get_category_facets(
	db: AsyncSession,
	category_id: uuid.UUID,
	filters: str | None = None,
) -> FacetsResponse:
	from database.models.catalog.base import FilterTypeEnum

	# Возвращает список фасетов (фильтров) для указанной категории и для каждого значения — количество товаров (count), соответствующих этому значению при текущих применённых фильтрах. Вызывается при загрузке страницы категории и при каждом изменении фильтров на клиенте (чтобы обновить счётчики рядом с опциями фильтров).
	category = await category_crud.get_category_by_id(db, category_id)
	if not category:
		raise CategoryNotFoundError(f"Category with id {category_id} not found")

	applied_filters = json.loads(filters) if filters else None

	available_filters = await category_crud.get_category_filters(db, category_id)

	filters_list = []
	for filter_item in available_filters:
		filter_values = None
		if filter_item.type == FilterTypeEnum.LIST:
			filter_values = await category_crud.get_filter_values(db, filter_item.id)

		filters_list.append(
			Filter(
				id=filter_item.id,
				slug=filter_item.slug,
				name=filter_item.name,
				type=filter_item.type,
				value=filter_values,
				min=filter_item.min,
				max=filter_item.max,
			)
		)

	facets: list[Facet] = []
	for filter_item in available_filters:
		facet_values: list[FacetValue] = []
		if filter_item.type == FilterTypeEnum.LIST:
			filter_values = await category_crud.get_filter_values(db, filter_item.id)
			for value in filter_values:
				count = await product_crud.count_products_by_filter(
					db, category_id, filter_item.id, value, applied_filters
				)
				facet_values.append(FacetValue(value=value, count=count))
		facets.append(Facet(name=filter_item.name, values=facet_values))

	return FacetsResponse(
		category_id=str(category_id), filters=filters_list, facets=facets
	)


async def get_category_breadcrumbs(
	db: AsyncSession, category_id: str | None, product_id: str | None
) -> BreadcrumbResponse:
	if not category_id and not product_id:
		raise ValueError("Either category_id or product_id must be provided")

	if category_id and product_id:
		raise ValueError("Only one of category_id or product_id should be provided")

	resolved_via = ResolveViaEnum.PRODUCT if product_id else ResolveViaEnum.CATEGORY

	resolved_category_id: uuid.UUID
	if product_id:
		resolved_category_id = await product_crud.get_product_category_id(
			db, uuid.UUID(product_id)
		)
	else:
		resolved_category_id = uuid.UUID(category_id)

	current = await category_crud.get_category_by_id(db, resolved_category_id)
	if not current:
		raise CategoryNotFoundError(
			f"Category with id {resolved_category_id} not found"
		)

	chain: list[Category] = [current]
	while chain[-1].parent_id:
		parent_id = chain[-1].parent_id
		parent = await category_crud.get_category_by_id(db, parent_id)
		if not parent:
			raise CategoryHierarchyError(
				f"Category with id {resolved_category_id} has missing parent {parent_id}"
			)
		chain.append(parent)

	path = list(reversed(chain))
	url_parts: list[str] = []
	items: list[BreadcrumbItem] = []
	for idx, cat in enumerate(path, start=1):
		url_parts.append(cat.slug)
		items.append(
			BreadcrumbItem(
				id=cat.id,
				slug=cat.slug,
				name=cat.name,
				url="/".join(url_parts),
				level=idx,
				is_current=(idx == len(path)),
			)
		)

	return BreadcrumbResponse(
		data=items,
		meta=BreadcrumbMeta(
			resolved_via=resolved_via,
			category_id=resolved_category_id,
			product_id=uuid.UUID(product_id) if product_id else None,
		),
	)
