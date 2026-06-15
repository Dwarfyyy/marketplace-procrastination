from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from crud import outbox as outbox_crud
from crud import product as product_crud
from crud import sku as sku_crud
from database.models.catalog.base import ProductStatusEnum
from database.models.catalog.variants import Sku
from exceptions.product import ProductNotFoundError, ProductNotOwnerError
from exceptions.sku import (
	SkuActiveReservesError,
	SkuForbiddenError,
	SkuNotFoundError,
	SkuValidationError,
)
from schemas.sku import (
	CharacteristicSchema,
	ImageAttachRequest,
	ImageSchema,
	SkuCreate,
	SkuImageCreate,
	SkuImageResponse,
	SkuResponse,
)


async def build_sku_response(db: AsyncSession, sku: Sku) -> SkuResponse:
	images = await sku_crud.load_images_for_sku(db, sku.id)
	return SkuResponse(
		id=sku.id,
		product_id=sku.product_id,
		name=sku.name,
		price=sku.price,
		discount=sku.discount,
		cost_price=sku.cost_price,
		stock_quantity=sku.stock_quantity,
		active_quantity=sku.active_quantity,
		reserved_quantity=sku.reserved_quantity,
		article=sku.article or None,
		characteristics=[
			CharacteristicSchema.model_validate(c) for c in sku.characteristics
		],
		images=[ImageSchema.model_validate(img) for img in images],
		created_at=sku.created_at,
		updated_at=sku.updated_at,
	)


async def _get_owned_sku(db: AsyncSession, sku_id: UUID, seller_id: UUID) -> tuple:
	pair = await sku_crud.get_sku_and_product(db, sku_id)
	if pair is None:
		raise SkuNotFoundError(f"SKU with id {sku_id} not found")

	sku, product = pair
	if product.seller_id != seller_id:
		raise ProductNotOwnerError("SKU does not belong to the authenticated seller")
	if product.status == ProductStatusEnum.HARD_BLOCKED:
		raise SkuForbiddenError("Cannot modify SKU of hard-blocked product")

	return sku, product


def _process_sku_images(images: list[SkuImageCreate]) -> list[dict]:
	normalized: list[dict] = []
	for image in images:
		url = image.url.strip()
		if not url:
			raise SkuValidationError("Each image must have a non-empty url")
		normalized.append({"url": url, "ordering": image.ordering})
	return normalized


async def create_sku(db: AsyncSession, data: SkuCreate, seller_id: UUID) -> SkuResponse:
	# Serialize SKU creation for a product so only one concurrent request can
	# observe that it is creating the first SKU.
	product = await product_crud.get_product_by_id_only(
		db,
		data.product_id,
		for_update=True,
	)
	if not product:
		raise ProductNotFoundError(f"Product with id {data.product_id} not found")
	if product.seller_id != seller_id:
		raise ProductNotOwnerError(
			"Product does not belong to the authenticated seller"
		)
	if product.status == ProductStatusEnum.HARD_BLOCKED:
		raise SkuForbiddenError("Cannot add SKU to hard-blocked product")
	if data.price <= 0:
		raise SkuValidationError("price must be a positive integer")

	sku_images = _process_sku_images(data.images)
	is_first_sku = await sku_crud.count_skus_by_product_id(db, product.id) == 0

	moderation_event = None
	if is_first_sku and product.status == ProductStatusEnum.CREATED:
		moderation_event = "CREATED"
	elif product.status in (
		ProductStatusEnum.MODERATED,
		ProductStatusEnum.BLOCKED,
	):
		moderation_event = "EDITED"

	if moderation_event == "CREATED" and not sku_images:
		raise SkuValidationError("at least one image is required for the first SKU")

	json_before = (
		await product_crud.build_product_snapshot(db, product)
		if moderation_event == "EDITED"
		else None
	)

	sku_payload = data.model_dump()
	sku_payload["cost_price"] = (
		sku_payload.get("cost_price")
		if sku_payload.get("cost_price") is not None
		else 0
	)
	sku_payload["article"] = sku_payload.get("article") or ""

	sku = await sku_crud.create(
		db,
		sku_payload,
		product=product,
		images=sku_images,
		moderation_event=moderation_event,
		json_before=json_before,
	)
	return await build_sku_response(db, sku)


async def attach_sku_image(
	db: AsyncSession, sku_id: UUID, data: ImageAttachRequest, seller_id: UUID
) -> SkuImageResponse:
	url = data.url.strip()
	if not url:
		raise SkuValidationError("url is required")

	sku, _ = await _get_owned_sku(db, sku_id, seller_id)

	image = await sku_crud.attach_sku_image(
		db,
		sku,
		url,
		data.ordering,
	)
	return SkuImageResponse.model_validate(image)


async def get_sku(db: AsyncSession, sku_id: UUID, seller_id: UUID) -> SkuResponse:
	sku, _ = await _get_owned_sku(db, sku_id, seller_id)
	return await build_sku_response(db, sku)


async def update_sku(
	db: AsyncSession, sku_id: UUID, data: dict, seller_id: UUID
) -> SkuResponse:
	_, product = await _get_owned_sku(db, sku_id, seller_id)
	submit_for_remoderation = product.status in [
		ProductStatusEnum.BLOCKED,
		ProductStatusEnum.MODERATED,
	]

	updated = await sku_crud.update(
		db,
		sku_id,
		data,
		product=product,
		should_remoderate=submit_for_remoderation,
	)
	if not updated:
		raise SkuNotFoundError(f"SKU with id {sku_id} not found")
	return await build_sku_response(db, updated)


async def delete_sku(db: AsyncSession, sku_id: UUID, seller_id: UUID) -> None:
	pair = await sku_crud.get_sku_and_product_for_update(db, sku_id)
	if pair is None:
		raise SkuNotFoundError(f"SKU with id {sku_id} not found")

	sku, product = pair
	if product.seller_id != seller_id:
		raise ProductNotOwnerError("SKU does not belong to the authenticated seller")
	if product.status == ProductStatusEnum.HARD_BLOCKED:
		raise SkuForbiddenError("Cannot delete SKU of hard-blocked product")
	if sku.reserved_quantity > 0:
		raise SkuActiveReservesError("Cannot delete SKU with active reserves")

	emit_out_of_stock = (
		product.status == ProductStatusEnum.MODERATED and sku.active_quantity > 0
	)
	await sku_crud.delete_sku(db, sku)

	is_last_sku = await sku_crud.count_skus_by_product_id(db, product.id) == 0
	if is_last_sku and product.status == ProductStatusEnum.ON_MODERATION:
		product.status = ProductStatusEnum.CREATED
		db.add(product)
		await outbox_crud.enqueue_moderation_product_event(
			db,
			product_id=product.id,
			seller_id=product.seller_id,
			event="DELETED",
		)
	if emit_out_of_stock:
		await outbox_crud.enqueue_sku_out_of_stock_event(
			db, sku_id, product.id, sku.active_quantity
		)

	await db.commit()


async def get_skus_by_product_id(
	db: AsyncSession, product_id: UUID, seller_id: UUID
) -> list[SkuResponse]:
	product = await product_crud.get_product_by_id(db, product_id, seller_id)
	if not product:
		raise ProductNotFoundError(f"Product with id {product_id} not found")

	skus = await sku_crud.get_by_product_id(db, product_id)
	return [await build_sku_response(db, sku) for sku in skus]
