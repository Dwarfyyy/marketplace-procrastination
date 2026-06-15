import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database.core import Base


class ModerationCardStatus(str, enum.Enum):
	PENDING = "PENDING"
	IN_REVIEW = "IN_REVIEW"
	MODERATED = "MODERATED"
	BLOCKED = "BLOCKED"
	HARD_BLOCKED = "HARD_BLOCKED"
	ARCHIVED = "ARCHIVED"


class ModerationCard(Base):
	"""A product's place in the moderation queue."""

	__tablename__ = "cards"
	__table_args__ = {"schema": "moderation"}

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
	seller_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
	status: Mapped[ModerationCardStatus] = mapped_column(
		Enum(ModerationCardStatus, name="moderationcardstatusenum"),
		default=ModerationCardStatus.PENDING,
		server_default=ModerationCardStatus.PENDING.value,
	)
	json_before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
	json_after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
	)
