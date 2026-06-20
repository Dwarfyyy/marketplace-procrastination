"""product_events

Revision ID: 1a2b3c4d5e6f
Revises: 6434e8a4b37e
Create Date: 2026-06-15 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "6434e8a4b37e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	"""Upgrade schema."""
	op.add_column(
		"items",
		sa.Column("unavailable_reason", sa.String(length=32), nullable=True),
		schema="cart",
	)
	op.create_table(
		"product_events_processed",
		sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("event_type", sa.String(length=32), nullable=False),
		sa.Column(
			"processed_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.PrimaryKeyConstraint("idempotency_key"),
		schema="cart",
	)


def downgrade() -> None:
	"""Downgrade schema."""
	op.drop_table("product_events_processed", schema="cart")
	op.drop_column("items", "unavailable_reason", schema="cart")
