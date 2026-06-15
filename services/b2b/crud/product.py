from datetime import datetime
from enum import Enum
from uuid import UUID

from crud import outbox as outbox_crud
from database.models.catalog.base import Product, ProductStatusEnum
from database.models.catalog.variants import (
	Characteristic,
	Image,
	ImageEntityTypeEnum,
	Sku,
)
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


async def submit_for_moderation(
	db: AsyncSession,
	product: Product,
	event: str = "CREATED",
	json_before: dict | None = None,
) -> None:
	product.status = ProductStatusEnum.ON_MODERATION
	db.add(product)
	await db.flush()
	json_after = await build_product_snapshot(db, product)
	await outbox_crud.enqueue_moderation_product_event(
		db,
		product_id=product.id,
		seller_id=product.seller_id,
		event=event,
		json_before=json_before,
		json_after=json_after,
	)


def _json_value(value: object) -> object:
	if isinstance(value, UUID):
		return str(value)
	if isinstance(value, datetime):
		return value.isoformat()
	if isinstance(value, Enum):
		return value.value
	return value


async def build_product_snapshot(db: AsyncSession, product: Product) -> dict:
	await db.flush()
	skus_result = await db.execute(
		select(Sku).where(Sku.product_id == product.id).order_by(Sku.created_at, Sku.id)
	)
	skus = list(skus_result.scalars().all())
	sku_ids = [sku.id for sku in skus]

	characteristics_result = await db.execute(
		select(Characteristic)
		.where(
			or_(
				Characteristic.product_id == product.id,
				Characteristic.sku_id.in_(sku_ids),
			)
		)
		.order_by(Characteristic.name, Characteristic.value, Characteristic.id)
	)
	characteristics = list(characteristics_result.scalars().all())
	product_characteristics = [
		{"name": item.name, "value": item.value}
		for item in characteristics
		if item.product_id == product.id and item.sku_id is None
	]
	sku_characteristics: dict[UUID, list[dict[str, str]]] = {}
	for item in characteristics:
		if item.sku_id is not None:
			sku_characteristics.setdefault(item.sku_id, []).append(
				{"name": item.name, "value": item.value}
			)

	images_result = await db.execute(
		select(Image)
		.where(
			or_(
				and_(
					Image.entity_type == ImageEntityTypeEnum.PRODUCT,
					Image.entity_id == product.id,
				),
				and_(
					Image.entity_type == ImageEntityTypeEnum.SKU,
					Image.entity_id.in_(sku_ids),
				),
			)
		)
		.order_by(Image.ordering, Image.id)
	)
	images = list(images_result.scalars().all())
	product_images = [
		{"url": image.url, "ordering": image.ordering}
		for image in images
		if image.entity_type == ImageEntityTypeEnum.PRODUCT
		and image.entity_id == product.id
	]
	sku_images: dict[UUID, list[dict[str, object]]] = {}
	for image in images:
		if image.entity_type == ImageEntityTypeEnum.SKU:
			sku_images.setdefault(image.entity_id, []).append(
				{"url": image.url, "ordering": image.ordering}
			)

	return {
		"id": str(product.id),
		"seller_id": str(product.seller_id),
		"category_id": str(product.category_id),
		"title": product.title,
		"slug": product.slug,
		"description": product.description,
		"status": product.status.value,
		"deleted": product.deleted,
		"images": product_images,
		"characteristics": product_characteristics,
		"skus": [
			{
				"id": str(sku.id),
				"product_id": str(sku.product_id),
				"name": sku.name,
				"price": sku.price,
				"discount": sku.discount,
				"cost_price": sku.cost_price,
				"stock_quantity": sku.stock_quantity,
				"active_quantity": sku.active_quantity,
				"reserved_quantity": sku.reserved_quantity,
				"article": sku.article or None,
				"images": sku_images.get(sku.id, []),
				"characteristics": sku_characteristics.get(sku.id, []),
				"created_at": _json_value(sku.created_at),
				"updated_at": _json_value(sku.updated_at),
			}
			for sku in skus
		],
		"created_at": _json_value(product.created_at),
		"updated_at": _json_value(product.updated_at),
	}


async def add_product(
	product: Product,
	db: AsyncSession,
	images: list[dict],
	characteristics: list[dict],
) -> tuple[Product, list[Image], list[Characteristic]]:
	db.add(product)
	await db.flush()

	product_images = [
		Image(
			entity_type=ImageEntityTypeEnum.PRODUCT,
			entity_id=product.id,
			url=image["url"],
			ordering=image["ordering"],
		)
		for image in images
	]
	product_characteristics = [
		Characteristic(
			product_id=product.id,
			name=characteristic["name"],
			value=characteristic["value"],
		)
		for characteristic in characteristics
	]
	db.add_all([*product_images, *product_characteristics])
	await db.commit()
	await db.refresh(product)
	for image in product_images:
		await db.refresh(image)
	for characteristic in product_characteristics:
		await db.refresh(characteristic)
	return product, product_images, product_characteristics


