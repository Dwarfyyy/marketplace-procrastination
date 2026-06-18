from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from exceptions.sku import (
	SkuIdempotencyConflictError,
	SkuInsufficientStockError,
	SkuNotFoundError,
)
from schemas.fulfill import FulfillRequest, FulfillResponse
from services import fulfill_service

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.post("/fulfill", response_model=FulfillResponse)
async def fulfill(
	request: FulfillRequest,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> FulfillResponse:
	try:
		return await fulfill_service.fulfill(db, request)
	except SkuNotFoundError as exc:
		await db.rollback()
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail={"code": "NOT_FOUND", "message": str(exc)},
		) from exc
	except (SkuInsufficientStockError, SkuIdempotencyConflictError) as exc:
		await db.rollback()
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail={"code": "INVENTORY_CONFLICT", "message": str(exc)},
		) from exc
