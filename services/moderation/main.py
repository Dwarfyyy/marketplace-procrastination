import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.products import router as products_router
from core.config import settings
from core.db import engine
from database.models import Base
from services import outbox


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
	async with engine.begin() as connection:
		await connection.run_sync(Base.metadata.create_all)
	worker: asyncio.Task | None = None
	if settings.OUTBOX_WORKER_ENABLED:
		worker = asyncio.create_task(outbox.run_forever())
	yield
	if worker is not None:
		worker.cancel()
		try:
			await worker
		except asyncio.CancelledError:
			pass


app = FastAPI(title="NeoMarket Moderation API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
	detail = exc.detail
	if isinstance(detail, dict) and set(detail) >= {"code", "message"}:
		content = {"code": detail["code"], "message": detail["message"]}
	else:
		content = {"code": "HTTP_ERROR", "message": str(detail)}
	return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
	_request: Request, exc: RequestValidationError
) -> JSONResponse:
	fields = sorted({str(error["loc"][-1]) for error in exc.errors()})
	return JSONResponse(
		status_code=400,
		content={
			"code": "VALIDATION_ERROR",
			"message": f"Invalid request fields: {', '.join(fields)}",
		},
	)


app.include_router(products_router, prefix="/api/v1")


@app.get("/")
async def healthcheck() -> dict[str, str]:
	return {"service": "NeoMarket Moderation", "status": "online"}
