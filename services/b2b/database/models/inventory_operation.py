import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database.core import Base


class InventoryOperation(Base):
	__tablename__ = "inventory_operations"
	__table_args__ = (
		UniqueConstraint(
			"operation",
			"idempotency_key",
			name="uq_inventory_operation_idempotency",
		),
		{"schema": "catalog"},
	)

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	operation: Mapped[str] = mapped_column(String(32))
	idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
	items: Mapped[dict] = mapped_column(JSONB)
	result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
