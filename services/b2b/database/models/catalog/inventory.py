import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, text, func, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.schema import CheckConstraint

from database.core import Base


class InvoiceStatusEnum(str, enum.Enum):
	CREATED = "CREATED"
	PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
	ACCEPTED = "ACCEPTED"
	CANCELLED = "CANCELLED"


class Invoice(Base):
	__tablename__ = "invoices"
	__table_args__ = {"schema": "catalog"}

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	seller_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
	status: Mapped[InvoiceStatusEnum] = mapped_column(
		default=InvoiceStatusEnum.CREATED, server_default="CREATED"
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
	)
	accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	items: Mapped[list["InvoiceItem"]] = relationship(
		"InvoiceItem", back_populates="invoice", cascade="all, delete-orphan"
	)


class InvoiceItem(Base):
	__tablename__ = "invoice_items"
	__table_args__ = (
		CheckConstraint("quantity > 0", name="chk_invoice_quantity_positive"),
		{"schema": "catalog"},
	)

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	invoice_id: Mapped[uuid.UUID] = mapped_column(
		ForeignKey("catalog.invoices.id", ondelete="CASCADE")
	)
	sku_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog.skus.id"))
	quantity: Mapped[int] = mapped_column(Integer)
	accepted_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

	invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="items")
