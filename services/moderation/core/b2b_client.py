import logging

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

MODERATION_EVENTS_PATH = "/api/v1/moderation/events"


async def send_moderation_event(payload: dict) -> bool:
	"""Best-effort delivery of a moderation decision to B2B.

	Returns True if B2B acknowledged the event (2xx), False otherwise. Failures
	are swallowed - the event stays PENDING in the outbox for retry by the
	outbox worker.
	"""
	url = f"{settings.B2B_BASE_URL}{MODERATION_EVENTS_PATH}"
	headers = {"X-Service-Key": settings.B2B_MODERATION_SERVICE_KEY}

	try:
		async with httpx.AsyncClient(timeout=5.0) as client:
			response = await client.post(url, json=payload, headers=headers)
		response.raise_for_status()
	except httpx.HTTPError:
		logger.exception("Failed to deliver moderation event to B2B")
		return False
	return True
