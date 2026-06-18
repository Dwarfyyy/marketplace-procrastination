from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException


async def current_moderator_id(
	value: Annotated[str | None, Header(alias="X-Moderator-ID")] = None,
) -> UUID:
	if value is None:
		raise HTTPException(
			status_code=401,
			detail={
				"code": "UNAUTHORIZED",
				"message": "Missing X-Moderator-ID header",
			},
		)
	try:
		return UUID(value)
	except ValueError as exc:
		raise HTTPException(
			status_code=401,
			detail={"code": "UNAUTHORIZED", "message": "Invalid moderator ID"},
		) from exc
