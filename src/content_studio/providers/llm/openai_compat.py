import time
from typing import Any

import httpx

from content_studio.providers.llm.base import BaseLLMProvider
from content_studio.providers.llm.pricing import estimate_cost_usd
from content_studio.providers.llm.types import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMTransientError,
    LLMUsage,
    ProviderHealth,
)


class OpenAICompatibleProvider(BaseLLMProvider):
    """Cloud LLM adapter for OpenAI and any OpenAI-compatible API (OpenRouter, Groq, DeepSeek)."""

    is_cloud = True

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.openai.com/v1",
        provider_name: str = "openai",
        default_timeout: float = 180.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.provider_name = provider_name
        self._api_key = (api_key or "").strip() or None
        self._base_url = base_url.rstrip("/")
        self._default_timeout = default_timeout
        self._transport = transport

    @property
    def is_configured(self) -> bool:
        return self._api_key is not None

    def _build_client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            transport=self._transport,
        )

    def _build_payload(self, request: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.json_mode or request.json_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key:
            raise LLMConfigurationError(f"{self.provider_name} API key is not configured.")

        timeout = request.timeout_seconds or self._default_timeout
        payload = self._build_payload(request)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self.provider_name == "openrouter":
            headers["X-Title"] = "Santosh Analytics AI Content Studio"
            headers["HTTP-Referer"] = "http://localhost:8501"

        start = time.perf_counter()
        try:
            async with self._build_client(timeout) as client:
                response = await client.post(
                    "/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"{self.provider_name} request to '{request.model}' timed out after {timeout}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMTransientError(f"Failed to reach {self.provider_name} API: {exc}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code >= 500 or response.status_code == 429:
            raise LLMTransientError(
                f"{self.provider_name} returned transient HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
        if response.status_code >= 400:
            raise LLMProviderError(
                f"{self.provider_name} returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError(f"{self.provider_name} returned invalid JSON response.") from exc

        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise LLMProviderError(f"{self.provider_name} returned no choices: {data!r}")

        first = choices[0]
        content = str((first.get("message") or {}).get("content") or "")
        if not content:
            raise LLMProviderError(f"{self.provider_name} choice contained empty text: {first!r}")

        usage_meta = data.get("usage") or {}
        prompt_tokens = int(usage_meta.get("prompt_tokens") or 0)
        completion_tokens = int(usage_meta.get("completion_tokens") or 0)
        cost = estimate_cost_usd(
            provider=self.provider_name,
            model=request.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResponse(
            provider=self.provider_name,
            model=str(data.get("model") or request.model),
            content=content,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost_usd=cost,
                latency_ms=latency_ms,
            ),
            finish_reason=str(first.get("finish_reason") or "stop"),
            raw_metadata={"finish_reason": first.get("finish_reason")},
        )

    async def health_check(self) -> ProviderHealth:
        if not self._api_key:
            return ProviderHealth(
                provider=self.provider_name,
                is_cloud=self.is_cloud,
                available=False,
                base_url=self._base_url,
                models=[],
                error="API key not configured",
            )
        preset_models = (
            ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"]
            if self.provider_name == "openai"
            else []
        )
        return ProviderHealth(
            provider=self.provider_name,
            is_cloud=self.is_cloud,
            available=True,
            base_url=self._base_url,
            models=preset_models,
            error=None,
        )
