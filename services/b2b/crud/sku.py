from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from crud import images as images_crud
from crud import product as product_crud
from database.models import Characteristic, Sku
from database.models.catalog.base import Product
from database.models.catalog.variants import Image, ImageEntityTypeEnum


async def create(
	db: AsyncSession,
	data: dict,
	product: Product,
	images: list[dict] | None = None,
	moderation_event: str | None = None,
	json_before: dict | None = None,
) -> Sku:
	chars_data = data.pop("characteristics", []) or []
	data.pop("images", None)
	data.pop("product_id", None)

	sku = Sku(product_id=product.id, **data)
	db.add(sku)
	await db.flush()

	for char in chars_data:
		char_fields = {"name": char["name"], "value": char["value"]}
		db.add(Characteristic(**char_fields, sku_id=sku.id))

	for image in images or []:
		await images_crud.attach_sku_image(
			db,
			sku.id,
			image["url"],
			image.get("ordering", 0),
		)

	if moderation_event is not None:
		await product_crud.submit_for_moderation(
			db,
			product,
			event=moderation_event,
			json_before=json_before,
		)

	await db.commit()
	return await get_sku_by_id(db, sku.id)


async def get_sku_by_id(db: AsyncSession, sku_id: UUID) -> Sku | None:
	result = await db.execute(
		select(Sku).options(joinedload(Sku.characteristics)).where(Sku.id == sku_id)
	)
	return result.unique().scalar_one_or_none()


async def get_sku_and_product(
	db: AsyncSession, sku_id: UUID
) -> tuple[Sku, Product] | None:
	sku = await get_sku_by_id(db, sku_id)
	if sku is None:
		return None
	product = await product_crud.get_product_by_id_only(db, sku.product_id)
	if product is None:
		return None
	return sku, product


async def get_sku_and_product_for_update(
	db: AsyncSession, sku_id: UUID
) -> tuple[Sku, Product] | None:
	result = await db.execute(
		select(Sku, Product)
		.join(Product, Product.id == Sku.product_id)
		.where(Sku.id == sku_id)
		.with_for_update()
	)
	row = result.one_or_none()
	if row is None:
		return None
	sku, product = row
	return sku, product


async def delete_sku(db: AsyncSession, sku: Sku) -> None:
	await db.execute(
		delete(Image).where(
			Image.entity_type == ImageEntityTypeEnum.SKU,
			Image.entity_id == sku.id,
		)
	)
	await db.delete(sku)
	await db.flush()


async def attach_sku_image(
	db: AsyncSession,
	sku: Sku,
	url: str,
	ordering: int,
) -> Image:
	image = await images_crud.attach_sku_image(db, sku.id, url, ordering)
	await db.commit()
	await db.refresh(image)
	return image


async def get_by_product_id(db: AsyncSession, product_id: UUID) -> list[Sku]:
	result = await db.execute(
		select(Sku)
		.options(joinedload(Sku.characteristics))
		.where(Sku.product_id == product_id)
	)
	return list(result.unique().scalars().all())


async def update(
	db: AsyncSession,
	sku_id: UUID,
	data: dict,
	product: Product | None = None,
	should_remoderate: bool = False,
) -> Sku | None:
	sku = await get_sku_by_id(db, sku_id)
	if not sku:
		return None

	data.pop("product_id", None)
	characteristics = data.pop("characteristics", None)
	data.pop("images", None)
	data.pop("reserved_quantity", None)

	if should_remoderate and product is not None:
		json_before = await product_crud.build_product_snapshot(db, product)
	else:
		json_before = None

	for key, value in data.items():
		setattr(sku, key, value)

	if characteristics is not None:
		await db.execute(delete(Characteristic).where(Characteristic.sku_id == sku.id))
		db.add_all(
			[
				Characteristic(
					sku_id=sku.id,
					name=characteristic["name"],
					value=characteristic["value"],
				)
				for characteristic in characteristics
			]
		)
	if should_remoderate and product is not None:
		await product_crud.submit_for_moderation(
			db,
			product,
			event="EDITED",
			json_before=json_before,
		)

	await db.commit()
	await db.refresh(sku)
	if characteristics is not None:
		await db.refresh(sku, attribute_names=["characteristics"])
	return sku


async def count_skus_by_product_id(db: AsyncSession, product_id: UUID) -> int:
	result = await db.execute(
		select(func.count()).select_from(Sku).where(Sku.product_id == product_id)
	)
	return int(result.scalar_one())


async def load_images_for_sku(db: AsyncSession, sku_id: UUID) -> list[Image]:
	return await images_crud.get_sku_images_by_id(sku_id, db)
