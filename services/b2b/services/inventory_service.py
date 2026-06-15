from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from crud import inventory as inventory_crud
from crud import outbox as outbox_crud
from exceptions.sku import (
	SkuIdempotencyConflictError,
	SkuInsufficientStockError,
	SkuNotFoundError,
)
from schemas.inventory import (
	InventoryOrderRequest,
	InventoryOrderResponse,
	InventoryItemRequest,
	ReserveRequest,
	ReserveResponse,
)


def _normalize_items(items: list[InventoryItemRequest]) -> list[dict]:
	quantities: dict[UUID, int] = {}
	for item in items:
		quantities[item.sku_id] = quantities.get(item.sku_id, 0) + item.quantity
	return [
		{"sku_id": str(sku_id), "quantity": quantities[sku_id]}
		for sku_id in sorted(quantities, key=str)
	]


def _operation_key(
	request: ReserveRequest | InventoryOrderRequest,
) -> UUID:
	if isinstance(request, ReserveRequest):
		return request.idempotency_key
	return request.order_id


def _operation_payload(
	request: ReserveRequest | InventoryOrderRequest,
	normalized_items: list[dict],
) -> dict:
	return {
		"order_id": str(request.order_id),
		"items": normalized_items,
	}


def _build_result(
	request: ReserveRequest | InventoryOrderRequest,
	operation: str,
) -> dict:
	now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
	if operation == "RESERVE":
		return {
			"order_id": str(request.order_id),
			"status": "RESERVED",
			"reserved_at": now,
		}
	return {
		"order_id": str(request.order_id),
		"status": "UNRESERVED",
		"processed_at": now,
	}


def _build_response(
	operation: str,
	result: dict,
) -> ReserveResponse | InventoryOrderResponse:
	if operation == "RESERVE":
		return ReserveResponse.model_validate(result)
	return InventoryOrderResponse.model_validate(result)


async def _apply_inventory_operation(
	db: AsyncSession,
	request: ReserveRequest | InventoryOrderRequest,
	operation: str,
) -> ReserveResponse | InventoryOrderResponse:
	normalized_items = _normalize_items(request.items)
	operation_key = _operation_key(request)
	operation_payload = _operation_payload(request, normalized_items)
	await inventory_crud.lock_idempotency_key(db, operation, operation_key)
	existing = await inventory_crud.get_operation(db, operation, operation_key)
	if existing is not None and existing.items != operation_payload:
		raise SkuIdempotencyConflictError(
			f"{'idempotency_key' if operation == 'RESERVE' else 'order_id'} "
			"was already used with a different payload"
		)
	if existing is not None and existing.result is not None:
		return _build_response(operation, existing.result)

	sku_ids = [UUID(item["sku_id"]) for item in normalized_items]
	skus = await inventory_crud.lock_skus(db, sku_ids)
	if len(skus) != len(sku_ids):
		found_ids = {sku.id for sku in skus}
		missing_id = next(sku_id for sku_id in sku_ids if sku_id not in found_ids)
		raise SkuNotFoundError(f"SKU with id {missing_id} not found")

	quantities = {
		UUID(item["sku_id"]): int(item["quantity"]) for item in normalized_items
	}
	for sku in skus:
		quantity = quantities[sku.id]
		available = (
			sku.active_quantity if operation == "RESERVE" else sku.reserved_quantity
		)
		if available < quantity:
			raise SkuInsufficientStockError(
				f"SKU with id {sku.id} has insufficient quantity"
			)

	for sku in skus:
		quantity = quantities[sku.id]
		if operation == "RESERVE":
			sku.active_quantity -= quantity
			sku.reserved_quantity += quantity
			if sku.active_quantity == 0:
				await outbox_crud.enqueue_sku_out_of_stock_event(
					db, sku.id, sku.product_id, sku.active_quantity
				)
		else:
			sku.active_quantity += quantity
			sku.reserved_quantity -= quantity
		db.add(sku)

	result = _build_result(request, operation)
	inventory_crud.add_operation(
		db,
		operation,
		operation_key,
		operation_payload,
		result,
	)
	await db.commit()
	return _build_response(operation, result)


async def reserve(db: AsyncSession, request: ReserveRequest) -> ReserveResponse:
	return await _apply_inventory_operation(db, request, "RESERVE")


async def unreserve(
	db: AsyncSession, request: InventoryOrderRequest
) -> InventoryOrderResponse:
	return await _apply_inventory_operation(db, request, "UNRESERVE")
