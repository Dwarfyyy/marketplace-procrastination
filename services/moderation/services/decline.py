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


def _event_field_reports(request: DeclineRequest) -> list[dict[str, str]]:
	return [
		{
			"field_name": report.field_path,
			"comment": report.message,
		}
		for report in request.field_reports
	]


async def decline_product(
	db: AsyncSession,
	ticket_id: UUID,
	moderator_id: UUID,
	request: DeclineRequest,
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

	reasons: list[BlockingReason] = []
	for reason_id in request.blocking_reason_ids:
		reason = await db.get(BlockingReason, reason_id)
		if reason is None:
			raise error(404, "NOT_FOUND", "Blocking reason not found")
		reasons.append(reason)
	primary_reason = next((reason for reason in reasons if reason.hard_block), reasons[0])

	now = datetime.now(timezone.utc)
	idempotency_key = uuid.uuid4()
	card.status = (
		ModerationStatus.HARD_BLOCKED
		if primary_reason.hard_block
		else ModerationStatus.BLOCKED
	)
	card.date_moderation = now
	card.blocking_reason_id = primary_reason.id
	card.moderator_comment = request.comment
	card.field_reports = [
		report.model_dump(mode="json", exclude_none=True)
		for report in request.field_reports
	]
	event_field_reports = _event_field_reports(request)
	db.add(
		OutboxEvent(
			idempotency_key=idempotency_key,
			event_type="BLOCKED",
			payload={
				"idempotency_key": str(idempotency_key),
				"product_id": str(card.product_id),
				"event_type": "BLOCKED",
				"hard_block": primary_reason.hard_block,
				"blocking_reason_id": str(primary_reason.id),
				"blocking_reason_title": primary_reason.title,
				"moderator_comment": request.comment,
				"field_reports": event_field_reports,
				"occurred_at": now.isoformat().replace("+00:00", "Z"),
			},
		)
	)
	await db.commit()
	return card
