import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.card import ModerationCard, ModerationCardStatus


async def lock_card_by_product(
	db: AsyncSession, product_id: uuid.UUID
) -> ModerationCard | None:
	result = await db.execute(
		select(ModerationCard)
		.where(ModerationCard.product_id == product_id)
		.with_for_update()
	)
	return result.scalar_one_or_none()


async def lock_card_by_id(db: AsyncSession, card_id: uuid.UUID) -> ModerationCard | None:
	result = await db.execute(
		select(ModerationCard).where(ModerationCard.id == card_id).with_for_update()
	)
	return result.scalar_one_or_none()


def create_card(
	db: AsyncSession,
	*,
	product_id: uuid.UUID,
	seller_id: uuid.UUID,
	status: ModerationCardStatus,
	json_after: dict | None,
	json_before: dict | None = None,
) -> ModerationCard:
	card = ModerationCard(
		product_id=product_id,
		seller_id=seller_id,
		status=status,
		json_before=json_before,
		json_after=json_after,
	)
	db.add(card)
	return card
