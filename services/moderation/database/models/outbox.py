import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database.core import Base


class OutboxEventStatus(str, enum.Enum):
	PENDING = "PENDING"
	SENT = "SENT"


class OutboxEvent(Base):
	"""Outgoing events for B2B (`POST /api/v1/moderation/events`)."""

	__tablename__ = "outbox_events"
	__table_args__ = {"schema": "moderation"}

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
	event_type: Mapped[str] = mapped_column(String(32))
	payload: Mapped[dict] = mapped_column(JSONB)
	status: Mapped[OutboxEventStatus] = mapped_column(
		Enum(OutboxEventStatus, name="moderationoutboxeventstatusenum"),
		default=OutboxEventStatus.PENDING,
		server_default=OutboxEventStatus.PENDING.value,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
	sent_at: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True), nullable=True
	)
