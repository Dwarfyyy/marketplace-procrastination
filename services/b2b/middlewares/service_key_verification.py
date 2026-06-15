import secrets
from typing import Callable

from core.config import settings
from fastapi import Request
from fastapi.responses import JSONResponse

SERVICE_KEY_PATH_PREFIX = "/api/v1/public"
SERVICE_CATALOG_PATH = "/api/v1/products"
INVENTORY_SERVICE_PATHS = {
	"/api/v1/inventory/reserve",
	"/api/v1/inventory/unreserve",
	"/api/v1/inventory/fulfill",
}
MODERATION_SERVICE_PATH = "/api/v1/moderation/events"


def is_service_request(request: Request) -> bool:
	return (
		request.url.path.startswith(SERVICE_KEY_PATH_PREFIX)
		or (
			request.method == "GET"
			and request.url.path == SERVICE_CATALOG_PATH
			and not request.headers.get("Authorization", "").startswith("Bearer ")
		)
		or request.url.path in INVENTORY_SERVICE_PATHS
		or (request.url.path == MODERATION_SERVICE_PATH)
	)


def expected_service_key(request: Request) -> str:
	if request.url.path == MODERATION_SERVICE_PATH:
		return settings.MODERATION_SERVICE_KEY
	return settings.B2C_SERVICE_KEY


async def verify_service_key(request: Request, call_next: Callable) -> JSONResponse:
	if not is_service_request(request):
		return await call_next(request)

	service_key = request.headers.get("X-Service-Key")
	expected = expected_service_key(request)
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
