import asyncio
import json
import logging
from dataclasses import dataclass

from pydantic import BaseModel

from content_studio.config.settings import Settings
from content_studio.database.models.project import Project
from content_studio.database.repositories.project_repository import ProjectRepository
from content_studio.database.repositories.usage_repository import UsageRepository
from content_studio.providers.llm.anthropic import AnthropicProvider
from content_studio.providers.llm.base import BaseLLMProvider
from content_studio.providers.llm.gemini import GeminiProvider
from content_studio.providers.llm.ollama import OllamaProvider
from content_studio.providers.llm.openai_compat import OpenAICompatibleProvider
from content_studio.providers.llm.structured import parse_structured_output
from content_studio.providers.llm.types import (
    BudgetExceededError,
    LLMConfigurationError,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMTransientError,
    ProviderHealth,
    RouteDecision,
    StructuredOutputError,
    TaskType,
)

logger = logging.getLogger(__name__)

_WRITING_TASKS: frozenset[TaskType] = frozenset(
    {
        TaskType.TOPIC_STRATEGY,
        TaskType.SCRIPTWRITING,
        TaskType.STORYBOARD,
        TaskType.METADATA,
    }
)
_FAST_TASKS: frozenset[TaskType] = frozenset(
    {
        TaskType.QA_REVIEW,
        TaskType.ASSET_PLANNING,
    }
)


@dataclass(slots=True)
class StructuredResult[T: BaseModel]:
    data: T
    response: LLMResponse
    route: RouteDecision
    attempts: int


