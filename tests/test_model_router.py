from pathlib import Path

import pytest
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings
from content_studio.database.repositories import ProjectRepository, UsageRepository
from content_studio.providers.llm import (
    BaseLLMProvider,
    BudgetExceededError,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMTransientError,
    LLMUsage,
    ModelRouter,
    ProviderHealth,
    StructuredOutputError,
    TaskType,
)


class _ScriptPlan(BaseModel):
    hook: str = Field(min_length=5)
    sections: list[str] = Field(min_length=2)


class _FakeProvider(BaseLLMProvider):
    def __init__(
        self,
        *,
        provider_name: str,
        is_cloud: bool,
        outcomes: list[LLMResponse | Exception],
    ) -> None:
        self.provider_name = provider_name
        self.is_cloud = is_cloud
        self._outcomes = list(outcomes)
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError(f"No more scripted outcomes for {self.provider_name}")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.provider_name,
            is_cloud=self.is_cloud,
            available=True,
            models=["fake-model"],
        )


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        APP_ENV="test",
        DATA_DIR=tmp_path / "data",
        LLM_RETRY_BASE_DELAY_SECONDS=0.0,
        **overrides,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_router_enforces_local_only_and_task_model_mapping(tmp_path: Path) -> None:
    cfg = _make_settings(
        tmp_path,
        LOCAL_ONLY=True,
        OLLAMA_DEFAULT_MODEL="qwen2.5-coder:14b",
        OLLAMA_WRITING_MODEL="llama3.1:8b",
        OLLAMA_FAST_MODEL="qwen2.5:3b",
    )
    local = _FakeProvider(
        provider_name="ollama",
        is_cloud=False,
        outcomes=[
            LLMResponse(provider="ollama", model="llama3.1:8b", content="Namaste devs!"),
            LLMResponse(provider="ollama", model="qwen2.5:3b", content="QA ok"),
        ],
    )
    cloud = _FakeProvider(provider_name="gemini", is_cloud=True, outcomes=[])
    router = ModelRouter(app_settings=cfg, local_provider=local, cloud_provider=cloud)

    # Even when prefer_cloud=True, LOCAL_ONLY forces Ollama with writing model
    resp1, route1 = await router.generate(
        task=TaskType.SCRIPTWRITING,
        messages=[LLMMessage(role="user", content="Write intro")],
        prefer_cloud=True,
    )
    assert resp1.provider == "ollama"
    assert route1.model == "llama3.1:8b"
    assert route1.fallback_reason == "local_only_mode"
    assert len(cloud.requests) == 0

    # QA task picks fast model
    _resp2, route2 = await router.generate(
        task=TaskType.QA_REVIEW,
        messages=[LLMMessage(role="user", content="Check")],
    )
    assert route2.model == "qwen2.5:3b"

    # Strict cloud raises BudgetExceededError in LOCAL_ONLY mode
    with pytest.raises(BudgetExceededError):
        await router.resolve_route(TaskType.FACT_CHECK, prefer_cloud=True, strict_cloud=True)


