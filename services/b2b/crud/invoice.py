from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from uuid import UUID
from database.models.catalog.inventory import Invoice, InvoiceItem, InvoiceStatusEnum
from schemas.invoice import InvoiceCreate


async def create_invoice(
	db: AsyncSession, invoice_data: InvoiceCreate, seller_id: UUID
) -> Invoice:
	"""Creates an invoice and its items in one transaction."""
	db_invoice = Invoice(
		seller_id=seller_id,
		status=InvoiceStatusEnum.CREATED,
	)
	db.add(db_invoice)
	await db.flush()

	for item in invoice_data.items:
		db_item = InvoiceItem(
			invoice_id=db_invoice.id,
			sku_id=item.sku_id,
			quantity=item.quantity,
			accepted_quantity=None,
		)
		db.add(db_item)

	await db.commit()

	result = await db.execute(
		select(Invoice)
		.options(joinedload(Invoice.items))
		.filter(Invoice.id == db_invoice.id)
		.execution_options(populate_existing=True)
	)

	return result.unique().scalar_one()


async def get_invoice_by_id(db: AsyncSession, invoice_id: UUID) -> Invoice | None:
	"""Receives the invoice by ID along with its items."""
	result = await db.execute(
		select(Invoice)
		.options(joinedload(Invoice.items))
		.filter(Invoice.id == invoice_id)
	)

	return result.unique().scalar_one_or_none()


async def get_all_invoices(
	db: AsyncSession, skip: int = 0, limit: int = 100
) -> tuple[int, list[Invoice]]:
	"""Gets a list of all invoices with pagination."""
	total_result = await db.execute(select(func.count(Invoice.id)))
	total = total_result.scalar_one()

	result = await db.execute(
		select(Invoice).options(joinedload(Invoice.items)).offset(skip).limit(limit)
	)

	return total, result.unique().scalars().all()


async def update_invoice_status(
	db: AsyncSession, invoice_id: UUID, status: str
) -> Invoice | None:
	"""Updates the status of the invoice and sets the acceptance date."""
	result = await db.execute(select(Invoice).filter(Invoice.id == invoice_id))
	db_invoice = result.scalar_one_or_none()

	if db_invoice:
		db_invoice.status = status
		if status == "ACCEPTED":
			db_invoice.accepted_at = func.now()
		await db.commit()
		await db.refresh(db_invoice)
	return db_invoice


async def update_invoice_to_accepted(db: AsyncSession, invoice: Invoice) -> Invoice:
	for item in invoice.items:
		item.accepted_quantity = item.quantity
		db.add(item)
	invoice.status = InvoiceStatusEnum.ACCEPTED
	invoice.accepted_at = func.now()

	await db.commit()
	await db.refresh(invoice)
	return invoice


async def delete_invoice(db: AsyncSession, db_invoice: Invoice) -> None:
	await db.delete(db_invoice)
	await db.commit()
