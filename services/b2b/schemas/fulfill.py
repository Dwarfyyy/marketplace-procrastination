from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from schemas.inventory import InventoryItemRequest


class FulfillRequest(BaseModel):
	order_id: UUID
	items: list[InventoryItemRequest] = Field(..., min_length=1, max_length=100)


class FulfillResponse(BaseModel):
	order_id: UUID
	status: Literal["FULFILLED"]
	processed_at: datetime
