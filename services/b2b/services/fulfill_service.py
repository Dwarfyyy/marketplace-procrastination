from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from crud import fulfill as fulfill_crud
from database.models.catalog.variants import Sku
from exceptions.sku import (
	SkuIdempotencyConflictError,
	SkuInsufficientStockError,
	SkuNotFoundError,
)
from schemas.fulfill import FulfillRequest, FulfillResponse
from schemas.inventory import InventoryItemRequest


def _normalize_items(items: list[InventoryItemRequest]) -> list[dict]:
	quantities: dict[UUID, int] = {}
	for item in items:
		quantities[item.sku_id] = quantities.get(item.sku_id, 0) + item.quantity
	return [
		{"sku_id": str(sku_id), "quantity": quantities[sku_id]}
		for sku_id in sorted(quantities, key=str)
	]


def _snapshot_skus(skus: list[Sku]) -> list[dict]:
	return [
		{
			"sku_id": str(sku.id),
			"active_quantity": sku.active_quantity,
			"reserved_quantity": sku.reserved_quantity,
		}
		for sku in skus
	]


def _build_response(order_id: UUID, processed_at: datetime) -> FulfillResponse:
	return FulfillResponse(
		order_id=order_id,
		status="FULFILLED",
		processed_at=processed_at,
	)


async def fulfill(db: AsyncSession, request: FulfillRequest) -> FulfillResponse:
	normalized_items = _normalize_items(request.items)
	await fulfill_crud.lock_order_id(db, request.order_id)
	existing = await fulfill_crud.get_fulfilled_order(db, request.order_id)
	if existing is not None:
		if existing.items != normalized_items:
			raise SkuIdempotencyConflictError(
				"order_id was already fulfilled with a different payload"
			)
		return _build_response(request.order_id, existing.fulfilled_at)

	sku_ids = [UUID(item["sku_id"]) for item in normalized_items]
	skus = await fulfill_crud.lock_skus(db, sku_ids)
	if len(skus) != len(sku_ids):
		found_ids = {sku.id for sku in skus}
		missing_id = next(sku_id for sku_id in sku_ids if sku_id not in found_ids)
		raise SkuNotFoundError(f"SKU with id {missing_id} not found")

	quantities = {
		UUID(item["sku_id"]): int(item["quantity"]) for item in normalized_items
	}
	for sku in skus:
		if sku.reserved_quantity < quantities[sku.id]:
			raise SkuInsufficientStockError(
				f"SKU with id {sku.id} has insufficient reserved quantity"
			)

	for sku in skus:
		sku.reserved_quantity -= quantities[sku.id]
		db.add(sku)

	result = _snapshot_skus(skus)
	fulfilled_order = fulfill_crud.add_fulfilled_order(
		db,
		request.order_id,
		normalized_items,
		result,
	)
	await db.flush()
	await db.refresh(fulfilled_order, attribute_names=["fulfilled_at"])
	response = _build_response(request.order_id, fulfilled_order.fulfilled_at)
	await db.commit()
	return response
