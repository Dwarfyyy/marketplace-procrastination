from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ApproveRequest(BaseModel):
	moderator_comment: str | None = Field(default=None, max_length=1000)


class FieldReport(BaseModel):
	field_name: str = Field(min_length=1, max_length=255)
	sku_id: UUID | None = None
	comment: str = Field(min_length=1, max_length=1000)


class DeclineRequest(BaseModel):
	blocking_reason_id: UUID
	moderator_comment: str | None = Field(default=None, max_length=1000)
	field_reports: list[FieldReport] = Field(default_factory=list)


class ModerationDecisionResponse(BaseModel):
	product_id: UUID
	status: Literal["MODERATED", "BLOCKED", "HARD_BLOCKED"]
