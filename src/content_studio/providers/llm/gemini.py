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


class GeminiProvider(BaseLLMProvider):
    """Configurable cloud LLM adapter using the Gemini REST API."""

    provider_name = "gemini"
    is_cloud = True

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        default_timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
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
        system_parts: list[dict[str, str]] = []
        contents: list[dict[str, Any]] = []

        for msg in request.messages:
            if msg.role == "system":
                system_parts.append({"text": msg.content})
            else:
                gemini_role = "model" if msg.role == "assistant" else "user"
                contents.append({"role": gemini_role, "parts": [{"text": msg.content}]})

        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Proceed."}]})

        generation_config: dict[str, Any] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            generation_config["maxOutputTokens"] = request.max_tokens
        if request.json_mode or request.json_schema is not None:
            generation_config["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        return payload

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key:
            raise LLMConfigurationError("Gemini API key is not configured.")

        timeout = request.timeout_seconds or self._default_timeout
        payload = self._build_payload(request)
        endpoint = f"/models/{request.model}:generateContent"

        start = time.perf_counter()
        try:
            async with self._build_client(timeout) as client:
                response = await client.post(
                    endpoint,
                    headers={"x-goog-api-key": self._api_key},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Gemini request to model '{request.model}' timed out after {timeout}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMTransientError(f"Failed to reach Gemini API: {exc}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code >= 500 or response.status_code == 429:
            raise LLMTransientError(
                f"Gemini returned transient HTTP {response.status_code}: {response.text[:300]}"
            )
        if response.status_code >= 400:
            raise LLMProviderError(
                f"Gemini returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError("Gemini returned invalid JSON response.") from exc

        candidates = data.get("candidates") or []
        if not candidates or not isinstance(candidates[0], dict):
            raise LLMProviderError(f"Gemini returned no candidates: {data!r}")

        first = candidates[0]
        parts = first.get("content", {}).get("parts", [])
        text_chunks = [
            str(part["text"]) for part in parts if isinstance(part, dict) and "text" in part
        ]
        content = "".join(text_chunks)
        if not content:
            raise LLMProviderError(f"Gemini candidate contained empty text: {first!r}")

        usage_meta = data.get("usageMetadata") or {}
        prompt_tokens = int(usage_meta.get("promptTokenCount") or 0)
        completion_tokens = int(usage_meta.get("candidatesTokenCount") or 0)
        cost = estimate_cost_usd(
            provider=self.provider_name,
            model=request.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResponse(
            provider=self.provider_name,
            model=request.model,
            content=content,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost_usd=cost,
                latency_ms=latency_ms,
            ),
            finish_reason=str(first.get("finishReason") or "STOP"),
            raw_metadata={"finishReason": first.get("finishReason")},
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
        return ProviderHealth(
            provider=self.provider_name,
            is_cloud=self.is_cloud,
            available=True,
            base_url=self._base_url,
            models=[],
            error=None,
        )
