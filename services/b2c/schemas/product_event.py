import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ProductEventPayload(BaseModel):
	product_id: uuid.UUID
	sku_ids: list[uuid.UUID] = Field(default_factory=list)
	sku_id: uuid.UUID | None = None
	hard_block: bool = False


class ProductEventRequest(BaseModel):
	event_type: Literal["PRODUCT_BLOCKED", "PRODUCT_DELETED", "SKU_OUT_OF_STOCK"]
	idempotency_key: uuid.UUID
	occurred_at: datetime
	payload: ProductEventPayload

	@model_validator(mode="after")
	def validate_sku_ids(self) -> "ProductEventRequest":
		if not self.payload.sku_ids and self.payload.sku_id is None:
			raise ValueError("payload must contain sku_ids or sku_id")
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
