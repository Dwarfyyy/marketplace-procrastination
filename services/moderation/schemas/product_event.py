import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

class ProductEventPayload(BaseModel):
	product_id: uuid.UUID
	seller_id: uuid.UUID
	json_before: dict[str, Any] | None = None
	json_after: dict[str, Any] = Field(default_factory=dict)


class ProductEventRequest(BaseModel):
	event_type: Literal["PRODUCT_CREATED", "PRODUCT_EDITED", "PRODUCT_DELETED"]
	idempotency_key: uuid.UUID
	occurred_at: datetime
	payload: ProductEventPayload


class ProductEventResponse(BaseModel):
	idempotency_key: uuid.UUID
	processed: bool
	card_id: uuid.UUID | None = None
	status: str | None = None
