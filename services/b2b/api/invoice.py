import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from core.db import get_db
from database.models.catalog.inventory import Invoice
from schemas.invoice import InvoiceCreate, InvoiceResponse
from services import invoice as invoice_service
from exceptions.invoice import (
	InvoiceError,
	InvoiceNotFoundError,
	InvalidInvoiceStatusError,
	EmptyInvoiceError,
	InvoiceSkuNotModeratedError,
	InvoiceSkuNotOwnerError,
)
from exceptions.sku import SkuNotFoundError


router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice_endpoint(
	request: Request,
	invoice_data: InvoiceCreate,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> InvoiceResponse:
	seller_id = uuid.UUID(str(request.state.user_id))
	try:
		return await invoice_service.create_new_invoice(db, invoice_data, seller_id)
	except SkuNotFoundError as e:
		raise HTTPException(
			status_code=404,
			detail={"code": "NOT_FOUND", "message": str(e)},
		) from e
	except EmptyInvoiceError as e:
		raise HTTPException(
			status_code=400,
			detail={"code": "EMPTY_ITEMS", "message": str(e)},
		) from e
	except InvoiceSkuNotModeratedError as e:
		raise HTTPException(
			status_code=400,
			detail={"code": "SKU_NOT_MODERATED", "message": str(e)},
		) from e
	except InvoiceSkuNotOwnerError as e:
		raise HTTPException(
			status_code=403,
			detail={"code": "NOT_OWNER", "message": str(e)},
		) from e
	except InvoiceError as e:
		raise HTTPException(
			status_code=400,
			detail={"code": "INVALID_INVOICE", "message": str(e)},
		) from e


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice_endpoint(
	invoice_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> InvoiceResponse:
	try:
		return await invoice_service.get_invoice(db, invoice_id)
	except InvoiceNotFoundError as e:
		raise HTTPException(status_code=404, detail=str(e)) from e
	except InvalidInvoiceStatusError as e:
		raise HTTPException(status_code=400, detail=str(e)) from e
	except InvoiceError as e:
		raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{invoice_id}/accept", response_model=InvoiceResponse)
async def accept_invoice_endpoint(
	invoice_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> Invoice:
	try:
		return await invoice_service.accept_invoice(db, invoice_id)
	except InvoiceNotFoundError as e:
		raise HTTPException(status_code=404, detail=str(e)) from e
	except InvalidInvoiceStatusError as e:
		raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/")
async def get_all_invoices_endpoint(
	db: Annotated[AsyncSession, Depends(get_db)], skip: int = 0, limit: int = 10
) -> dict:
	total, invoices = await invoice_service.get_all_invoices(db, skip=skip, limit=limit)
	return {"total": total, "items": invoices, "skip": skip, "limit": limit}


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice_endpoint(
	invoice_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
	try:
		await invoice_service.delete_invoice(db, invoice_id)
	except InvoiceNotFoundError as e:
		raise HTTPException(status_code=404, detail=str(e)) from e
	except InvalidInvoiceStatusError as e:
		raise HTTPException(status_code=400, detail=str(e)) from e
	except InvoiceError as e:
		raise HTTPException(status_code=400, detail=str(e)) from e
	return None
