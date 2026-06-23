import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Integer, String, Text, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
	pass


class ModerationStatus(str, enum.Enum):
	PENDING = "PENDING"
	IN_REVIEW = "IN_REVIEW"
	MODERATED = "MODERATED"
	BLOCKED = "BLOCKED"
	HARD_BLOCKED = "HARD_BLOCKED"


class TicketKind(str, enum.Enum):
	CREATE = "CREATE"
	EDIT = "EDIT"


class OutboxStatus(str, enum.Enum):
	PENDING = "PENDING"
	SENT = "SENT"


class ProductModeration(Base):
	__tablename__ = "product_moderation"

	id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
	product_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, index=True)
	seller_id: Mapped[uuid.UUID] = mapped_column(Uuid)
	kind: Mapped[TicketKind] = mapped_column(Enum(TicketKind), default=TicketKind.CREATE)
	status: Mapped[ModerationStatus] = mapped_column(
		Enum(ModerationStatus), default=ModerationStatus.PENDING
	)
	queue_priority: Mapped[int] = mapped_column(Integer, default=1)
	json_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
	json_after: Mapped[dict] = mapped_column(JSON)
	field_reports: Mapped[list] = mapped_column(JSON, default=list)
	blocking_reason_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
	moderator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
	moderator_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
	date_created: Mapped[datetime] = mapped_column(DateTime, default=func.now())
	date_updated: Mapped[datetime] = mapped_column(
		DateTime, default=func.now(), onupdate=func.now()
	)
	date_moderation: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BlockingReason(Base):
	__tablename__ = "product_blocking_reasons"

	id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
	title: Mapped[str] = mapped_column(String(255), unique=True)
	hard_block: Mapped[bool] = mapped_column(Boolean, default=False)


class OutboxEvent(Base):
	__tablename__ = "moderation_outbox_events"

	id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
	idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
	event_type: Mapped[str] = mapped_column(String(64))
	payload: Mapped[dict] = mapped_column(JSON)
	status: Mapped[OutboxStatus] = mapped_column(
		Enum(OutboxStatus), default=OutboxStatus.PENDING
	)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
	sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProductEventProcessed(Base):
	__tablename__ = "product_events_processed"

	idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
	product_id: Mapped[uuid.UUID] = mapped_column(Uuid)
	event_type: Mapped[str] = mapped_column(String(32))
	processed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