async def get_seller_products(
	db: AsyncSession,
	seller_id: UUID,
	status: ProductStatusEnum | None = None,
	search: str | None = None,
	limit: int = 20,
	offset: int = 0,
	include_deleted: bool = True,
) -> tuple[list[tuple[Product, int, int]], int]:
	sku_aggregates = (
		select(
			Sku.product_id.label("product_id"),
			func.count(Sku.id).label("skus_count"),
			func.sum(Sku.active_quantity).label("total_active_quantity"),
		)
		.group_by(Sku.product_id)
		.subquery()
	)
	query = (
		select(
			Product,
			func.coalesce(sku_aggregates.c.skus_count, 0),
			func.coalesce(sku_aggregates.c.total_active_quantity, 0),
		)
		.outerjoin(sku_aggregates, Product.id == sku_aggregates.c.product_id)
		.where(Product.seller_id == seller_id)
		.order_by(Product.created_at.desc(), Product.id.desc())
	)
	count_query = select(func.count(Product.id)).where(Product.seller_id == seller_id)
	if status is not None:
		query = query.where(Product.status == status)
		count_query = count_query.where(Product.status == status)
	if not include_deleted:
		query = query.where(Product.deleted.is_(False))
		count_query = count_query.where(Product.deleted.is_(False))
	if search:
		escaped = (
			search.strip().replace("/", "//").replace("%", "/%").replace("_", "/_")
		)
		if escaped:
			search_condition = Product.title.ilike(f"%{escaped}%", escape="/")
			query = query.where(search_condition)
			count_query = count_query.where(search_condition)

	total_count = int((await db.execute(count_query)).scalar() or 0)
	result = await db.execute(query.offset(offset).limit(limit))
	rows = [(product, int(count), int(total)) for product, count, total in result.all()]
	return rows, total_count


async def get_product_by_id(
	db: AsyncSession, product_id: UUID, seller_id: UUID
) -> Product | None:
	result = await db.execute(
		select(Product).where(Product.id == product_id, Product.seller_id == seller_id)
	)
	return result.scalar_one_or_none()


async def get_product_by_id_only(
	db: AsyncSession,
	product_id: UUID,
	*,
	for_update: bool = False,
) -> Product | None:
	query = select(Product).where(Product.id == product_id)
	if for_update:
		query = query.with_for_update()
	result = await db.execute(query)
	return result.scalar_one_or_none()


async def get_product_characteristics(
	db: AsyncSession, product_id: UUID
) -> list[Characteristic]:
	result = await db.execute(
		select(Characteristic).where(
			Characteristic.product_id == product_id,
			Characteristic.sku_id.is_(None),
		)
	)
	return list(result.scalars().all())


async def get_product_characteristics_for_products(
	db: AsyncSession, product_ids: list[UUID]
) -> dict[UUID, list[Characteristic]]:
	if not product_ids:
		return {}
	result = await db.execute(
		select(Characteristic).where(
			Characteristic.product_id.in_(product_ids),
			Characteristic.sku_id.is_(None),
		)
	)
	grouped: dict[UUID, list[Characteristic]] = {}
	for characteristic in result.scalars().all():
		if characteristic.product_id is not None:
			grouped.setdefault(characteristic.product_id, []).append(characteristic)
	return grouped


async def update_product(
	db: AsyncSession,
	db_obj: Product,
	update_data: dict,
	should_remoderate: bool = False,
) -> Product:
	json_before = (
		await build_product_snapshot(db, db_obj) if should_remoderate else None
	)
	characteristics = update_data.pop("characteristics", None)
	for field, value in update_data.items():
		setattr(db_obj, field, value)

	db.add(db_obj)
	if characteristics is not None:
		await db.execute(
			delete(Characteristic).where(
				Characteristic.product_id == db_obj.id,
				Characteristic.sku_id.is_(None),
			)
		)
		db.add_all(
			[
				Characteristic(
					product_id=db_obj.id,
					name=characteristic["name"],
					value=characteristic["value"],
				)
				for characteristic in characteristics
			]
		)
	if should_remoderate:
		await submit_for_moderation(
			db,
			db_obj,
			event="EDITED",
			json_before=json_before,
		)

	await db.commit()
	await db.refresh(db_obj)
	return db_obj


async def soft_delete_product(
	db: AsyncSession,
	db_obj: Product,
	sku_ids: list[UUID],
) -> Product:
	db_obj.deleted = True
	db.add(db_obj)
	await outbox_crud.enqueue_product_deleted_events(
		db,
		product_id=db_obj.id,
		seller_id=db_obj.seller_id,
		sku_ids=sku_ids,
	)
	await db.commit()
	await db.refresh(db_obj)
	return db_obj


async def hard_delete_product(db: AsyncSession, db_obj: Product) -> None:
	await db.delete(db_obj)
	await db.commit()
