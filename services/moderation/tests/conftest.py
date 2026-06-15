from collections.abc import AsyncGenerator, AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
	AsyncEngine,
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)

from core import db as core_db
from database.models import Base
from main import app as moderation_app


@pytest.fixture()
async def engine() -> AsyncIterator[AsyncEngine]:
	engine = create_async_engine("sqlite+aiosqlite:///:memory:")
	async with engine.begin() as connection:
		await connection.run_sync(Base.metadata.create_all)
	try:
		yield engine
	finally:
		await engine.dispose()


@pytest.fixture()
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
	return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture()
async def db(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
	async with session_factory() as session:
		yield session


@pytest.fixture()
def app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
	async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
		async with session_factory() as session:
			yield session

	moderation_app.dependency_overrides[core_db.get_db] = override_get_db
	return moderation_app


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
	async with AsyncClient(
		transport=ASGITransport(app=app), base_url="http://test"
	) as client:
		yield client