@pytest.mark.asyncio
async def test_router_cloud_budget_tracking_and_fallback(
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    cfg = _make_settings(
        tmp_path,
        LOCAL_ONLY=False,
        MAX_BUDGET_USD=1.0,
        GEMINI_DEFAULT_MODEL="gemini-2.5-flash",
    )
    project_repo = ProjectRepository(db_session)
    usage_repo = UsageRepository(db_session)
    project = await project_repo.create(
        title="Hybrid Routing",
        topic="Hybrid AI Models",
        config={"cloud_fallback_enabled": True},
        budget_usd=0.05,
    )

    cloud = _FakeProvider(
        provider_name="gemini",
        is_cloud=True,
        outcomes=[
            LLMResponse(
                provider="gemini",
                model="gemini-2.5-flash",
                content="Cloud synthesis",
                usage=LLMUsage(
                    prompt_tokens=1000,
                    completion_tokens=400,
                    estimated_cost_usd=0.06,
                    latency_ms=420,
                ),
            )
        ],
    )
    local = _FakeProvider(
        provider_name="ollama",
        is_cloud=False,
        outcomes=[
            LLMResponse(
                provider="ollama",
                model="qwen2.5-coder:14b",
                content="Local fallback response",
                usage=LLMUsage(prompt_tokens=200, completion_tokens=100, latency_ms=300),
            )
        ],
    )
    router = ModelRouter(
        app_settings=cfg,
        local_provider=local,
        cloud_provider=cloud,
        usage_repo=usage_repo,
        project_repo=project_repo,
    )

    # First call succeeds on cloud and updates project.spent_usd + llm_usage_logs
    resp1, route1 = await router.generate(
        task=TaskType.RESEARCH_SYNTHESIS,
        messages=[LLMMessage(role="user", content="Synthesize findings")],
        project_id=project.id,
        node_name="research_node",
    )
    assert resp1.provider == "gemini"
    assert route1.is_cloud is True

    refreshed = await project_repo.get_by_id(project.id)
    assert refreshed is not None
    assert refreshed.spent_usd == pytest.approx(0.06)

    # Second call sees spent_usd (0.06) >= project.budget_usd (0.05) -> falls back to local
    resp2, route2 = await router.generate(
        task=TaskType.RESEARCH_SYNTHESIS,
        messages=[LLMMessage(role="user", content="Second pass")],
        project_id=project.id,
        node_name="research_node",
    )
    assert resp2.provider == "ollama"
    assert route2.is_cloud is False
    assert route2.fallback_reason == "project_budget_exhausted"

    logs = await usage_repo.list_for_project(project.id)
    assert len(logs) == 2


@pytest.mark.asyncio
async def test_router_honors_per_project_provider_and_model_overrides(
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    cfg = _make_settings(
        tmp_path,
        LOCAL_ONLY=False,
        PREFER_CLOUD_DEFAULT=True,
        MAX_BUDGET_USD=5.0,
        OLLAMA_DEFAULT_MODEL="qwen2.5-coder:14b",
        GEMINI_DEFAULT_MODEL="gemini-2.5-flash",
    )
    project_repo = ProjectRepository(db_session)
    local = _FakeProvider(provider_name="ollama", is_cloud=False, outcomes=[])
    cloud = _FakeProvider(provider_name="gemini", is_cloud=True, outcomes=[])
    router = ModelRouter(
        app_settings=cfg,
        local_provider=local,
        cloud_provider=cloud,
        project_repo=project_repo,
    )

    local_proj = await project_repo.create(
        title="Fast Local Project",
        topic="SQLite Tuning",
        config={"llm_provider": "ollama", "llm_model": "qwen3.5:9b"},
        budget_usd=2.0,
    )
    route_local = await router.resolve_route(TaskType.SCRIPTWRITING, project_id=local_proj.id)
    assert route_local.provider == "ollama"
    assert route_local.model == "qwen3.5:9b"
    assert route_local.is_cloud is False

    cloud_proj = await project_repo.create(
        title="Custom Cloud Project",
        topic="LLM Eval",
        config={"llm_provider": "gemini", "llm_model": "gemini-2.5-pro"},
        budget_usd=2.0,
    )
    route_cloud = await router.resolve_route(TaskType.SCRIPTWRITING, project_id=cloud_proj.id)
    assert route_cloud.provider == "gemini"
    assert route_cloud.model == "gemini-2.5-pro"
    assert route_cloud.is_cloud is True


@pytest.mark.asyncio
async def test_router_hybrid_tiered_cloud_tasks_routing(
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    cfg = _make_settings(
        tmp_path,
        LOCAL_ONLY=False,
        PREFER_CLOUD_DEFAULT=False,
        CLOUD_LLM_PROVIDER="openai",
        OPENAI_API_KEY="sk-test-key",
        OPENAI_DEFAULT_MODEL="gpt-4.1",
        OLLAMA_DEFAULT_MODEL="qwen3.5:9b",
        OLLAMA_FAST_MODEL="qwen2.5:3b",
        CLOUD_TASKS=["scriptwriting", "fact_check"],
        MAX_BUDGET_USD=5.0,
    )
    project_repo = ProjectRepository(db_session)
    project = await project_repo.create(
        title="Hybrid Tiered",
        topic="Vector Databases",
        budget_usd=2.0,
    )
    router = ModelRouter(app_settings=cfg, project_repo=project_repo)

    # Lightweight step -> small fast local Ollama model
    qa_route = await router.resolve_route(TaskType.QA_REVIEW, project_id=project.id)
    assert qa_route.provider == "ollama"
    assert qa_route.model == "qwen2.5:3b"
    assert qa_route.is_cloud is False

    # Important step -> powerful OpenAI cloud model
    script_route = await router.resolve_route(TaskType.SCRIPTWRITING, project_id=project.id)
    assert script_route.provider == "openai"
    assert script_route.model == "gpt-4.1"
    assert script_route.is_cloud is True


@pytest.mark.asyncio
async def test_router_retries_transient_errors_and_cloud_outage_fallback(tmp_path: Path) -> None:
    cfg = _make_settings(
        tmp_path,
        LOCAL_ONLY=False,
        MAX_BUDGET_USD=5.0,
        LLM_MAX_RETRIES=1,
    )
    cloud = _FakeProvider(
        provider_name="gemini",
        is_cloud=True,
        outcomes=[
            LLMTransientError("503 service unavailable"),
            LLMTransientError("503 still unavailable"),
        ],
    )
    local = _FakeProvider(
        provider_name="ollama",
        is_cloud=False,
        outcomes=[
            LLMTransientError("temporary glitch"),
            LLMResponse(provider="ollama", model="qwen2.5-coder:14b", content="Recovered locally"),
        ],
    )
    router = ModelRouter(app_settings=cfg, local_provider=local, cloud_provider=cloud)

    resp, route = await router.generate(
        task=TaskType.GENERAL,
        messages=[LLMMessage(role="user", content="Hello")],
        prefer_cloud=True,
    )
    assert resp.content == "Recovered locally"
    assert route.provider == "ollama"
    assert route.fallback_reason == "cloud_provider_error"
    assert len(cloud.requests) == 2
    assert len(local.requests) == 2


@pytest.mark.asyncio
async def test_router_structured_output_repair_and_failure(
    tmp_path: Path,
    db_session: AsyncSession,
) -> None:
    cfg = _make_settings(tmp_path, LOCAL_ONLY=True, LLM_STRUCTURED_MAX_REPAIRS=1)
    project_repo = ProjectRepository(db_session)
    usage_repo = UsageRepository(db_session)
    project = await project_repo.create(title="Structured Test", topic="Pydantic Contracts")

    # Attempt 1 returns invalid schema (only 1 section), Attempt 2 repairs cleanly
    local = _FakeProvider(
        provider_name="ollama",
        is_cloud=False,
        outcomes=[
            LLMResponse(
                provider="ollama",
                model="qwen2.5-coder:14b",
                content='{"hook": "Great hook!", "sections": ["Only one"]}',
                usage=LLMUsage(prompt_tokens=100, completion_tokens=30, latency_ms=150),
            ),
            LLMResponse(
                provider="ollama",
                model="qwen2.5-coder:14b",
                content='{"hook": "Great hook!", "sections": ["Intro", "Demo"]}',
                usage=LLMUsage(prompt_tokens=150, completion_tokens=40, latency_ms=180),
            ),
        ],
    )
    router = ModelRouter(
        app_settings=cfg,
        local_provider=local,
        usage_repo=usage_repo,
        project_repo=project_repo,
    )

    result = await router.generate_structured(
        task=TaskType.SCRIPTWRITING,
        messages=[LLMMessage(role="user", content="Plan script")],
        response_model=_ScriptPlan,
        project_id=project.id,
        node_name="scriptwriter",
    )
    assert result.attempts == 2
    assert result.data.sections == ["Intro", "Demo"]
    assert len(await usage_repo.list_for_project(project.id)) == 2

    # Exhausting repair attempts raises StructuredOutputError
    failing_local = _FakeProvider(
        provider_name="ollama",
        is_cloud=False,
        outcomes=[
            LLMResponse(provider="ollama", model="m", content="not json"),
            LLMResponse(provider="ollama", model="m", content="still not json"),
        ],
    )
    failing_router = ModelRouter(app_settings=cfg, local_provider=failing_local)
    with pytest.raises(StructuredOutputError):
        await failing_router.generate_structured(
            task=TaskType.SCRIPTWRITING,
            messages=[LLMMessage(role="user", content="Plan")],
            response_model=_ScriptPlan,
        )
