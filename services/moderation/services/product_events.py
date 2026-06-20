from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ModerationStatus, ProductModeration, TicketKind


def strip_private_fields(product_data: dict) -> dict:
	cleaned = {**product_data}
	cleaned["skus"] = [
		{
			key: value
			for key, value in sku.items()
			if key not in {"cost_price", "reserved_quantity"}
		}
		for sku in product_data.get("skus", [])
	]
	return cleaned


async def apply_product_event(db: AsyncSession, event: dict) -> None:
	event_type = event.get("event_type")
	payload = event.get("payload", {})
	product_id = UUID(payload["product_id"])

	result = await db.execute(
		select(ProductModeration)
		.where(ProductModeration.product_id == product_id)
		.with_for_update()
	)
	card = result.scalar_one_or_none()

	if event_type == "PRODUCT_DELETED":
		if card is not None:
			await db.delete(card)
			await db.commit()
		return

	if event_type not in {"PRODUCT_CREATED", "PRODUCT_EDITED"}:
		raise ValueError(f"Unsupported product event: {event_type}")

	json_after = strip_private_fields(payload["json_after"])
	seller_id = UUID(payload["seller_id"])
	if card is None:
		kind = TicketKind.CREATE if event_type == "PRODUCT_CREATED" else TicketKind.EDIT
		card = ProductModeration(
			product_id=product_id,
			seller_id=seller_id,
			kind=kind,
			status=ModerationStatus.PENDING,
			queue_priority=1,
			json_after=json_after,
		)
		db.add(card)
	else:
		if card.status == ModerationStatus.HARD_BLOCKED:
			return
		old_status = card.status
		card.json_before = card.json_after
		card.json_after = json_after
		card.kind = TicketKind.EDIT
		card.status = ModerationStatus.PENDING
		card.moderator_id = None
		card.queue_priority = 2 if old_status == ModerationStatus.BLOCKED else 3
	await db.commit()
