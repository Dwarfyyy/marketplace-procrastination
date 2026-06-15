from sqlalchemy.ext.asyncio import AsyncSession

from crud import moderation_event as moderation_event_crud
from crud import outbox as outbox_crud
from crud import sku as sku_crud
from database.models.catalog.base import Product, ProductStatusEnum
from exceptions.product import ProductNotFoundError
from schemas.moderation_event import ModerationEventRequest


def _clear_blocking_data(product: Product) -> None:
	product.blocked_reason_id = None
	product.blocking_reason_title = None
	product.moderator_comment = ""
	product.field_reports = []


def _apply_blocking_data(product: Product, request: ModerationEventRequest) -> None:
	product.blocked_reason_id = request.blocking_reason_id
	product.blocking_reason_title = request.blocking_reason_title
	product.moderator_comment = request.moderator_comment or ""
	product.field_reports = [
		report.model_dump(mode="json", exclude_none=True)
		for report in request.field_reports
	]
	product.status = (
		ProductStatusEnum.HARD_BLOCKED
		if request.hard_block
		else ProductStatusEnum.BLOCKED
	)


async def apply_moderation_event(
	db: AsyncSession, request: ModerationEventRequest
) -> None:
	await moderation_event_crud.lock_idempotency_key(db, request.idempotency_key)
	existing = await moderation_event_crud.get_processed_event(
		db, request.idempotency_key
	)
	if existing is not None:
		return

	product = await moderation_event_crud.lock_product(db, request.product_id)
	if product is None:
		raise ProductNotFoundError("Product not found")

	if request.event_type == "MODERATED":
		product.status = ProductStatusEnum.MODERATED
		_clear_blocking_data(product)
	else:
		_apply_blocking_data(product, request)
		skus = await sku_crud.get_by_product_id(db, product.id)
		await outbox_crud.enqueue_product_blocked_event(
			db,
			product_id=product.id,
			sku_ids=[sku.id for sku in skus],
			hard_block=request.hard_block,
			occurred_at=request.occurred_at,
		)

	db.add(product)
	moderation_event_crud.add_processed_event(
		db,
		request.idempotency_key,
		request.product_id,
		request.event_type,
	)
	await db.commit()
