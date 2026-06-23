"""add product_events_processed table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"product_events_processed",
		sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("event_type", sa.String(length=32), nullable=False),
		sa.Column(
			"processed_at",
			sa.DateTime(),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.PrimaryKeyConstraint("idempotency_key"),
	)


def downgrade() -> None:
	op.drop_table("product_events_processed")
