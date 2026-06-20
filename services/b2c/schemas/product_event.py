import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

EventType = Literal[
	"PRODUCT_BLOCKED",
	"PRODUCT_HARD_BLOCKED",
	"PRODUCT_DELETED",
	"SKU_OUT_OF_STOCK",
	"SKU_BACK_IN_STOCK",
	"PRICE_CHANGED",
]

# SKU-level events reference a concrete SKU; product-level events
# (PRODUCT_BLOCKED/PRODUCT_HARD_BLOCKED/PRODUCT_DELETED) carry only product_id
# per spec (EventProductRef) and resolve affected SKUs from the catalog.
SKU_LEVEL_EVENTS = frozenset(
	{"SKU_OUT_OF_STOCK", "SKU_BACK_IN_STOCK", "PRICE_CHANGED"}
)


class ProductEventPayload(BaseModel):
	product_id: uuid.UUID
	sku_ids: list[uuid.UUID] = Field(default_factory=list)
	sku_id: uuid.UUID | None = None
	hard_block: bool = False


class ProductEventRequest(BaseModel):
	event_type: EventType
	idempotency_key: uuid.UUID
	occurred_at: datetime
	payload: ProductEventPayload

	@model_validator(mode="after")
	def validate_sku_reference(self) -> "ProductEventRequest":
		# Product-level events carry only product_id; SKU-level events must
		# point at a concrete SKU (sku_id or sku_ids).
		if self.event_type in SKU_LEVEL_EVENTS:
			if not self.payload.sku_ids and self.payload.sku_id is None:
				raise ValueError("SKU-level event requires sku_id or sku_ids")
		return self

	@property
	def sku_ids(self) -> list[uuid.UUID]:
		if self.payload.sku_ids:
			return self.payload.sku_ids
		return [self.payload.sku_id] if self.payload.sku_id else []


class ProductEventResponse(BaseModel):
	idempotency_key: uuid.UUID
	processed: bool
	updated_count: int = 0
