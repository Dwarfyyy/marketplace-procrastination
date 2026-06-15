import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ModerationStatus, OutboxEvent, ProductModeration


def _error(status_code: int, code: str, message: str) -> HTTPException:
	return HTTPException(
		status_code=status_code,
		detail={"code": code, "message": message},
	)


def _has_skus(card: ProductModeration) -> bool:
	skus = card.json_after.get("skus", [])
	return isinstance(skus, list) and len(skus) > 0


async def approve_product(
	db: AsyncSession,
	product_id: UUID,
	moderator_id: UUID,
	moderator_comment: str | None,
) -> None:
	result = await db.execute(
		select(ProductModeration)
		.where(ProductModeration.product_id == product_id)
		.with_for_update()
	)
	card = result.scalar_one_or_none()
	if card is None:
		raise _error(404, "NOT_FOUND", "Product not found in moderation queue")
	if card.status == ModerationStatus.HARD_BLOCKED:
		raise _error(409, "CONFLICT", "Product is permanently blocked")
	if card.status != ModerationStatus.IN_REVIEW:
		raise _error(409, "CONFLICT", "Product is not in review status")
	if card.moderator_id != moderator_id:
		raise _error(403, "FORBIDDEN", "This moderation card is not assigned to you")
	if not _has_skus(card):
		raise _error(409, "CONFLICT", "Product has no SKUs, cannot approve")

	now = datetime.now(timezone.utc)
	idempotency_key = uuid.uuid4()
	card.status = ModerationStatus.MODERATED
	card.date_moderation = now
	card.moderator_comment = moderator_comment
	card.blocking_reason_id = None
	card.field_reports = []
	db.add(
		OutboxEvent(
			idempotency_key=idempotency_key,
			event_type="MODERATED",
			payload={
				"idempotency_key": str(idempotency_key),
				"product_id": str(product_id),
				"event_type": "MODERATED",
				"hard_block": False,
				"field_reports": [],
				"occurred_at": now.isoformat().replace("+00:00", "Z"),
			},
		)
	)
	await db.commit()
