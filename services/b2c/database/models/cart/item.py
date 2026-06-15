import uuid
from datetime import datetime

from sqlalchemy import (
	String,
	Integer,
	DateTime,
	text,
	func,
	Index,
	CheckConstraint,
	ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.core import Base


class CartItem(Base):
	__tablename__ = "items"
	__table_args__ = (
		CheckConstraint(
			"user_id IS NOT NULL OR session_id IS NOT NULL", name="chk_cart_identity"
		),
		CheckConstraint("quantity > 0", name="chk_cart_quantity_positive"),
		Index("idx_cart_user", "user_id"),
		Index("idx_cart_session", "session_id"),
		Index(
			"uniq_cart_user_sku",
			"user_id",
			"sku_id",
			unique=True,
			postgresql_where=text("user_id IS NOT NULL"),
		),
		Index(
			"uniq_cart_session_sku",
			"session_id",
			"sku_id",
			unique=True,
			postgresql_where=text("session_id IS NOT NULL"),
		),
		{"schema": "cart"},
	)

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)

	user_id: Mapped[uuid.UUID | None] = mapped_column(
		UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE")
	)
	session_id: Mapped[str | None] = mapped_column(String(255))
	sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

	quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
	unit_price_at_add: Mapped[int | None] = mapped_column(Integer, nullable=True)
	unavailable_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
	)

	# Relationships
	user = relationship("User", back_populates="cart_items")