class ModelRouter:
    """Routes LLM tasks across local and optional cloud providers with guardrails.

    Enforces:
    - Local-first operation when ``LOCAL_ONLY=True``.
    - Global and per-project USD budget caps before any cloud call.
    - Bounded exponential-backoff retries on transient errors.
    - Graceful fallback to local Ollama on cloud provider outages.
    - Strict Pydantic structured output validation with bounded repair turns.
    - Automatic usage/cost persistence into ``llm_usage_logs`` and ``projects.spent_usd``.
    """

    def __init__(
        self,
        *,
        app_settings: Settings,
        local_provider: BaseLLMProvider | None = None,
        cloud_provider: BaseLLMProvider | None = None,
        usage_repo: UsageRepository | None = None,
        project_repo: ProjectRepository | None = None,
    ) -> None:
        self._settings = app_settings
        self._local_provider: BaseLLMProvider = local_provider or OllamaProvider(
            base_url=app_settings.OLLAMA_BASE_URL,
            default_timeout=app_settings.LLM_TIMEOUT_SECONDS,
        )
        self._cloud_provider: BaseLLMProvider | None = cloud_provider or self._build_default_cloud(
            app_settings
        )
        self._usage_repo = usage_repo
        self._project_repo = project_repo

    @staticmethod
    def _resolve_cloud_api_key(app_settings: Settings, provider_name: str) -> str | None:
        specific: str | None = None
        if provider_name == "gemini":
            specific = app_settings.GEMINI_API_KEY
        elif provider_name == "openai":
            specific = app_settings.OPENAI_API_KEY
        elif provider_name == "anthropic":
            specific = app_settings.ANTHROPIC_API_KEY
        chosen = (specific or "").strip() or (app_settings.CLOUD_API_KEY or "").strip()
        return chosen or None

    @staticmethod
    def _resolve_cloud_base_url(app_settings: Settings, provider_name: str) -> str:
        override = (app_settings.CLOUD_BASE_URL or "").strip()
        if override:
            return override
        if provider_name == "gemini":
            return app_settings.GEMINI_BASE_URL
        if provider_name == "anthropic":
            return app_settings.ANTHROPIC_BASE_URL
        return app_settings.OPENAI_BASE_URL

    @classmethod
    def _build_default_cloud(cls, app_settings: Settings) -> BaseLLMProvider | None:
        provider_name = app_settings.CLOUD_LLM_PROVIDER.strip().lower()
        api_key = cls._resolve_cloud_api_key(app_settings, provider_name)
        if not api_key:
            return None

        base_url = cls._resolve_cloud_base_url(app_settings, provider_name)
        if provider_name == "gemini":
            return GeminiProvider(
                api_key=api_key,
                base_url=base_url,
                default_timeout=app_settings.LLM_TIMEOUT_SECONDS,
            )
        if provider_name == "anthropic":
            return AnthropicProvider(
                api_key=api_key,
                base_url=base_url,
                default_timeout=app_settings.LLM_TIMEOUT_SECONDS,
            )
        if provider_name in {"openai", "openai_compatible"}:
            return OpenAICompatibleProvider(
                api_key=api_key,
                base_url=base_url,
                provider_name=provider_name,
                default_timeout=app_settings.LLM_TIMEOUT_SECONDS,
            )
        return None

    def local_model_for_task(self, task: TaskType) -> str:
        if task in _WRITING_TASKS and self._settings.OLLAMA_WRITING_MODEL:
            return self._settings.OLLAMA_WRITING_MODEL
        if task in _FAST_TASKS and self._settings.OLLAMA_FAST_MODEL:
            return self._settings.OLLAMA_FAST_MODEL
        return self._settings.OLLAMA_DEFAULT_MODEL

    def cloud_model_for_task(self, _task: TaskType) -> str:
        override = (self._settings.CLOUD_DEFAULT_MODEL or "").strip()
        if override:
            return override
        provider_name = self._settings.CLOUD_LLM_PROVIDER.strip().lower()
        if provider_name == "openai":
            return self._settings.OPENAI_DEFAULT_MODEL
        if provider_name == "anthropic":
            return self._settings.ANTHROPIC_DEFAULT_MODEL
        return self._settings.GEMINI_DEFAULT_MODEL

    def describe_routing_table(self) -> dict[str, dict[str, object]]:
        table: dict[str, dict[str, object]] = {}
        for task in TaskType:
            decision = self._decide_route(
                task=task,
                prefer_cloud=self._settings.PREFER_CLOUD_DEFAULT,
                strict_cloud=False,
                project=None,
                current_global_spend=0.0,
            )
            table[task.value] = decision.model_dump()
        return table

    def _decide_route(
        self,
        *,
        task: TaskType,
        prefer_cloud: bool,
        strict_cloud: bool,
        project: Project | None,
        current_global_spend: float,
    ) -> RouteDecision:
        project_cfg = project.config if project is not None else {}
        project_provider = str(project_cfg.get("llm_provider") or "default").strip().lower()
        raw_project_model = project_cfg.get("llm_model")
        project_model = str(raw_project_model).strip() if raw_project_model else None

        local_model = (
            project_model
            if (project_provider == "ollama" and project_model)
            else self.local_model_for_task(task)
        )
        if project_provider == "ollama" and not strict_cloud:
            return RouteDecision(
                task=task,
                provider=self._local_provider.provider_name,
                model=local_model,
                is_cloud=False,
            )

        project_allows_cloud = bool(project_cfg.get("cloud_fallback_enabled", False))
        task_prefers_cloud = task.value in {
            item.strip().lower() for item in self._settings.CLOUD_TASKS
        }
        project_wants_cloud = project_provider in {
            "cloud",
            "gemini",
            "openai",
            "anthropic",
            "openai_compatible",
        }
        wants_cloud = (
            prefer_cloud
            or self._settings.PREFER_CLOUD_DEFAULT
            or task_prefers_cloud
            or project_allows_cloud
            or project_wants_cloud
        )

        if not wants_cloud:
            return RouteDecision(
                task=task,
                provider=self._local_provider.provider_name,
                model=local_model,
                is_cloud=False,
            )

        if self._settings.LOCAL_ONLY:
            if strict_cloud:
                raise BudgetExceededError("Cloud LLM calls are disabled because LOCAL_ONLY=true.")
            return RouteDecision(
                task=task,
                provider=self._local_provider.provider_name,
                model=local_model,
                is_cloud=False,
                fallback_reason="local_only_mode",
            )

        if self._cloud_provider is None:
            if strict_cloud:
                raise LLMConfigurationError("No cloud LLM provider is configured.")
            return RouteDecision(
                task=task,
                provider=self._local_provider.provider_name,
                model=local_model,
                is_cloud=False,
                fallback_reason="cloud_provider_unavailable",
            )

        if (
            self._settings.MAX_BUDGET_USD <= 0.0
            or current_global_spend >= self._settings.MAX_BUDGET_USD
        ):
            if strict_cloud:
                raise BudgetExceededError(
                    f"Global LLM budget exhausted (${current_global_spend:.4f} / "
                    f"${self._settings.MAX_BUDGET_USD:.4f})."
                )
            return RouteDecision(
                task=task,
                provider=self._local_provider.provider_name,
                model=local_model,
                is_cloud=False,
                fallback_reason="global_budget_exhausted",
            )

        if project is not None and (
            project.budget_usd <= 0.0 or project.spent_usd >= project.budget_usd
        ):
            if strict_cloud:
                raise BudgetExceededError(
                    f"Project budget exhausted (${project.spent_usd:.4f} / "
                    f"${project.budget_usd:.4f})."
                )
            return RouteDecision(
                task=task,
                provider=self._local_provider.provider_name,
                model=local_model,
                is_cloud=False,
                fallback_reason="project_budget_exhausted",
            )

        cloud_model = (
            project_model
            if (project_wants_cloud and project_model)
            else self.cloud_model_for_task(task)
        )
        return RouteDecision(
            task=task,
            provider=self._cloud_provider.provider_name,
            model=cloud_model,
            is_cloud=True,
        )

    async def resolve_route(
        self,
        task: TaskType,
        *,
        project_id: str | None = None,
        prefer_cloud: bool = False,
        strict_cloud: bool = False,
    ) -> RouteDecision:
        project: Project | None = None
        if project_id is not None and self._project_repo is not None:
            project = await self._project_repo.get_by_id(project_id)

        global_spend = 0.0
        if self._usage_repo is not None:
            global_spend = await self._usage_repo.total_spend_all()

        return self._decide_route(
            task=task,
            prefer_cloud=prefer_cloud,
            strict_cloud=strict_cloud,
            project=project,
            current_global_spend=global_spend,
        )

    async def _invoke_with_retries(
        self,
        provider: BaseLLMProvider,
        request: LLMRequest,
    ) -> LLMResponse:
        max_attempts = 1 + self._settings.LLM_MAX_RETRIES
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            try:
                return await provider.generate(request)
            except LLMTransientError as exc:
                last_error = exc
                if attempt + 1 >= max_attempts:
                    break
                delay = self._settings.LLM_RETRY_BASE_DELAY_SECONDS * (2**attempt)
                logger.warning(
                    "Transient LLM error on %s/%s (attempt %d/%d): %s. Retrying in %.2fs.",
                    provider.provider_name,
                    request.model,
                    attempt + 1,
                    max_attempts,
                    exc,
                    delay,
                )
                if delay > 0:
                    await asyncio.sleep(delay)

        assert last_error is not None
        raise last_error

    async def _record_usage(
        self,
        *,
        response: LLMResponse,
        node_name: str,
        project_id: str | None,
        run_id: str | None,
    ) -> None:
        if project_id is None or self._usage_repo is None:
            return

        await self._usage_repo.create(
            project_id=project_id,
            run_id=run_id,
            provider=response.provider,
            model=response.model,
            node_name=node_name,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            estimated_cost_usd=response.usage.estimated_cost_usd,
            latency_ms=response.usage.latency_ms,
        )

        if self._project_repo is not None and response.usage.estimated_cost_usd > 0.0:
            project = await self._project_repo.get_by_id(project_id)
            if project is not None:
                updated_spend = round(project.spent_usd + response.usage.estimated_cost_usd, 8)
                await self._project_repo.update(project, spent_usd=updated_spend)

    async def generate(
        self,
        *,
        task: TaskType,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_mode: bool = False,
        json_schema: dict | None = None,
        timeout_seconds: float | None = None,
        node_name: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        prefer_cloud: bool = False,
        strict_cloud: bool = False,
        fallback_to_local_on_error: bool = True,
    ) -> tuple[LLMResponse, RouteDecision]:
        route = await self.resolve_route(
            task,
            project_id=project_id,
            prefer_cloud=prefer_cloud,
            strict_cloud=strict_cloud,
        )
        effective_node = node_name or task.value

        provider = (
            self._cloud_provider
            if route.is_cloud and self._cloud_provider is not None
            else self._local_provider
        )
        request = LLMRequest(
            messages=messages,
            model=route.model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            json_schema=json_schema,
            timeout_seconds=timeout_seconds or self._settings.LLM_TIMEOUT_SECONDS,
        )

        try:
            response = await self._invoke_with_retries(provider, request)
        except LLMTransientError:
            if route.is_cloud and fallback_to_local_on_error and not strict_cloud:
                logger.warning(
                    "Cloud provider %s failed for task %s; falling back to local %s.",
                    provider.provider_name,
                    task.value,
                    self._local_provider.provider_name,
                )
                route = RouteDecision(
                    task=task,
                    provider=self._local_provider.provider_name,
                    model=self.local_model_for_task(task),
                    is_cloud=False,
                    fallback_reason="cloud_provider_error",
                )
                fallback_request = request.model_copy(update={"model": route.model})
                response = await self._invoke_with_retries(self._local_provider, fallback_request)
            else:
                raise

        await self._record_usage(
            response=response,
            node_name=effective_node,
            project_id=project_id,
            run_id=run_id,
        )
        return response, route

    async def generate_structured[T: BaseModel](
        self,
        *,
        task: TaskType,
        messages: list[LLMMessage],
        response_model: type[T],
        temperature: float = 0.1,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
        node_name: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        prefer_cloud: bool = False,
        strict_cloud: bool = False,
    ) -> StructuredResult[T]:
        schema = response_model.model_json_schema()
        schema_instruction = LLMMessage(
            role="system",
            content=(
                "Respond with valid JSON ONLY (no extra prose) conforming strictly to this "
                f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
            ),
        )
        conversation = [schema_instruction, *messages]

        max_attempts = 1 + self._settings.LLM_STRUCTURED_MAX_REPAIRS
        last_error: StructuredOutputError | None = None

        for attempt in range(1, max_attempts + 1):
            response, route = await self.generate(
                task=task,
                messages=conversation,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
                json_schema=schema,
                timeout_seconds=timeout_seconds,
                node_name=node_name,
                project_id=project_id,
                run_id=run_id,
                prefer_cloud=prefer_cloud,
                strict_cloud=strict_cloud,
            )
            try:
                parsed = parse_structured_output(response.content, response_model)
                return StructuredResult(
                    data=parsed,
                    response=response,
                    route=route,
                    attempts=attempt,
                )
            except StructuredOutputError as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                conversation.append(LLMMessage(role="assistant", content=response.content or "{}"))
                conversation.append(
                    LLMMessage(
                        role="user",
                        content=(
                            "Your previous JSON output failed validation with the following "
                            f"error:\n{exc}\n\n"
                            "Return ONLY a corrected JSON object matching the required schema."
                        ),
                    )
                )

        assert last_error is not None
        raise last_error

    async def check_providers_health(self) -> list[ProviderHealth]:
        checks = [self._local_provider.health_check()]
        if self._cloud_provider is not None:
            checks.append(self._cloud_provider.health_check())
        else:
            provider_name = self._settings.CLOUD_LLM_PROVIDER.strip().lower()
            checks.append(
                asyncio.sleep(
                    0,
                    result=ProviderHealth(
                        provider=provider_name,
                        is_cloud=True,
                        available=False,
                        base_url=self._resolve_cloud_base_url(self._settings, provider_name),
                        models=[],
                        error="Cloud API key not configured",
                    ),
                )
            )
        return list(await asyncio.gather(*checks))
