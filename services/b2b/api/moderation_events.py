from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from exceptions.product import ProductNotFoundError
from schemas.moderation_event import ModerationEventRequest
from services import moderation_event_service

router = APIRouter(prefix="/moderation", tags=["Moderation Events"])


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
async def receive_moderation_event(
	request: ModerationEventRequest,
	db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
	try:
		await moderation_event_service.apply_moderation_event(db, request)
		return Response(status_code=status.HTTP_204_NO_CONTENT)
	except ProductNotFoundError as exc:
		await db.rollback()
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail={"code": "NOT_FOUND", "message": str(exc)},
		) from exc
