"""
Async SQLAlchemy engine and session factory.
Used for persisting conversation history, feedback, and audit logs.

The engine and sessionmaker are created lazily on first use. This keeps module
import cheap and side-effect free: importing ORM models (or running Alembic in
offline mode) does not require a live database driver or connection. The engine
is only built when a session is actually requested.
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=settings.debug,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, creating it on first call."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a DB session per request."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def __getattr__(name: str):
    """
    Backward-compatible lazy access to `engine` / `AsyncSessionLocal`.
    Prefer get_engine() / get_sessionmaker() in new code.
    """
    if name == "engine":
        return get_engine()
    if name == "AsyncSessionLocal":
        return get_sessionmaker()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
