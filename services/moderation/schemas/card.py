import uuid

from pydantic import BaseModel

from database.models.card import ModerationCardStatus


class ApproveCardResponse(BaseModel):
	card_id: uuid.UUID
	status: ModerationCardStatus
