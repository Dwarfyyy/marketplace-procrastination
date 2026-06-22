import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ModerationStatus, ProductModeration

PRODUCT_EVENT_SERVICE_KEY_HEADERS = {"X-Service-Key": "test-b2b-service-key"}


@pytest.fixture()
def seller_id() -> uuid.UUID:
	return uuid.uuid4()


async def make_card(
	db_session: AsyncSession,
	*,
	product_id: uuid.UUID,
	seller_id: uuid.UUID,
	status: ModerationStatus,
	json_before: dict | None = None,
	json_after: dict | None = None,
) -> ProductModeration:
	card = ProductModeration(
		product_id=product_id,
		seller_id=seller_id,
		status=status,
		json_before=json_before,
		json_after=json_after,
	)
	db_session.add(card)
	await db_session.commit()
	await db_session.refresh(card)
	return card
