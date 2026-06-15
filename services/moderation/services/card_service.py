import uuid

from sqlalchemy.ext.asyncio import AsyncSession

import crud.card as card_crud
import crud.outbox as outbox_crud
from core.b2b_client import send_moderation_event
from database.models.card import ModerationCardStatus
from exceptions.card import (
	CardMissingSkuError,
	CardNotAssignedToModeratorError,
	CardNotFoundError,
	CardNotInReviewError,
)
from schemas.card import ApproveCardResponse


async def approve_card(
	db: AsyncSession, card_id: uuid.UUID, moderator_id: uuid.UUID
) -> ApproveCardResponse:
	card = await card_crud.lock_card_by_id(db, card_id)
	if card is None:
		raise CardNotFoundError("Moderation card not found")

	if card.moderator_id != moderator_id:
		raise CardNotAssignedToModeratorError(
			"Card is assigned to a different moderator"
		)

	if card.status != ModerationCardStatus.IN_REVIEW:
		raise CardNotInReviewError("Card is not in IN_REVIEW status")

	skus = (card.json_after or {}).get("skus")
	if not skus:
		raise CardMissingSkuError("Product has no SKUs and cannot be approved")

	card.status = ModerationCardStatus.MODERATED
	outbox_event = outbox_crud.enqueue_moderated_event(db, card.product_id)

	await db.commit()
	await db.refresh(card)

	if await send_moderation_event(outbox_event.payload):
		await outbox_crud.mark_event_sent(db, outbox_event)

	return ApproveCardResponse(card_id=card.id, status=card.status)
