import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models.catalog.base import (
	Category,
	CategoryFilters,
	FilterTypeEnum,
	FilterValues,
	Product,
	ProductStatusEnum,
)
from database.models.catalog.variants import Sku
from tests.factories.catalog import (
	CategoryFactory,
	CategoryFiltersFactory,
	FilterValuesFactory,
	ProductFactory,
	SkuFactory,
)


def _fixed_uuid() -> uuid.UUID:
	return uuid.uuid4()


@dataclass(frozen=True, slots=True)
class CategoriesTreeData:
	root: Category
	child: Category
	grandchild: Category


@dataclass(frozen=True, slots=True)
class MultipleRootCategoriesData:
	root_a: Category
	root_b: Category


@pytest.fixture()
async def categories_tree(
	db_session: AsyncSession,
) -> CategoriesTreeData:
	"""
	Create categories tree test data.
	"""
	root = CategoryFactory.build(
		id=_fixed_uuid(), parent_id=None, name="Электроника", slug="electronics"
	)
	child = CategoryFactory.build(
		id=_fixed_uuid(), parent_id=root.id, name="Смартфоны", slug="smartphones"
	)
	grandchild = CategoryFactory.build(
		id=_fixed_uuid(), parent_id=child.id, name="Android", slug="android"
	)

	db_session.add_all([root, child, grandchild])
	await db_session.commit()
	return CategoriesTreeData(root=root, child=child, grandchild=grandchild)


@pytest.fixture()
async def multiple_root_categories(
	db_session: AsyncSession,
) -> MultipleRootCategoriesData:
	root_a = CategoryFactory.build(
		id=_fixed_uuid(), parent_id=None, name="Электроника", slug="electronics"
	)
	root_b = CategoryFactory.build(
		id=_fixed_uuid(), parent_id=None, name="Одежда", slug="clothing"
	)
	db_session.add_all([root_a, root_b])
	await db_session.commit()
	return MultipleRootCategoriesData(root_a=root_a, root_b=root_b)


@dataclass(frozen=True, slots=True)
class OrphanCategoryData:
	orphan: Category
	missing_parent_id: uuid.UUID


@pytest.fixture()
async def orphan_category(
	db_session: AsyncSession,
) -> OrphanCategoryData:
	"""
	Create orphan category test data.
	Sets session replication role to replica to avoid foreign key constraints errors. Needs for orphan category.
	"""
	missing_parent_id = _fixed_uuid()
	await db_session.execute(text("SET session_replication_role = replica"))
	orphan = CategoryFactory.build(
		id=_fixed_uuid(),
		parent_id=missing_parent_id,
		name="Orphan",
		slug="orphan",
	)
	db_session.add(orphan)
	await db_session.commit()
	await db_session.execute(text("SET session_replication_role = DEFAULT"))
	await db_session.commit()
	return OrphanCategoryData(orphan=orphan, missing_parent_id=missing_parent_id)


@dataclass(frozen=True, slots=True)
class CategoryWithProductsData:
	category: Category
	filters: tuple[CategoryFilters, CategoryFilters]
	values: tuple[FilterValues, FilterValues]
	products: tuple[Product, Product]


@pytest.fixture()
async def category_with_products(
	db_session: AsyncSession,
) -> CategoryWithProductsData:
	"""
	Create category with filters test data.
	"""
	category = CategoryFactory.build(
		id=_fixed_uuid(),
		name="Category with Filters",
		slug="category-with-filters",
	)
	filter_1 = CategoryFiltersFactory.build(
		id=_fixed_uuid(),
		category_id=category.id,
		name="Filter 1",
		slug="filter-1",
		type=FilterTypeEnum.LIST,
		value="Value 1",
	)
	filter_2 = CategoryFiltersFactory.build(
		id=_fixed_uuid(),
		category_id=category.id,
		name="Filter 2",
		slug="filter-2",
		type=FilterTypeEnum.LIST,
		value="Value 2",
	)
	filter_value_1 = FilterValuesFactory.build(
		id=_fixed_uuid(), filter_id=filter_1.id, value="Value 1"
	)
	filter_value_2 = FilterValuesFactory.build(
		id=_fixed_uuid(), filter_id=filter_2.id, value="Value 2"
	)
	product_1 = ProductFactory.build(
		id=_fixed_uuid(),
		category_id=category.id,
		title="Product 1",
		slug="product-1",
		description="Description 1",
	)
	product_2 = ProductFactory.build(
		id=_fixed_uuid(),
		category_id=category.id,
		title="Product 2",
		slug="product-2",
		description="Description 1",
	)

	sku_1 = Sku(
		id=_fixed_uuid(),
		product_id=product_1.id,
		name="Sku 1",
		price=100,
		active_quantity=1,
	)
	sku_2 = Sku(
		id=_fixed_uuid(),
		product_id=product_2.id,
		name="Sku 2",
		price=100,
		active_quantity=1,
	)

	db_session.add_all(
		[
			category,
			filter_1,
			filter_2,
			filter_value_1,
			filter_value_2,
			product_1,
			product_2,
			sku_1,
			sku_2,
		]
	)
	await db_session.commit()
	return CategoryWithProductsData(
		category=category,
		filters=(filter_1, filter_2),
		values=(filter_value_1, filter_value_2),
		products=(product_1, product_2),
	)


