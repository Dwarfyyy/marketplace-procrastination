import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.models.card import ModerationCard, ModerationCardStatus


@pytest.fixture()
def seller_id() -> uuid.UUID:
	return uuid.uuid4()


@pytest.fixture()
def moderator_id() -> uuid.UUID:
	return uuid.uuid4()


def auth_headers(user_id: uuid.UUID) -> dict[str, str]:
	expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
	token = jwt.encode(
		{
			"user_id": str(user_id),
			"exp": int(expires_at.timestamp()),
			"iat": int(datetime.now(timezone.utc).timestamp()),
		},
		settings.SECRET_KEY,
		algorithm=settings.ALGORITHM,
	)
	return {"Authorization": f"Bearer {token}"}


async def make_card(
	db_session: AsyncSession,
	*,
	product_id: uuid.UUID,
	seller_id: uuid.UUID,
	status: ModerationCardStatus,
	moderator_id: uuid.UUID | None = None,
	json_before: dict | None = None,
	json_after: dict | None = None,
) -> ModerationCard:
	card = ModerationCard(
		product_id=product_id,
		seller_id=seller_id,
		moderator_id=moderator_id,
		status=status,
		json_before=json_before,
		json_after=json_after,
	)
	db_session.add(card)
	await db_session.commit()
	await db_session.refresh(card)
	return card
