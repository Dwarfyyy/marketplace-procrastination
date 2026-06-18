from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from exceptions.sku import (
	SkuIdempotencyConflictError,
	SkuInsufficientStockError,
	SkuNotFoundError,
)
from schemas.inventory import (
	InventoryOrderRequest,
	InventoryOrderResponse,
	ReserveRequest,
	ReserveResponse,
)
from services import inventory_service

router = APIRouter(prefix="/inventory", tags=["Inventory"])


async def _execute(
	db: AsyncSession,
	request: ReserveRequest | InventoryOrderRequest,
	operation: str,
) -> ReserveResponse | InventoryOrderResponse:
	try:
		if operation == "RESERVE":
			return await inventory_service.reserve(db, request)
		return await inventory_service.unreserve(db, request)
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


@router.post("/reserve", response_model=ReserveResponse)
async def reserve(
	request: ReserveRequest,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> ReserveResponse:
	return await _execute(db, request, "RESERVE")


@router.post("/unreserve", response_model=InventoryOrderResponse)
async def unreserve(
	request: InventoryOrderRequest,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryOrderResponse:
	return await _execute(db, request, "UNRESERVE")
