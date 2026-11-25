import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from content_studio.config.settings import Settings
from content_studio.database.models.registered_model import RegisteredModel
from content_studio.database.repositories import ModelRegistryRepository
from content_studio.providers.llm import (
    AnthropicProvider,
    BaseLLMProvider,
    GeminiProvider,
    LLMError,
    LLMMessage,
    LLMRequest,
    OllamaProvider,
    OpenAICompatibleProvider,
)
from content_studio.services.artifact_service import ResourceNotFoundError

_KEY_VAULT_FILENAME = ".model_registry_keys.json"

PROVIDER_DEFAULT_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "openai_compatible": "https://openrouter.ai/api/v1",
}


class ModelPreset(BaseModel):
    label: str
    provider: str
    model_id: str
    base_url: str
    tier: str
    is_cloud: bool
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0
    notes: str = ""


RECOMMENDED_MODEL_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        label="Local Ollama — Qwen 2.5 3B (Free, Fast Small Tasks)",
        provider="ollama",
        model_id="qwen2.5:3b",
        base_url="http://localhost:11434",
        tier="local_small",
        is_cloud=False,
        notes="Ultra-fast local model ideal for Topic Strategy, QA, Metadata, and Asset Planning.",
    ),
    ModelPreset(
        label="Local Ollama — Qwen 3.5 9B (Free, General Local)",
        provider="ollama",
        model_id="qwen3.5:9b",
        base_url="http://localhost:11434",
        tier="local_small",
        is_cloud=False,
        notes="Stronger local model for research synthesis or local script drafts.",
    ),
    ModelPreset(
        label="OpenRouter — Auto Free Router (Always-Live Free Tier)",
        provider="openrouter",
        model_id="openrouter/free",
        base_url="https://openrouter.ai/api/v1",
        tier="cloud_free",
        is_cloud=True,
        notes="OpenRouter's official free auto-router — picks any available free model.",
    ),
    ModelPreset(
        label="OpenRouter — Gemma 4 31B Instruct (Free Tier)",
        provider="openrouter",
        model_id="google/gemma-4-31b-it:free",
        base_url="https://openrouter.ai/api/v1",
        tier="cloud_free",
        is_cloud=True,
        notes="Free 31B Google Gemma 4 on OpenRouter — strong multilingual & Hinglish.",
    ),
    ModelPreset(
        label="OpenRouter — Nemotron 3 Ultra 550B (Free Tier)",
        provider="openrouter",
        model_id="nvidia/nemotron-3-ultra-550b-a55b:free",
        base_url="https://openrouter.ai/api/v1",
        tier="cloud_free",
        is_cloud=True,
        notes="Free flagship reasoning model on OpenRouter — strong for fact-checking.",
    ),
    ModelPreset(
        label="OpenRouter — Gemini 2.5 Flash (Ultra-Cheap)",
        provider="openrouter",
        model_id="google/gemini-2.5-flash",
        base_url="https://openrouter.ai/api/v1",
        tier="cloud_powerful",
        is_cloud=True,
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
        notes="Very low-cost, high-speed model via OpenRouter with strong Hinglish & JSON output.",
    ),
    ModelPreset(
        label="Groq — Llama 3.3 70B Versatile (Free Tier, Ultra-Fast)",
        provider="groq",
        model_id="llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1",
        tier="cloud_free",
        is_cloud=True,
        notes="Free-tier Groq API with sub-second latency; needs a free console.groq.com key.",
    ),
    ModelPreset(
        label="Google Gemini — Gemini 2.5 Flash (Direct API)",
        provider="gemini",
        model_id="gemini-2.5-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        tier="cloud_powerful",
        is_cloud=True,
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
        notes="Direct Google AI Studio API (generous free tier & low paid cost).",
    ),
    ModelPreset(
        label="OpenAI — GPT-4.1 Mini (Direct API)",
        provider="openai",
        model_id="gpt-4.1-mini",
        base_url="https://api.openai.com/v1",
        tier="cloud_powerful",
        is_cloud=True,
        input_cost_per_1m=0.40,
        output_cost_per_1m=1.60,
        notes="Direct OpenAI API — reliable structured output & technical writing.",
    ),
    ModelPreset(
        label="Anthropic — Claude Sonnet 4 (Direct API)",
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        base_url="https://api.anthropic.com/v1",
        tier="cloud_powerful",
        is_cloud=True,
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
        notes="Flagship technical writing & Hinglish script quality via Anthropic API.",
    ),
)


