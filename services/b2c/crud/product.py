import uuid
from collections import deque
from typing import List, Tuple, Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Sku
from database.models.catalog.base import Category, Product
from exceptions.product import ProductNotFoundError
from schemas.sku import Sku as SkuSchema
from database.models.catalog.base import ProductStatusEnum
from sqlalchemy import func as sql_func
from crud.category import get_category_by_id


async def get_category_descendants(
	db: AsyncSession, category_id: uuid.UUID
) -> list[uuid.UUID]:
	res = await db.execute(select(Category.id, Category.parent_id))
	cats = res.all()

	children_by_parent: dict[uuid.UUID | None, list[uuid.UUID]] = {}
	for child_id, parent_id in cats:
		children_by_parent.setdefault(parent_id, []).append(child_id)

	collected: list[uuid.UUID] = []
	seen: set[uuid.UUID] = set()
	queue = deque([category_id])

	while queue:
		current_id = queue.popleft()
		if current_id in seen:
			continue
		seen.add(current_id)
		collected.append(current_id)
		queue.extend(children_by_parent.get(current_id, []))

	return collected


async def count_products_in_category(db: AsyncSession, category_id: uuid.UUID) -> int:
	category_ids = await get_category_descendants(db, category_id)
	result = await db.execute(
		select(func.count(Product.id)).where(Product.category_id.in_(category_ids))
	)
	return result.scalar() or 0


async def get_product_skus(
	db: AsyncSession, product_id: uuid.UUID
) -> List[SkuSchema] | None:
	"""
	Returns a list of skus for a given product ID.
	:param db: database session
	:param product_id: product ID
	:return: list of skus or None if not found
	"""
	result = await db.execute(
		select(Sku)
		.where(Sku.product_id == product_id)
		.options(selectinload(Sku.images))
	)
	return list(result.scalars().all())


async def get_products_list(
	db: AsyncSession,
	limit: int,
	offset: int,
	category_id: Optional[uuid.UUID],
	filter: Optional[dict],
	sort: str,
	search: Optional[str],
) -> Tuple[List[Product], int]:
	query = select(Product).options(
		selectinload(Product.images),
		selectinload(Product.skus),
		selectinload(Product.seller),
	)
	count_query = select(func.count(func.distinct(Product.id)))

	# Условие видимости: status = MODERATED AND active_quantity > 0
	query = query.where(
		Product.status == ProductStatusEnum.MODERATED,
		Product.deleted == False,  # noqa
		Product.id.in_(select(Sku.product_id).where(Sku.active_quantity > 0)),
	)

	count_query = count_query.where(
		Product.status == ProductStatusEnum.MODERATED,
		Product.deleted == False,  # noqa
		Product.id.in_(select(Sku.product_id).where(Sku.active_quantity > 0)),
	)

	if category_id:
		category_ids = await get_category_descendants(db, category_id)
		query = query.where(Product.category_id.in_(category_ids))
		count_query = count_query.where(Product.category_id.in_(category_ids))

	if filter:
		for key, value in filter.items():
			column = getattr(Product, key, None)
			if column is not None:
				query = query.where(column == value)
				count_query = count_query.where(column == value)

	if search:
		search_val = search.strip()
		if len(search_val) >= 4:
			escaped_search = (
				search_val.replace("/", "//").replace("%", "/%").replace("_", "/_")
			)

			term = f"%{escaped_search}%"

			search_condition = or_(
				Product.title.ilike(term, escape="/"),
				Product.description.ilike(term, escape="/"),
			)

			query = query.where(search_condition)
			count_query = count_query.where(search_condition)

	match sort:
		case "price_asc" | "price_desc":
			min_price_subquery = (
				select(Sku.product_id, sql_func.min(Sku.price).label("min_price"))
				.group_by(Sku.product_id)
				.subquery()
			)
			query = query.outerjoin(
				min_price_subquery, Product.id == min_price_subquery.c.product_id
			)
			sort_column = (
				min_price_subquery.c.min_price.asc()
				if sort == "price_asc"
				else min_price_subquery.c.min_price.desc()
			)
			query = query.order_by(sort_column)
		case "popularity":
			query = query.order_by(Product.popularity.desc())
		case "new":
			query = query.order_by(Product.created_at.desc())
		case _:
			query = query.order_by(Product.created_at.desc())

	query = query.offset(offset).limit(limit)

	products = list((await db.execute(query)).scalars().all())
	total = (await db.execute(count_query)).scalar() or 0

	return products, total


async def get_product_full(db: AsyncSession, id: uuid.UUID) -> Optional[Product]:
	stmt = (
		select(Product)
		.where(
			Product.id == id,
			Product.status == ProductStatusEnum.MODERATED,
			Product.deleted == False,  # noqa: E712
		)
		.options(
			selectinload(Product.images),
			selectinload(Product.characteristics),
			selectinload(Product.skus).selectinload(Sku.images),
			selectinload(Product.skus).selectinload(Sku.characteristics),
		)
	)
	return (await db.execute(stmt)).scalar_one_or_none()


