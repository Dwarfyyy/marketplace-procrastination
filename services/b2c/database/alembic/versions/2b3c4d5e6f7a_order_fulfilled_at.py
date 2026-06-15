"""order_fulfilled_at

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-06-15 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2b3c4d5e6f7a"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	"""Upgrade schema."""
	op.add_column(
		"orders",
		sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
		schema="orders",
	)


def downgrade() -> None:
	"""Downgrade schema."""
	op.drop_column("orders", "fulfilled_at", schema="orders")
