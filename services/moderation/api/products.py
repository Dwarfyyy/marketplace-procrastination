from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import current_moderator_id
from core.db import get_db
from database.models import ModerationStatus, ProductModeration
from schemas.products import ApproveRequest, DeclineRequest, TicketResponse, TicketStatus
from services.approval import approve_product
from services.decline import decline_product

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _ticket_status(status: ModerationStatus) -> TicketStatus:
	if status == ModerationStatus.MODERATED:
		return "APPROVED"
	return status.value


def _ticket_response(card: ProductModeration) -> TicketResponse:
	return TicketResponse(
		id=card.id,
		product_id=card.product_id,
		seller_id=card.seller_id,
		kind=card.kind.value,
		status=_ticket_status(card.status),
		queue_priority=card.queue_priority,
		created_at=card.date_created,
	)


@router.post("/{ticket_id}/approve")
async def approve(
	ticket_id: UUID,
	request: ApproveRequest,
	moderator_id: Annotated[UUID, Depends(current_moderator_id)],
	db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
	card = await approve_product(db, ticket_id, moderator_id, request.comment)
	return _ticket_response(card)


@router.post("/{ticket_id}/block")
async def decline(
	ticket_id: UUID,
	request: DeclineRequest,
	moderator_id: Annotated[UUID, Depends(current_moderator_id)],
	db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
	card = await decline_product(db, ticket_id, moderator_id, request)
	return _ticket_response(card)