@dataclass(frozen=True, slots=True)
class OtherCategoryWithProductData:
	category: Category
	product: Product


@pytest.fixture()
async def other_category_with_product(
	db_session: AsyncSession,
) -> OtherCategoryWithProductData:
	"""A second category with its own visible, in-stock product.

	Used alongside ``category_with_products`` to assert that filtering by
	``category_id`` isolates results to the requested category.
	"""
	category = CategoryFactory.build(
		id=_fixed_uuid(),
		name="Other Category",
		slug="other-category",
	)
	product = ProductFactory.build(
		id=_fixed_uuid(),
		category_id=category.id,
		title="Other Product",
		slug="other-product",
		description="Other description",
		status=ProductStatusEnum.MODERATED,
	)
	sku = Sku(
		id=_fixed_uuid(),
		product_id=product.id,
		name="Other Sku",
		price=100,
		active_quantity=1,
	)
	db_session.add_all([category, product, sku])
	await db_session.commit()
	return OtherCategoryWithProductData(category=category, product=product)


@dataclass(frozen=True, slots=True)
class VisibilityProductsData:
	category: Category
	visible_product: Product
	hidden_by_status_product: Product
	hidden_by_stock_product: Product


@pytest.fixture()
async def visibility_products(
	db_session: AsyncSession,
	category_with_products: CategoryWithProductsData,
) -> VisibilityProductsData:
	hidden_by_status = category_with_products.products[0]
	hidden_by_status.status = ProductStatusEnum.CREATED

	hidden_by_stock = category_with_products.products[1]
	existing_skus = (
		(
			await db_session.execute(
				select(Sku).where(Sku.product_id == hidden_by_stock.id)
			)
		)
		.scalars()
		.all()
	)
	for sku in existing_skus:
		sku.active_quantity = 0

	visible_product = ProductFactory.build(
		id=_fixed_uuid(),
		category_id=category_with_products.category.id,
		title="Visible product",
		slug="visible-product",
		description="Visible",
		status=ProductStatusEnum.MODERATED,
	)
	visible_sku = Sku(
		id=_fixed_uuid(),
		product_id=visible_product.id,
		name="Visible sku",
		price=100,
		active_quantity=1,
	)

	db_session.add_all([visible_product, visible_sku])
	await db_session.commit()

	return VisibilityProductsData(
		category=category_with_products.category,
		visible_product=visible_product,
		hidden_by_status_product=hidden_by_status,
		hidden_by_stock_product=hidden_by_stock,
	)


@dataclass(frozen=True, slots=True)
class SimilarProductsData:
	category: Category
	base_product: Product
	similar_products: tuple[Product, ...]
	other_category: Category
	other_products: tuple[Product, ...]


def _add_product_with_sku(
	products: list,
	skus: list,
	*,
	category_id: uuid.UUID,
	status: ProductStatusEnum = ProductStatusEnum.MODERATED,
	active_quantity: int = 10,
) -> Product:
	product = ProductFactory.build(
		id=_fixed_uuid(),
		category_id=category_id,
		status=status,
	)
	skus.append(
		SkuFactory.build(product_id=product.id, active_quantity=active_quantity)
	)
	products.append(product)
	return product


