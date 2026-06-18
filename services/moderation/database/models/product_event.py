import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database.core import Base


class ProductEventProcessed(Base):
	"""Idempotency record for B2B product events (`POST /events/product`)."""

	__tablename__ = "product_events_processed"
	__table_args__ = {"schema": "moderation"}

	idempotency_key: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True
	)
	product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
	event_type: Mapped[str] = mapped_column(String(32), nullable=False)
	processed_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
