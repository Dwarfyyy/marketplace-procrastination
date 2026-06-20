"""add ticket kind to product_moderation

Revision ID: a1b2c3d4e5f6
Revises: 3f1a0c9d6b2e
Create Date: 2026-06-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "3f1a0c9d6b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text("CREATE TYPE ticketkind AS ENUM ('CREATE', 'EDIT')")
    )
    op.add_column(
        "product_moderation",
        sa.Column(
            "kind",
            sa.Enum("CREATE", "EDIT", name="ticketkind"),
            nullable=False,
            server_default="CREATE",
        ),
    )


def downgrade() -> None:
    op.drop_column("product_moderation", "kind")
    op.execute(sa.text("DROP TYPE ticketkind"))
