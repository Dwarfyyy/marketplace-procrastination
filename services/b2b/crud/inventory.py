from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.catalog.variants import Sku
from database.models.inventory_operation import InventoryOperation


async def lock_idempotency_key(
	db: AsyncSession,
	operation: str,
	idempotency_key: UUID,
) -> None:
	operation_bit = 1 if operation == "RESERVE" else 2
	unsigned_key = (idempotency_key.int & ((1 << 63) - 1)) ^ operation_bit
	await db.execute(select(func.pg_advisory_xact_lock(unsigned_key)))


async def get_operation(
	db: AsyncSession,
	operation: str,
	idempotency_key: UUID,
) -> InventoryOperation | None:
	result = await db.execute(
		select(InventoryOperation).where(
			InventoryOperation.operation == operation,
			InventoryOperation.idempotency_key == idempotency_key,
		)
	)
	return result.scalar_one_or_none()


async def lock_skus(db: AsyncSession, sku_ids: list[UUID]) -> list[Sku]:
	result = await db.execute(
		select(Sku).where(Sku.id.in_(sku_ids)).order_by(Sku.id).with_for_update()
	)
	return list(result.scalars().all())


def add_operation(
	db: AsyncSession,
	operation: str,
	idempotency_key: UUID,
	items: dict,
	result: dict,
) -> InventoryOperation:
	db_operation = InventoryOperation(
		operation=operation,
		idempotency_key=idempotency_key,
		items=items,
		result=result,
	)
	db.add(db_operation)
	return db_operation
