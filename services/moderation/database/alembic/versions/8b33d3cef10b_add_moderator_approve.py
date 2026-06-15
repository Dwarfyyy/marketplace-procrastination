"""add_moderator_approve

Revision ID: 8b33d3cef10b
Revises: 3f1a0c9d6b2e
Create Date: 2026-06-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8b33d3cef10b"
down_revision: Union[str, Sequence[str], None] = "3f1a0c9d6b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	"""Upgrade schema."""
	op.add_column(
		"cards",
		sa.Column("moderator_id", postgresql.UUID(as_uuid=True), nullable=True),
		schema="moderation",
	)

	op.execute(
		sa.text(
			"CREATE TYPE moderationoutboxeventstatusenum AS ENUM ('PENDING', 'SENT')"
		)
	)
	op.create_table(
		"outbox_events",
		sa.Column(
			"id",
			postgresql.UUID(as_uuid=True),
			server_default=sa.text("gen_random_uuid()"),
			nullable=False,
		),
		sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("event_type", sa.String(length=32), nullable=False),
		sa.Column("payload", postgresql.JSONB(), nullable=False),
		sa.Column(
			"status",
			postgresql.ENUM(
				"PENDING",
				"SENT",
				name="moderationoutboxeventstatusenum",
				create_type=False,
			),
			server_default="PENDING",
			nullable=False,
		),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint("idempotency_key"),
		schema="moderation",
	)


def downgrade() -> None:
	"""Downgrade schema."""
	op.drop_table("outbox_events", schema="moderation")
	op.execute(sa.text("DROP TYPE moderationoutboxeventstatusenum"))
	op.drop_column("cards", "moderator_id", schema="moderation")
