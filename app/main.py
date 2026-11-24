import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.routes import (
    approvals_router,
    artifacts_router,
    assets_router,
    competitors_router,
    evaluation_router,
    fact_check_router,
    guidelines_router,
    health_router,
    llm_router,
    production_router,
    projects_router,
    research_router,
    scripts_router,
    storyboard_router,
    system_router,
    workflows_router,
)
from content_studio.config.settings import settings
from content_studio.database.session import engine
from content_studio.services import ResourceNotFoundError, WorkflowGateError
from content_studio.utils.logging import configure_structured_logging

logger = logging.getLogger("content_studio.api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    configure_structured_logging(settings.LOG_LEVEL)
    settings.ensure_directories()
    logger.info("Starting Santosh Analytics AI Content Studio API")
    yield
    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Santosh Analytics AI Content Studio",
        version="1.0.0",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "HTTP request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @application.exception_handler(ResourceNotFoundError)
    async def not_found_handler(_request: Request, exc: ResourceNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @application.exception_handler(WorkflowGateError)
    async def gate_error_handler(_request: Request, exc: WorkflowGateError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled server error on %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error. Check structured application logs."},
        )

    application.include_router(health_router)
    application.include_router(system_router)
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
    application.include_router(assets_router)
    application.include_router(production_router)
    application.include_router(evaluation_router)
    application.include_router(workflows_router)
    return application


app = create_app()
