from app.api.routes.approvals import router as approvals_router
from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.guidelines import router as guidelines_router
from app.api.routes.health import router as health_router
from app.api.routes.projects import router as projects_router

__all__ = [
    "approvals_router",
    "artifacts_router",
    "guidelines_router",
    "health_router",
    "projects_router",
]
