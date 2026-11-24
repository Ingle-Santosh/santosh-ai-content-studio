from app.api.routes.approvals import router as approvals_router
from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.competitors import router as competitors_router
from app.api.routes.fact_check import router as fact_check_router
from app.api.routes.guidelines import router as guidelines_router
from app.api.routes.health import router as health_router
from app.api.routes.llm import router as llm_router
from app.api.routes.projects import router as projects_router
from app.api.routes.research import router as research_router
from app.api.routes.scripts import router as scripts_router
from app.api.routes.storyboard import router as storyboard_router
from app.api.routes.workflows import router as workflows_router

__all__ = [
    "approvals_router",
    "artifacts_router",
    "competitors_router",
    "fact_check_router",
    "guidelines_router",
    "health_router",
    "llm_router",
    "projects_router",
    "research_router",
    "scripts_router",
    "storyboard_router",
    "workflows_router",
]
