from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import crud.card as card_crud
import crud.product_event as product_event_crud
from database.models.card import ModerationCard, ModerationCardStatus
from schemas.product_event import ProductEventRequest, ProductEventResponse

# Statuses from which an edit returns the card to the moderation queue.
_REVIEWED_STATUSES = {ModerationCardStatus.MODERATED, ModerationCardStatus.BLOCKED}


def _apply_created(
	db: AsyncSession, request: ProductEventRequest, card: ModerationCard | None
) -> ModerationCard:
	if card is None:
		return card_crud.create_card(
			db,
			product_id=request.payload.product_id,
			seller_id=request.payload.seller_id,
			status=ModerationCardStatus.PENDING,
			json_after=request.payload.json_after,
		)
	# Retried CREATED for a card that already exists: refresh the snapshot
	# without disturbing the current moderation status.
	card.json_after = request.payload.json_after
	return card


def _apply_edited(
	db: AsyncSession, request: ProductEventRequest, card: ModerationCard | None
) -> ModerationCard:
	if card is None:
		return card_crud.create_card(
			db,
			product_id=request.payload.product_id,
			seller_id=request.payload.seller_id,
			status=ModerationCardStatus.PENDING,
			json_after=request.payload.json_after,
		)

	if card.status == ModerationCardStatus.HARD_BLOCKED:
		# Hard-blocked listings reject seller edits; the event is acknowledged
		# but does not change the card.
		return card

	if (
		card.status in _REVIEWED_STATUSES
		or card.status == ModerationCardStatus.ARCHIVED
	):
		card.json_before = card.json_after
		card.json_after = request.payload.json_after
		card.status = ModerationCardStatus.PENDING
		return card

	# PENDING / IN_REVIEW: update the fields under review in place.
	card.json_after = request.payload.json_after
	return card


def _apply_deleted(
	db: AsyncSession, request: ProductEventRequest, card: ModerationCard | None
) -> ModerationCard:
	if card is None:
		return card_crud.create_card(
			db,
			product_id=request.payload.product_id,
			seller_id=request.payload.seller_id,
			status=ModerationCardStatus.ARCHIVED,
			json_after=request.payload.json_after or None,
		)

	card.status = ModerationCardStatus.ARCHIVED
	return card


_HANDLERS = {
	"PRODUCT_CREATED": _apply_created,
	"PRODUCT_EDITED": _apply_edited,
	"PRODUCT_DELETED": _apply_deleted,
}


async def apply_product_event(
	db: AsyncSession, request: ProductEventRequest
) -> ProductEventResponse:
	await product_event_crud.lock_idempotency_key(db, request.idempotency_key)

	existing = await product_event_crud.get_processed_event(db, request.idempotency_key)
	if existing is not None:
		raise HTTPException(
			status_code=409,
			detail={
				"code": "DUPLICATE_EVENT",
				"message": "Event with this idempotency_key has already been processed",
			},
		)

	card = await card_crud.lock_card_by_product(db, request.payload.product_id)
	card = _HANDLERS[request.event_type](db, request, card)

	product_event_crud.add_processed_event(
		db, request.idempotency_key, request.payload.product_id, request.event_type
	)
	await db.commit()
	await db.refresh(card)
	return ProductEventResponse(
		idempotency_key=request.idempotency_key,
		processed=True,
		card_id=card.id,
		status=card.status,
	)
