"""init_moderation

Revision ID: 3f1a0c9d6b2e
Revises:
Create Date: 2026-06-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3f1a0c9d6b2e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	"""Upgrade schema."""
	op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS moderation"))
	op.execute(
		sa.text(
			"CREATE TYPE moderationcardstatusenum AS ENUM "
			"('PENDING', 'IN_REVIEW', 'MODERATED', 'BLOCKED', 'HARD_BLOCKED', 'ARCHIVED')"
		)
	)
	op.create_table(
		"cards",
		sa.Column(
			"id",
			postgresql.UUID(as_uuid=True),
			server_default=sa.text("gen_random_uuid()"),
			nullable=False,
		),
		sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column(
			"status",
			postgresql.ENUM(
				"PENDING",
				"IN_REVIEW",
				"MODERATED",
				"BLOCKED",
				"HARD_BLOCKED",
				"ARCHIVED",
				name="moderationcardstatusenum",
				create_type=False,
			),
			server_default="PENDING",
			nullable=False,
		),
		sa.Column("json_before", postgresql.JSONB(), nullable=True),
		sa.Column("json_after", postgresql.JSONB(), nullable=True),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.Column(
			"updated_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint("product_id"),
		schema="moderation",
	)
	op.create_table(
		"product_events_processed",
		sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("event_type", sa.String(length=32), nullable=False),
		sa.Column(
			"processed_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.PrimaryKeyConstraint("idempotency_key"),
		schema="moderation",
	)


def downgrade() -> None:
	"""Downgrade schema."""
	op.drop_table("product_events_processed", schema="moderation")
	op.drop_table("cards", schema="moderation")
	op.execute(sa.text("DROP TYPE moderationcardstatusenum"))
	op.execute(sa.text("DROP SCHEMA IF EXISTS moderation"))