@pytest.fixture()
async def one_product_category(db_session: AsyncSession) -> SimilarProductsData:
	category = CategoryFactory.build(
		id=_fixed_uuid(),
		parent_id=None,
	)
	other_category = CategoryFactory.build(
		id=_fixed_uuid(),
		parent_id=None,
	)
	products: list = []
	skus: list = []
	product = _add_product_with_sku(products, skus, category_id=category.id)
	db_session.add_all([category, other_category, *products, *skus])
	await db_session.commit()
	return SimilarProductsData(
		category=category,
		base_product=product,
		similar_products=(),
		other_category=other_category,
		other_products=(),
	)


@pytest.fixture()
async def similar_products_data(db_session: AsyncSession) -> SimilarProductsData:
	category = CategoryFactory.build(
		id=_fixed_uuid(),
		parent_id=None,
	)
	other_category = CategoryFactory.build(
		id=_fixed_uuid(),
		parent_id=None,
	)

	products: list[Product] = []
	skus: list = []
	base_product = _add_product_with_sku(products, skus, category_id=category.id)

	similar_products: list[Product] = []
	for _ in range(10):
		similar_products.append(
			_add_product_with_sku(products, skus, category_id=category.id)
		)

	other_products: list[Product] = []
	for _ in range(2):
		other_products.append(
			_add_product_with_sku(products, skus, category_id=other_category.id)
		)

	db_session.add_all([category, other_category, *products, *skus])
	await db_session.commit()

	return SimilarProductsData(
		category=category,
		base_product=base_product,
		similar_products=tuple(similar_products),
		other_category=other_category,
		other_products=tuple(other_products),
	)


@dataclass(frozen=True, slots=True)
class ProductData:
	base_product: Product
	skus: tuple[Sku, ...]


@pytest.fixture()
async def products_data(db_session: AsyncSession) -> ProductData:
	category = CategoryFactory.build(
		id=_fixed_uuid(),
		parent_id=None,
	)
	products: list[Product] = []
	for _ in range(15):
		products.append(
			ProductFactory.build(
				id=_fixed_uuid(),
				category_id=category.id,
				status=ProductStatusEnum.MODERATED,
			)
		)
	db_session.add_all([category, *products])
	await db_session.commit()

	sku_1 = Sku(
		id=_fixed_uuid(),
		product_id=products[0].id,
		name="sku1",
		price=100,
		active_quantity=1,
	)
	sku_2 = Sku(
		id=_fixed_uuid(),
		product_id=products[0].id,
		name="sku2",
		price=200,
		active_quantity=1,
	)
	db_session.add_all([sku_1, sku_2])
	await db_session.commit()

	stmt = (
		select(Product)
		.where(Product.id == products[0].id)
		.options(selectinload(Product.images), selectinload(Product.skus))
	)
	base_product = (await db_session.execute(stmt)).scalar_one()
	return ProductData(base_product=base_product, skus=tuple(base_product.skus))


@pytest.fixture()
async def blocked_product_data(db_session: AsyncSession) -> ProductData:
	category = CategoryFactory.build(
		id=_fixed_uuid(),
		parent_id=None,
	)
	product = ProductFactory.build(
		id=_fixed_uuid(),
		category_id=category.id,
		status=ProductStatusEnum.BLOCKED,
	)
	db_session.add_all([category, product])
	await db_session.commit()
	stmt = (
		select(Product)
		.where(Product.id == product.id)
		.options(selectinload(Product.images), selectinload(Product.skus))
	)
	base_product = (await db_session.execute(stmt)).scalar_one()
	return ProductData(base_product=base_product, skus=tuple(base_product.skus))


@pytest.fixture()
async def product_skus_out_of_stock_data(db_session: AsyncSession) -> ProductData:
	category = CategoryFactory.build(
		id=_fixed_uuid(),
		parent_id=None,
	)
	product = ProductFactory.build(
		id=_fixed_uuid(),
		category_id=category.id,
		status=ProductStatusEnum.MODERATED,
	)
	db_session.add_all([category, product])
	await db_session.commit()

	sku = Sku(
		id=_fixed_uuid(),
		product_id=product.id,
		name="sku",
		price=100,
		active_quantity=0,
	)
	db_session.add(sku)
	await db_session.commit()
	stmt = (
		select(Product)
		.where(Product.id == product.id)
		.options(selectinload(Product.images), selectinload(Product.skus))
	)
	base_product = (await db_session.execute(stmt)).scalar_one()
	return ProductData(base_product=base_product, skus=tuple(base_product.skus))
