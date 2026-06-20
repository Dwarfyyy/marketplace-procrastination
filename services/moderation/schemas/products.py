from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ApproveRequest(BaseModel):
	comment: str | None = Field(default=None, max_length=1000)


class FieldReport(BaseModel):
	field_path: str = Field(min_length=1, max_length=255)
	message: str = Field(min_length=1, max_length=1000)


class DeclineRequest(BaseModel):
	blocking_reason_ids: list[UUID] = Field(min_length=1)
	comment: str | None = Field(default=None, max_length=1000)
	field_reports: list[FieldReport] = Field(default_factory=list)


TicketStatus = Literal["PENDING", "IN_REVIEW", "APPROVED", "BLOCKED", "HARD_BLOCKED"]


class TicketResponse(BaseModel):
	id: UUID
	product_id: UUID
	seller_id: UUID
	kind: Literal["PRODUCT"] = "PRODUCT"
	status: TicketStatus
	queue_priority: int
	created_at: datetime
