from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import (
    approvals_router,
    artifacts_router,
    competitors_router,
    fact_check_router,
    guidelines_router,
    health_router,
    llm_router,
    projects_router,
    research_router,
    scripts_router,
    storyboard_router,
    workflows_router,
)
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
        version="0.2.0",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(projects_router)
    application.include_router(artifacts_router)
    application.include_router(guidelines_router)
    application.include_router(approvals_router)
    application.include_router(llm_router)
    application.include_router(research_router)
    application.include_router(fact_check_router)
    application.include_router(competitors_router)
    application.include_router(scripts_router)
    application.include_router(storyboard_router)
    application.include_router(workflows_router)
    return application


app = create_app()