class ModelConnectionTestResult(BaseModel):
    registry_id: str
    name: str
    provider: str
    model_id: str
    ok: bool
    latency_ms: int = 0
    reply_preview: str | None = None
    error: str | None = None


def mask_api_key(api_key: str | None) -> str | None:
    if not api_key or not api_key.strip():
        return None
    cleaned = api_key.strip()
    if len(cleaned) <= 8:
        return "****"
    return f"{cleaned[:5]}...{cleaned[-4:]}"


class ModelRegistryKeyStore:
    """Local gitignored key vault under data/.model_registry_keys.json (never stored in SQLite)."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir.resolve() / _KEY_VAULT_FILENAME

    def _read_all(self) -> dict[str, str]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {str(k): str(v) for k, v in raw.items() if v}
        except (OSError, ValueError):
            return {}
        return {}

    def _write_all(self, mapping: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def set_key(self, registry_id: str, api_key: str) -> None:
        cleaned = api_key.strip()
        if not cleaned:
            return
        data = self._read_all()
        data[registry_id] = cleaned
        self._write_all(data)

    def get_key(self, registry_id: str) -> str | None:
        return self._read_all().get(registry_id)

    def delete_key(self, registry_id: str) -> None:
        data = self._read_all()
        if registry_id in data:
            del data[registry_id]
            self._write_all(data)


class ModelRegistryService:
    """Manages user-registered local & cloud models and builds provider adapters for them."""

    def __init__(
        self,
        *,
        app_settings: Settings,
        registry_repo: ModelRegistryRepository,
        key_store: ModelRegistryKeyStore | None = None,
    ) -> None:
        self._settings = app_settings
        self._repo = registry_repo
        self._keys = key_store or ModelRegistryKeyStore(app_settings.resolved_data_dir)

    @property
    def key_store(self) -> ModelRegistryKeyStore:
        return self._keys

    async def register_model(
        self,
        *,
        name: str,
        provider: str,
        model_id: str,
        base_url: str | None = None,
        api_key: str | None = None,
        tier: str | None = None,
        input_cost_per_1m: float = 0.0,
        output_cost_per_1m: float = 0.0,
        notes: str | None = None,
    ) -> RegisteredModel:
        prov = provider.strip().lower()
        existing = await self._repo.get_by_name(name)
        if existing is not None:
            raise ValueError(f"A registered model named '{name.strip()}' already exists.")

        is_cloud = prov != "ollama"
        effective_url = (base_url or "").strip() or PROVIDER_DEFAULT_BASE_URLS.get(
            prov, "https://openrouter.ai/api/v1"
        )
        effective_tier = (tier or "").strip().lower() or (
            "local_small"
            if not is_cloud
            else (
                "cloud_free"
                if (input_cost_per_1m == 0.0 and output_cost_per_1m == 0.0)
                else "cloud_powerful"
            )
        )
        row = await self._repo.create(
            name=name,
            provider=prov,
            model_id=model_id,
            base_url=effective_url,
            tier=effective_tier,
            is_cloud=is_cloud,
            input_cost_per_1m=input_cost_per_1m,
            output_cost_per_1m=output_cost_per_1m,
            notes=notes,
        )
        if api_key and api_key.strip():
            self._keys.set_key(row.id, api_key)
        return row

    async def list_models(self, *, active_only: bool = False) -> list[RegisteredModel]:
        return list(await self._repo.list_all(active_only=active_only))

    async def get_model(self, registry_id: str) -> RegisteredModel:
        row = await self._repo.get_by_id(registry_id)
        if row is None:
            raise ResourceNotFoundError(f"Registered model '{registry_id}' not found.")
        return row

    async def update_model(
        self,
        registry_id: str,
        *,
        name: str | None = None,
        provider: str | None = None,
        model_id: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        tier: str | None = None,
        input_cost_per_1m: float | None = None,
        output_cost_per_1m: float | None = None,
        is_active: bool | None = None,
        notes: str | None = None,
    ) -> RegisteredModel:
        row = await self.get_model(registry_id)
        is_cloud = (provider.strip().lower() != "ollama") if provider is not None else None
        updated = await self._repo.update(
            row,
            name=name,
            provider=provider,
            model_id=model_id,
            base_url=base_url,
            tier=tier,
            is_cloud=is_cloud,
            input_cost_per_1m=input_cost_per_1m,
            output_cost_per_1m=output_cost_per_1m,
            is_active=is_active,
            notes=notes,
        )
        if api_key is not None and api_key.strip():
            self._keys.set_key(updated.id, api_key)
        return updated

    async def delete_model(self, registry_id: str) -> None:
        row = await self.get_model(registry_id)
        self._keys.delete_key(row.id)
        await self._repo.delete(row)

    def key_metadata(self, registry_id: str) -> tuple[bool, str | None]:
        raw = self._keys.get_key(registry_id)
        return bool(raw), mask_api_key(raw)

    def build_provider_for_model(self, entry: RegisteredModel) -> BaseLLMProvider:
        prov = entry.provider.strip().lower()
        api_key = self._keys.get_key(entry.id)
        timeout = self._settings.LLM_TIMEOUT_SECONDS

        if prov == "ollama":
            return OllamaProvider(base_url=entry.base_url, default_timeout=timeout)
        if prov == "gemini":
            return GeminiProvider(
                api_key=api_key or self._settings.GEMINI_API_KEY,
                base_url=entry.base_url,
                default_timeout=timeout,
            )
        if prov == "anthropic":
            return AnthropicProvider(
                api_key=api_key or self._settings.ANTHROPIC_API_KEY,
                base_url=entry.base_url,
                default_timeout=timeout,
            )
        # openai, openrouter, groq, openai_compatible
        fallback_key = (
            self._settings.OPENAI_API_KEY if prov == "openai" else self._settings.CLOUD_API_KEY
        )
        return OpenAICompatibleProvider(
            api_key=api_key or fallback_key,
            base_url=entry.base_url,
            provider_name=prov,
            default_timeout=timeout,
        )

    async def test_model_connection(self, registry_id: str) -> ModelConnectionTestResult:
        entry = await self.get_model(registry_id)
        provider = self.build_provider_for_model(entry)
        start = time.perf_counter()
        try:
            resp = await provider.generate(
                LLMRequest(
                    model=entry.model_id,
                    messages=[
                        LLMMessage(
                            role="user",
                            content="Reply with exactly one word: OK",
                        )
                    ],
                    temperature=0.0,
                    max_tokens=256,
                    timeout_seconds=30.0,
                )
            )
            elapsed = int((time.perf_counter() - start) * 1000)
            return ModelConnectionTestResult(
                registry_id=entry.id,
                name=entry.name,
                provider=entry.provider,
                model_id=entry.model_id,
                ok=True,
                latency_ms=elapsed,
                reply_preview=resp.content.strip()[:120],
            )
        except (LLMError, OSError, ValueError) as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            return ModelConnectionTestResult(
                registry_id=entry.id,
                name=entry.name,
                provider=entry.provider,
                model_id=entry.model_id,
                ok=False,
                latency_ms=elapsed,
                error=str(exc),
            )

    def list_presets(self) -> list[dict[str, Any]]:
        return [p.model_dump() for p in RECOMMENDED_MODEL_PRESETS]
