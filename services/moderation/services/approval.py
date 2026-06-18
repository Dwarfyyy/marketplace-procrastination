import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ModerationStatus, OutboxEvent, ProductModeration
from services.mutations import ensure_not_terminal, error


def _has_skus(card: ProductModeration) -> bool:
	skus = card.json_after.get("skus", [])
	return isinstance(skus, list) and len(skus) > 0


async def approve_product(
	db: AsyncSession,
	ticket_id: UUID,
	moderator_id: UUID,
	comment: str | None,
) -> ProductModeration:
	result = await db.execute(
		select(ProductModeration)
		.where(ProductModeration.id == ticket_id)
		.with_for_update()
	)
	card = result.scalar_one_or_none()
	if card is None:
		raise error(404, "NOT_FOUND", "Ticket not found in moderation queue")
	ensure_not_terminal(card)
	if card.status != ModerationStatus.IN_REVIEW:
		raise error(409, "CONFLICT", "Product is not in review status")
	if card.moderator_id != moderator_id:
		raise error(403, "FORBIDDEN", "This moderation card is not assigned to you")
	if not _has_skus(card):
		raise error(409, "CONFLICT", "Product has no SKUs, cannot approve")

	now = datetime.now(timezone.utc)
	idempotency_key = uuid.uuid4()
	card.status = ModerationStatus.MODERATED
	card.date_moderation = now
	card.moderator_comment = comment
	card.blocking_reason_id = None
	card.field_reports = []
	db.add(
		OutboxEvent(
			idempotency_key=idempotency_key,
			event_type="MODERATED",
			payload={
				"idempotency_key": str(idempotency_key),
				"product_id": str(card.product_id),
				"event_type": "MODERATED",
				"hard_block": False,
				"field_reports": [],
				"occurred_at": now.isoformat().replace("+00:00", "Z"),
			},
		)
	)
	await db.commit()
	return card
