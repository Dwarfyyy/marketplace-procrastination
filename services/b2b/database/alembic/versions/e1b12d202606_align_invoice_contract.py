"""align invoice statuses and item response with the API contract

Revision ID: e1b12d202606
Revises: d0b10d202606
Create Date: 2026-06-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1b12d202606"
down_revision: Union[str, Sequence[str], None] = "d0b10d202606"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column(
		"invoice_items",
		sa.Column("accepted_quantity", sa.Integer(), nullable=True),
		schema="catalog",
	)
	op.execute(
		"ALTER TABLE catalog.invoices ALTER COLUMN status DROP DEFAULT"
	)
	op.execute(
		"ALTER TABLE catalog.invoices "
		"ALTER COLUMN status TYPE VARCHAR USING status::text"
	)
	op.execute(
		"UPDATE catalog.invoices SET status = CASE "
		"WHEN status IN ('DRAFT', 'PENDING') THEN 'CREATED' "
		"WHEN status = 'REJECTED' THEN 'CANCELLED' "
		"ELSE status END"
	)
	op.execute("DROP TYPE public.invoicestatusenum")
	op.execute(
		"CREATE TYPE public.invoicestatusenum AS ENUM "
		"('CREATED', 'PARTIALLY_ACCEPTED', 'ACCEPTED', 'CANCELLED')"
	)
	op.execute(
		"ALTER TABLE catalog.invoices ALTER COLUMN status "
		"TYPE public.invoicestatusenum "
		"USING status::public.invoicestatusenum"
	)
	op.execute(
		"ALTER TABLE catalog.invoices ALTER COLUMN status SET DEFAULT 'CREATED'"
	)


def downgrade() -> None:
	op.execute(
		"ALTER TABLE catalog.invoices ALTER COLUMN status DROP DEFAULT"
	)
	op.execute(
		"ALTER TABLE catalog.invoices "
		"ALTER COLUMN status TYPE VARCHAR USING status::text"
	)
	op.execute(
		"UPDATE catalog.invoices SET status = CASE "
		"WHEN status IN ('CREATED', 'PARTIALLY_ACCEPTED') THEN 'PENDING' "
		"WHEN status = 'CANCELLED' THEN 'REJECTED' "
		"ELSE status END"
	)
	op.execute("DROP TYPE public.invoicestatusenum")
	op.execute(
		"CREATE TYPE public.invoicestatusenum AS ENUM "
		"('DRAFT', 'PENDING', 'ACCEPTED', 'REJECTED')"
	)
	op.execute(
		"ALTER TABLE catalog.invoices ALTER COLUMN status "
		"TYPE public.invoicestatusenum "
		"USING status::public.invoicestatusenum"
	)
	op.execute(
		"ALTER TABLE catalog.invoices ALTER COLUMN status SET DEFAULT 'DRAFT'"
	)
	op.drop_column("invoice_items", "accepted_quantity", schema="catalog")