async def _fetch_similar_products_batch(
	db: AsyncSession,
	category_ids: list[uuid.UUID],
	exclude_ids: set[uuid.UUID],
	limit: int,
) -> list[Product]:
	if limit <= 0 or not category_ids:
		return []

	conditions = [
		Product.category_id.in_(category_ids),
		Product.status == ProductStatusEnum.MODERATED,
		Product.deleted == False,  # noqa: E712
		Product.id.in_(select(Sku.product_id).where(Sku.active_quantity > 0)),
	]
	if exclude_ids:
		conditions.append(Product.id.not_in(exclude_ids))

	query = (
		select(Product)
		.where(*conditions)
		.options(
			selectinload(Product.images),
			selectinload(Product.skus),
			selectinload(Product.seller),
		)
		.order_by(func.random())
		.limit(limit)
	)
	return list((await db.execute(query)).scalars().all())


async def get_similar_products(
	db: AsyncSession,
	category_id: uuid.UUID,
	exclude_id: uuid.UUID,
	limit: int,
) -> list[Product]:

	exclude_ids = {exclude_id}
	category_ids = await get_category_descendants(db, category_id)
	products = await _fetch_similar_products_batch(db, category_ids, exclude_ids, limit)
	exclude_ids.update(product.id for product in products)

	if len(products) < limit:
		category = await get_category_by_id(db, category_id)
		if category is not None and category.parent_id is not None:
			parent_category_ids = await get_category_descendants(db, category.parent_id)
			extra = await _fetch_similar_products_batch(
				db,
				parent_category_ids,
				exclude_ids,
				limit - len(products),
			)
			products.extend(extra)

	return products


async def get_product_category_id(db: AsyncSession, product_id: uuid.UUID) -> uuid.UUID:
	result = await db.execute(
		select(Product.category_id).where(Product.id == product_id)
	)
	category_id = result.scalar()
	if not category_id:
		raise ProductNotFoundError(f"Product with id {product_id} not found")
	return category_id


async def count_products_by_filter(
	db: AsyncSession,
	category_id: uuid.UUID,
	filter_id: uuid.UUID,
	filter_value: str,
	applied_filters: dict | None = None,
) -> int:
	"""
	Подсчитывает количество видимых товаров в категории с определённым значением фильтра.

	applied_filters — словарь текущих применённых фильтров (ключи — id или slug фильтра, значения — строка или список значений).
	При подсчёте для конкретного фильтра мы учитываем все остальные applied_filters (AND), но НЕ учитываем сам текущий фильтр.
	"""
	from database.models.catalog.base import (
		ProductStatusEnum,
		ProductFilterValue,
		FilterValues,
		CategoryFilters,
	)

	category_ids = await get_category_descendants(db, category_id)

	filter_value_result = await db.execute(
		select(FilterValues.id).where(
			FilterValues.filter_id == filter_id, FilterValues.value == filter_value
		)
	)
	filter_value_id = filter_value_result.scalar()

	if not filter_value_id:
		return 0

	extra_conditions = []
	if applied_filters:
		for key, val in applied_filters.items():
			if val is None or (isinstance(val, (list, str)) and val == ""):
				continue

			try:
				other_filter_id = uuid.UUID(key)
			except Exception:  # noqa
				other = await db.execute(
					select(CategoryFilters.id).where(
						CategoryFilters.slug == str(key),
						CategoryFilters.category_id == category_id,
					)
				)
				other_filter_id = other.scalar()

			if not other_filter_id:
				continue

			if str(other_filter_id) == str(filter_id):
				continue

			values = val if isinstance(val, list) else [val]

			res = await db.execute(
				select(FilterValues.id).where(
					FilterValues.filter_id == other_filter_id,
					FilterValues.value.in_(values),
				)
			)
			fv_ids = res.scalars().all()

			if not fv_ids:
				return 0

			extra_conditions.append(
				Product.id.in_(
					select(ProductFilterValue.product_id).where(
						ProductFilterValue.filter_value_id.in_(fv_ids)
					)
				)
			)

	result = await db.execute(
		select(func.count(func.distinct(Product.id))).where(
			Product.status == ProductStatusEnum.MODERATED,
			Product.deleted == False,  # noqa
			Product.category_id.in_(category_ids),
			Product.id.in_(select(Sku.product_id).where(Sku.active_quantity > 0)),
			Product.id.in_(
				select(ProductFilterValue.product_id).where(
					ProductFilterValue.filter_value_id == filter_value_id
				)
			),
			*extra_conditions,
		)
	)
	return result.scalar() or 0
