import uuid

from fastapi import Request

from core.security import decode_access_token
from exceptions.auth import InvalidTokenError


async def get_current_moderator_id(request: Request) -> uuid.UUID:
	authorization = request.headers.get("Authorization", "")
	if not authorization.startswith("Bearer "):
		raise InvalidTokenError("Missing bearer token")

	try:
		payload = decode_access_token(authorization)
	except ValueError as exc:
		raise InvalidTokenError(str(exc)) from exc

	user_id = payload.get("user_id")
	if not user_id:
		raise InvalidTokenError("Token is missing user_id claim")

	try:
		return uuid.UUID(str(user_id))
	except ValueError as exc:
		raise InvalidTokenError("Token user_id is not a valid UUID") from exc
