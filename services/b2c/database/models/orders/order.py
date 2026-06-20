import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.core import Base


class OrderStatusEnum(str, enum.Enum):
	CREATED = "CREATED"
	PAID = "PAID"
	ASSEMBLING = "ASSEMBLING"
	DELIVERING = "DELIVERING"
	DELIVERED = "DELIVERED"
	CANCELLED = "CANCELLED"
	CANCEL_PENDING = "CANCEL_PENDING"


class Order(Base):
	__tablename__ = "orders"
	__table_args__ = {"schema": "orders"}

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	buyer_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE")
	)
	status: Mapped[OrderStatusEnum] = mapped_column(
		default=OrderStatusEnum.PAID, server_default="PAID"
	)
	number: Mapped[str | None] = mapped_column(String(50), unique=True)
	subtotal: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
	delivery_cost: Mapped[int] = mapped_column(
		BigInteger, default=0, server_default="0"
	)
	total: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
	address_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("personal.addresses.id")
	)
	payment_method_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("personal.payment_methods.id")
	)
	comment: Mapped[str | None] = mapped_column(Text)
	idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
	idempotency_request_hash: Mapped[str] = mapped_column(String(64))
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
	paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
	)
	items = relationship(
		"OrderItem", back_populates="order", cascade="all, delete-orphan"
	)
	address = relationship("Address")
	payment_method = relationship("PaymentMethod")
	status_history = relationship("OrderStatusHistory", cascade="all, delete-orphan")


class OrderStatusHistory(Base):
	__tablename__ = "order_status_history"
	__table_args__ = {"schema": "orders"}

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	order_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("orders.orders.id")
	)
	status: Mapped[OrderStatusEnum] = mapped_column(
		default=OrderStatusEnum.CREATED, server_default="CREATED"
	)
	changed_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
	reason: Mapped[str | None] = mapped_column(Text)
	order = relationship("Order", back_populates="status_history")
