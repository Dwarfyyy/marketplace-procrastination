from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
DATABASE_VERBOSE = settings.DATABASE_VERBOSE


engine = create_async_engine(
	SQLALCHEMY_DATABASE_URL, echo=DATABASE_VERBOSE, future=True
)
SessionLocal = async_sessionmaker(
	bind=engine,
	class_=AsyncSession,
	expire_on_commit=False,
	autoflush=False,
	autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
	async with SessionLocal() as session:
		yield session
