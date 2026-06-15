from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ApproveRequest(BaseModel):
	moderator_comment: str | None = Field(default=None, max_length=1000)


class ModerationDecisionResponse(BaseModel):
	product_id: UUID
	status: Literal["MODERATED"]
