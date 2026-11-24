from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from content_studio.config.settings import settings


class Base(DeclarativeBase):
    pass


def _configure_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def build_async_engine(
    database_url: str | None = None,
    *,
    echo: bool | None = None,
) -> AsyncEngine:
    url = database_url or settings.resolved_database_url
    sql_echo = (
        echo
        if echo is not None
        else (settings.APP_ENV == "development" and settings.LOG_LEVEL.upper() == "DEBUG")
    )
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    async_engine = create_async_engine(
        url,
        echo=sql_echo,
        connect_args=connect_args,
    )
    if url.startswith("sqlite"):
        event.listen(async_engine.sync_engine, "connect", _configure_sqlite_pragmas)
    return async_engine


def build_session_factory(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


engine = build_async_engine()
AsyncSessionLocal = build_session_factory(engine)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
