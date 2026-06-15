import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_moderator_id
from core.db import get_db
from exceptions.card import (
	CardMissingSkuError,
	CardNotAssignedToModeratorError,
	CardNotFoundError,
	CardNotInReviewError,
)
from schemas.card import ApproveCardResponse
from services import card_service

router = APIRouter(prefix="/cards", tags=["Cards"])


@router.post("/{card_id}/approve", response_model=ApproveCardResponse)
async def approve_card(
	card_id: uuid.UUID,
	db: Annotated[AsyncSession, Depends(get_db)],
	moderator_id: Annotated[uuid.UUID, Depends(get_current_moderator_id)],
) -> ApproveCardResponse:
	try:
		return await card_service.approve_card(db, card_id, moderator_id)
	except CardNotFoundError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail={"code": "NOT_FOUND", "message": str(exc)},
		) from exc
	except CardNotAssignedToModeratorError as exc:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail={"code": "FORBIDDEN", "message": str(exc)},
		) from exc
	except CardNotInReviewError as exc:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail={"code": "CONFLICT", "message": str(exc)},
		) from exc
	except CardMissingSkuError as exc:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail={"code": "CONFLICT", "message": str(exc)},
		) from exc
