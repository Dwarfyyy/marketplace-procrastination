from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InventoryItemRequest(BaseModel):
	sku_id: UUID
	quantity: int = Field(..., gt=0)


class ReserveRequest(BaseModel):
	idempotency_key: UUID
	order_id: UUID
	items: list[InventoryItemRequest] = Field(..., min_length=1, max_length=100)

	model_config = ConfigDict(extra="forbid")


class InventoryOrderRequest(BaseModel):
	order_id: UUID
	items: list[InventoryItemRequest] = Field(..., min_length=1, max_length=100)

	model_config = ConfigDict(extra="forbid")


class InventoryItemResponse(BaseModel):
	sku_id: UUID
	active_quantity: int
	reserved_quantity: int


class ReserveResponse(BaseModel):
	order_id: UUID
	status: Literal["RESERVED"]
	reserved_at: datetime


class InventoryOrderResponse(BaseModel):
	order_id: UUID
	status: Literal["UNRESERVED"]
	processed_at: datetime
