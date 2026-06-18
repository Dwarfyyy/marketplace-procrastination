from fastapi import HTTPException

from database.models import ModerationStatus, ProductModeration


def error(status_code: int, code: str, message: str) -> HTTPException:
	return HTTPException(
		status_code=status_code,
		detail={"code": code, "message": message},
	)


def ensure_not_terminal(card: ProductModeration) -> None:
	if card.status == ModerationStatus.HARD_BLOCKED:
		raise error(403, "FORBIDDEN", "Hard-blocked product cannot be modified")
