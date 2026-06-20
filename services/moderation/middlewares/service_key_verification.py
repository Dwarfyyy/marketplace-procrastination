import secrets
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from core.config import settings

PRODUCT_EVENTS_PATH = "/api/v1/b2b/events"
SERVICE_PATHS = {PRODUCT_EVENTS_PATH}


def is_service_request(request: Request) -> bool:
	return request.url.path in SERVICE_PATHS


async def verify_service_key(request: Request, call_next: Callable) -> JSONResponse:
	if not is_service_request(request):
		return await call_next(request)

	service_key = request.headers.get("X-Service-Key")
	expected = settings.B2B_SERVICE_KEY
	if (
		not service_key
		or not expected
		or not secrets.compare_digest(service_key, expected)
	):
		return JSONResponse(
			status_code=401,
			content={
				"code": "UNAUTHORIZED",
				"message": "Invalid or missing service key",
			},
		)

	return await call_next(request)
