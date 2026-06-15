import os
import subprocess
from collections.abc import AsyncGenerator, AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
	AsyncEngine,
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from core import db as core_db


@pytest.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
	"""
	Init test database and run migrations.
	"""
	with PostgresContainer("postgres:15") as pg:
		sync_url = pg.get_connection_url()
		async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
		env = os.environ.copy()
		env["DATABASE_URL"] = async_url

		subprocess.run(
			["uv", "run", "alembic", "-c", "database/alembic.ini", "upgrade", "head"],
			check=True,
			env=env,
		)  # noqa: S607

		engine = create_async_engine(async_url, echo=False)
		try:
			yield engine
		finally:
			await engine.dispose()


@pytest.fixture()
def session_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
	"""
	Create session for test database.
	"""
	return async_sessionmaker(
		bind=test_engine, expire_on_commit=False, class_=AsyncSession
	)


@pytest.fixture()
async def db_session(
	session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
	"""
	Create session for test database and truncate tables.
	"""
	async with session_factory() as session:
		try:
			yield session
		finally:
			await session.execute(
				text(
					"TRUNCATE TABLE moderation.product_events_processed, "
					"moderation.outbox_events, moderation.cards CASCADE"
				)
			)
			await session.commit()


@pytest.fixture()
def app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
	"""
	Create FastAPI app with override get_db dependency.
	"""

	async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
		async with session_factory() as session:
			yield session

	from main import (
		app as fastapi_app,
		http_exception_handler,
		invalid_token_exception_handler,
		request_validation_exception_handler,
	)

	from fastapi import FastAPI, HTTPException
	from fastapi.exceptions import RequestValidationError
	from fastapi.middleware.cors import CORSMiddleware
	from api.cards import router as cards_router
	from api.events import router as events_router
	from core.config import settings as app_settings
	from exceptions.auth import InvalidTokenError
	from middlewares.service_key_verification import verify_service_key

	app_settings.B2B_SERVICE_KEY = "test-b2b-service-key"
	app_settings.SECRET_KEY = "test-secret-key"
	app_settings.ALGORITHM = "HS256"
	app_settings.B2B_MODERATION_SERVICE_KEY = "test-moderation-service-key"

	test_app = FastAPI(debug=False)
	test_app.add_exception_handler(HTTPException, http_exception_handler)
	test_app.add_exception_handler(
		RequestValidationError, request_validation_exception_handler
	)
	test_app.add_exception_handler(InvalidTokenError, invalid_token_exception_handler)
	test_app.middleware("http")(verify_service_key)
	test_app.add_middleware(
		CORSMiddleware,
		allow_origins=["http://localhost:5173", "http://localhost:3000"],
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"],
	)
	test_app.include_router(events_router, prefix="/api/v1")
	test_app.include_router(cards_router, prefix="/api/v1")
	test_app.dependency_overrides[core_db.get_db] = override_get_db
	fastapi_app.dependency_overrides[core_db.get_db] = override_get_db

	return test_app


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
	"""
	Create client for test database.
	"""
	async with AsyncClient(
		transport=ASGITransport(app=app), base_url="http://test"
	) as client:
		yield client
