from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from schemas.product import FieldReport


class ModerationEventRequest(BaseModel):
	idempotency_key: UUID
	product_id: UUID
	event_type: Literal["MODERATED", "BLOCKED"]
	hard_block: bool = False
	blocking_reason_id: UUID | None = None
	blocking_reason_title: str | None = Field(default=None, max_length=255)
	moderator_comment: str | None = Field(default=None, max_length=1000)
	field_reports: list[FieldReport] = Field(default_factory=list)
	occurred_at: datetime

	@model_validator(mode="after")
	def validate_blocked_event(self) -> "ModerationEventRequest":
		if self.event_type == "BLOCKED" and self.blocking_reason_id is None:
			raise ValueError("blocking_reason_id is required for BLOCKED status")
		if self.event_type == "MODERATED" and self.hard_block:
			raise ValueError("hard_block is only allowed for BLOCKED status")
		return self
