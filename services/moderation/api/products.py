from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import current_moderator_id
from core.db import get_db
from schemas.products import ApproveRequest, DeclineRequest, ModerationDecisionResponse
from services.approval import approve_product
from services.decline import decline_product

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("/{product_id}/approve", response_model=ModerationDecisionResponse)
async def approve(
	product_id: UUID,
	request: ApproveRequest,
	moderator_id: Annotated[UUID, Depends(current_moderator_id)],
	db: Annotated[AsyncSession, Depends(get_db)],
) -> ModerationDecisionResponse:
	await approve_product(db, product_id, moderator_id, request.moderator_comment)
	return ModerationDecisionResponse(product_id=product_id, status="MODERATED")


@router.post("/{product_id}/decline", response_model=ModerationDecisionResponse)
async def decline(
	product_id: UUID,
	request: DeclineRequest,
	moderator_id: Annotated[UUID, Depends(current_moderator_id)],
	db: Annotated[AsyncSession, Depends(get_db)],
) -> ModerationDecisionResponse:
	status = await decline_product(db, product_id, moderator_id, request)
	return ModerationDecisionResponse(product_id=product_id, status=status.value)
