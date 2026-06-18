from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from crud import images as images_crud
from crud import product as product_crud
from crud import sku as sku_crud
from database.models.catalog.base import Product, ProductStatusEnum
from exceptions.product import (
	ProductAlreadyDeletedError,
	ProductForbiddenError,
	ProductNotFoundError,
	ProductNotOwnerError,
)
from schemas.product import (
	BlockingReason,
	CharacteristicsResponse,
	FieldReport,
	ProductCreate,
	ProductDetailResponse,
	ProductImageResponse,
	ProductPaginatedResponse,
	ProductResponse,
	ProductSellerRead,
	ProductUpdate,
)
from services import category_service
from services.sku_service import build_sku_response


def _build_blocking_reason(product: Product) -> BlockingReason | None:
	if (
		product.status
		not in [ProductStatusEnum.BLOCKED, ProductStatusEnum.HARD_BLOCKED]
		or product.blocked_reason_id is None
	):
		return None
	return BlockingReason(
		id=product.blocked_reason_id,
		title=product.blocking_reason_title or "",
		comment=product.moderator_comment or "",
	)


def _build_field_reports(product: Product) -> list[FieldReport]:
	if product.status not in [
		ProductStatusEnum.BLOCKED,
		ProductStatusEnum.HARD_BLOCKED,
	]:
		return []
	raw = product.field_reports or []
	return [FieldReport.model_validate(item) for item in raw]


def build_product_response(product: Product) -> ProductResponse:
	return ProductResponse(
		id=product.id,
		seller_id=product.seller_id,
		category_id=product.category_id,
		title=product.title,
		slug=product.slug,
		description=product.description,
		status=product.status,
		deleted=product.deleted,
		blocking_reason_id=product.blocked_reason_id,
		moderator_comment=product.moderator_comment,
		images=[],
		characteristics=[],
		skus=[],
		created_at=product.created_at,
		updated_at=product.updated_at,
	)


async def build_product_detail_response(
	db: AsyncSession, product: Product
) -> ProductDetailResponse:
	images = await images_crud.get_product_images_by_id(product.id, db)
	characteristics = await product_crud.get_product_characteristics(db, product.id)
	skus = await sku_crud.get_by_product_id(db, product.id)
	sku_responses = [await build_sku_response(db, sku) for sku in skus]

	return ProductDetailResponse(
		id=product.id,
		seller_id=product.seller_id,
		category_id=product.category_id,
		title=product.title,
		slug=product.slug,
		description=product.description or "",
		status=product.status,
		deleted=product.deleted,
		images=[
			ProductImageResponse(id=img.id, url=img.url, ordering=img.ordering)
			for img in images
		],
		characteristics=[
			CharacteristicsResponse(id=c.id, name=c.name, value=c.value)
			for c in characteristics
		],
		skus=sku_responses,
		created_at=product.created_at,
		updated_at=product.updated_at,
		blocked=product.status
		in [ProductStatusEnum.BLOCKED, ProductStatusEnum.HARD_BLOCKED],
		blocking_reason=_build_blocking_reason(product),
		field_reports=_build_field_reports(product),
	)


async def _get_owned_product(
	db: AsyncSession, product_id: UUID, seller_id: UUID
) -> Product:
	product = await product_crud.get_product_by_id_only(db, product_id)
	if product is None:
		raise ProductNotFoundError()
	if product.seller_id != seller_id:
		raise ProductNotOwnerError()
	if product.status == ProductStatusEnum.HARD_BLOCKED:
		raise ProductForbiddenError("Can't edit hard-blocked product")
	return product


async def create_new_product(
	db: AsyncSession, product_in: ProductCreate, seller_id: UUID
) -> ProductResponse:
	await category_service.get_category_or_404(db, product_in.category_id)

	product = Product(
		seller_id=seller_id,
		category_id=product_in.category_id,
		title=product_in.title,
		slug=product_in.slug or f"product-{uuid4().hex}",
		description=product_in.description,
		status=ProductStatusEnum.CREATED,
		deleted=False,
		moderator_comment="",
	)

	product, images, characteristics = await product_crud.add_product(
		product,
		db,
		images=[image.model_dump() for image in product_in.images],
		characteristics=[
			characteristic.model_dump() for characteristic in product_in.characteristics
		],
	)
	response = build_product_response(product)
	response.images = [
		ProductImageResponse(id=image.id, url=image.url, ordering=image.ordering)
		for image in images
	]
	response.characteristics = [
		CharacteristicsResponse(
			id=characteristic.id,
			name=characteristic.name,
			value=characteristic.value,
		)
		for characteristic in characteristics
	]
	return response


async def get_product_for_seller(
	db: AsyncSession, product_id: UUID, seller_id: UUID
) -> ProductDetailResponse:
	product = await product_crud.get_product_by_id(db, product_id, seller_id)
	if not product:
		raise ProductNotFoundError("Product not found")
	return await build_product_detail_response(db, product)


async def get_all_seller_products(
	db: AsyncSession,
	seller_id: UUID,
	status: ProductStatusEnum | None = None,
	search: str | None = None,
	limit: int = 20,
	offset: int = 0,
	include_deleted: bool = True,
) -> ProductPaginatedResponse:
	rows, total_count = await product_crud.get_seller_products(
		db, seller_id, status, search, limit, offset, include_deleted
	)
	return ProductPaginatedResponse(
		items=[
			ProductSellerRead(
				id=product.id,
				seller_id=product.seller_id,
				title=product.title,
				slug=product.slug,
				description=product.description,
				status=product.status,
				category_id=product.category_id,
				deleted=product.deleted,
				skus_count=skus_count,
				total_active_quantity=total_active_quantity,
				created_at=product.created_at,
				updated_at=product.updated_at,
			)
			for product, skus_count, total_active_quantity in rows
		],
		total_count=total_count,
		limit=limit,
		offset=offset,
	)


async def update_existing_product(
	db: AsyncSession, product_id: UUID, seller_id: UUID, product_in: ProductUpdate
) -> ProductResponse:
	product = await _get_owned_product(db, product_id, seller_id)
	submit_for_remoderation = product.status in [
		ProductStatusEnum.BLOCKED,
		ProductStatusEnum.MODERATED,
	]

	update_data = product_in.model_dump(exclude_unset=True)
	if category_id := update_data.get("category_id"):
		await category_service.get_category_or_404(db, category_id)
	updated_product = await product_crud.update_product(
		db,
		product,
		update_data,
		should_remoderate=submit_for_remoderation,
	)
	return build_product_response(updated_product)


async def remove_product(
	db: AsyncSession, product_id: UUID, seller_id: UUID
) -> dict[str, str]:
	product = await product_crud.get_product_by_id_only(db, product_id, for_update=True)
	if product is None:
		raise ProductNotFoundError("Product not found")
	if product.seller_id != seller_id:
		raise ProductNotOwnerError(
			"Product does not belong to the authenticated seller"
		)
	if product.status == ProductStatusEnum.HARD_BLOCKED:
		raise ProductForbiddenError("Cannot delete hard-blocked product")
	if product.deleted:
		raise ProductAlreadyDeletedError("Product already deleted")

	skus = await sku_crud.get_by_product_id(db, product.id)
	await product_crud.soft_delete_product(db, product, [sku.id for sku in skus])

	return {"message": "Product deleted successfully"}
