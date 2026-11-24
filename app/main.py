from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health_router, projects_router
from content_studio.config.settings import settings
from content_studio.database.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    settings.ensure_directories()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Santosh Analytics AI Content Studio",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(projects_router)
    return application


app = create_app()
