import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
	BlockingReason,
	ModerationStatus,
	OutboxEvent,
	ProductModeration,
)
from schemas.products import DeclineRequest
from services.mutations import ensure_not_terminal, error


async def decline_product(
	db: AsyncSession,
	product_id: UUID,
	moderator_id: UUID,
	request: DeclineRequest,
) -> ModerationStatus:
	result = await db.execute(
		select(ProductModeration)
		.where(ProductModeration.product_id == product_id)
		.with_for_update()
	)
	card = result.scalar_one_or_none()
	if card is None:
		raise error(404, "NOT_FOUND", "Product not found in moderation queue")
	ensure_not_terminal(card)
	if card.status != ModerationStatus.IN_REVIEW:
		raise error(409, "CONFLICT", "Product is not in review status")
	if card.moderator_id != moderator_id:
		raise error(403, "FORBIDDEN", "This moderation card is not assigned to you")

	reason = await db.get(BlockingReason, request.blocking_reason_id)
	if reason is None:
		raise error(404, "NOT_FOUND", "Blocking reason not found")

	now = datetime.now(timezone.utc)
	idempotency_key = uuid.uuid4()
	card.status = (
		ModerationStatus.HARD_BLOCKED
		if reason.hard_block
		else ModerationStatus.BLOCKED
	)
	card.date_moderation = now
	card.blocking_reason_id = reason.id
	card.moderator_comment = request.moderator_comment
	card.field_reports = [
		report.model_dump(mode="json", exclude_none=True)
		for report in request.field_reports
	]
	db.add(
		OutboxEvent(
			idempotency_key=idempotency_key,
			event_type="BLOCKED",
			payload={
				"idempotency_key": str(idempotency_key),
				"product_id": str(product_id),
				"event_type": "BLOCKED",
				"hard_block": reason.hard_block,
				"blocking_reason_id": str(reason.id),
				"blocking_reason_title": reason.title,
				"moderator_comment": request.moderator_comment,
				"field_reports": card.field_reports,
				"occurred_at": now.isoformat().replace("+00:00", "Z"),
			},
		)
	)
	await db.commit()
	return card.status
