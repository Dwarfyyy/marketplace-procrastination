from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.events import router as events_router
from core.config import settings
from middlewares.service_key_verification import verify_service_key

app = FastAPI(
	title="NeoMarket Moderation API",
	description="Сервис модерации товаров: приём событий от B2B",
	version="1.0.0",
	debug=settings.DEBUG,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
	detail = exc.detail
	if isinstance(detail, dict) and "code" in detail and "message" in detail:
		return JSONResponse(
			status_code=exc.status_code,
			content={
				"code": detail["code"],
				"message": detail["message"],
				"details": detail.get("details", []),
			},
			headers=exc.headers,
		)
	return JSONResponse(
		status_code=exc.status_code,
		content={"detail": detail},
		headers=exc.headers,
	)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
	_request: Request, exc: RequestValidationError
) -> JSONResponse:
	return JSONResponse(
		status_code=422,
		content={
			"code": "VALIDATION_ERROR",
			"message": "Request validation failed",
			"details": exc.errors(),
		},
	)


app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:5173", "http://localhost:3000"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

app.middleware("http")(verify_service_key)

app.include_router(events_router, prefix="/api/v1")


@app.get("/")
def read_root() -> dict[str, str]:
	return {
		"service": "NeoMarket Moderation",
		"status": "online",
		"documentation": "/docs",
	}
