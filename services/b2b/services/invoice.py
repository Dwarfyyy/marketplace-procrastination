from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from crud import invoice as invoice_crud
from crud import sku as sku_crud
from database.models.catalog.base import ProductStatusEnum
from database.models.catalog.inventory import Invoice, InvoiceStatusEnum
from schemas.invoice import InvoiceCreate
from exceptions.invoice import (
	EmptyInvoiceError,
	InvoiceNotFoundError,
	InvoiceSkuNotModeratedError,
	InvoiceSkuNotOwnerError,
	InvalidInvoiceStatusError,
)
from exceptions.sku import SkuNotFoundError


async def create_new_invoice(
	db: AsyncSession, invoice_data: InvoiceCreate, seller_id: UUID
) -> Invoice:
	if not invoice_data.items:
		raise EmptyInvoiceError("Invoice must contain at least one item")

	for item in invoice_data.items:
		pair = await sku_crud.get_sku_and_product(db, item.sku_id)
		if pair is None:
			raise SkuNotFoundError(f"SKU with id {item.sku_id} not found")
		_, product = pair
		if product.seller_id != seller_id:
			raise InvoiceSkuNotOwnerError(
				f"SKU with id {item.sku_id} belongs to another seller"
			)
		if product.status != ProductStatusEnum.MODERATED:
			raise InvoiceSkuNotModeratedError(
				f"SKU with id {item.sku_id} must belong to a moderated product"
			)

	return await invoice_crud.create_invoice(db, invoice_data, seller_id)


async def get_invoice(db: AsyncSession, invoice_id: UUID) -> Invoice:
	invoice = await invoice_crud.get_invoice_by_id(db, invoice_id)
	if not invoice:
		raise InvoiceNotFoundError()
	return invoice


async def accept_invoice(db: AsyncSession, invoice_id: UUID) -> Invoice:
	invoice = await invoice_crud.get_invoice_by_id(db, invoice_id)
	if not invoice:
		raise InvoiceNotFoundError(str(invoice_id))

	if invoice.status != InvoiceStatusEnum.CREATED:
		raise InvalidInvoiceStatusError(invoice.status, "accept")

	for item in invoice.items:
		sku = await sku_crud.get_sku_by_id(db, item.sku_id)
		if sku:
			sku.active_quantity += item.quantity

	return await invoice_crud.update_invoice_to_accepted(db, invoice)


async def get_all_invoices(
	db: AsyncSession, skip: int = 0, limit: int = 10
) -> list[Invoice]:
	return await invoice_crud.get_all_invoices(db, skip=skip, limit=limit)


async def delete_invoice(db: AsyncSession, invoice_id: UUID) -> None:
	invoice = await invoice_crud.get_invoice_by_id(db, invoice_id)
	if not invoice:
		raise InvoiceNotFoundError(str(invoice_id))

	if invoice.status != InvoiceStatusEnum.CREATED:
		raise InvalidInvoiceStatusError(invoice.status, "delete")

	await invoice_crud.delete_invoice(db, invoice)
