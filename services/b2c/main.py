import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api import (
	product,
	breadcrumbs,
	cart,
	catalog,
	favorite,
	subscriptions,
	auth,
	orders,
)
from core.config import settings
from core.db import get_db
from services import category_service
from middlewares.token_verification import verify_token

# Configure logging
if settings.DEBUG:
	logging.basicConfig(
		level=logging.DEBUG,
		format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
	)
	logging.getLogger("uvicorn").setLevel(logging.DEBUG)
	logging.getLogger("uvicorn.access").setLevel(logging.DEBUG)
	logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa
	# Startup: warm up categories tree cache
	try:
		db_gen = get_db()
		db = await db_gen.__anext__()
		await category_service.get_categories_tree(db)
	except Exception:  # noqa
		pass

	yield

	# Shutdown: cleanup if needed


app = FastAPI(debug=settings.DEBUG, lifespan=lifespan)


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


# Configure CORS
app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Frontend URLs
	allow_credentials=True,
	allow_methods=["*"],  # Allow all methods (GET, POST, PUT, DELETE, OPTIONS, etc.)
	allow_headers=["*"],  # Allow all headers
)

app.middleware("http")(verify_token)

app.include_router(product.router)
app.include_router(breadcrumbs.router)
app.include_router(cart.router)
app.include_router(favorite.router)
app.include_router(catalog.router)
app.include_router(auth.router)
app.include_router(subscriptions.router)
app.include_router(orders.router)
