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


class AnthropicProvider(BaseLLMProvider):
    """Cloud LLM adapter using the Anthropic Messages REST API (Claude models)."""

    provider_name = "anthropic"
    is_cloud = True

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.anthropic.com/v1",
        default_timeout: float = 180.0,
        anthropic_version: str = "2023-06-01",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip() or None
        self._base_url = base_url.rstrip("/")
        self._default_timeout = default_timeout
        self._anthropic_version = anthropic_version
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
        system_chunks: list[str] = []
        messages: list[dict[str, str]] = []

        for msg in request.messages:
            if msg.role == "system":
                system_chunks.append(msg.content)
            else:
                messages.append({"role": msg.role, "content": msg.content})

        if not messages:
            messages.append({"role": "user", "content": "Proceed."})

        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
            "messages": messages,
        }
        if system_chunks:
            payload["system"] = "\n\n".join(system_chunks)
        return payload

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key:
            raise LLMConfigurationError("Anthropic API key is not configured.")

        timeout = request.timeout_seconds or self._default_timeout
        payload = self._build_payload(request)

        start = time.perf_counter()
        try:
            async with self._build_client(timeout) as client:
                response = await client.post(
                    "/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": self._anthropic_version,
                        "content-type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Anthropic request to '{request.model}' timed out after {timeout}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMTransientError(f"Failed to reach Anthropic API: {exc}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code >= 500 or response.status_code == 429:
            raise LLMTransientError(
                f"Anthropic returned transient HTTP {response.status_code}: {response.text[:300]}"
            )
        if response.status_code >= 400:
            raise LLMProviderError(
                f"Anthropic returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError("Anthropic returned invalid JSON response.") from exc

        blocks = data.get("content") or []
        text_chunks = [
            str(block["text"])
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block
        ]
        content = "".join(text_chunks)
        if not content:
            raise LLMProviderError(f"Anthropic response contained empty text: {data!r}")

        usage_meta = data.get("usage") or {}
        prompt_tokens = int(usage_meta.get("input_tokens") or 0)
        completion_tokens = int(usage_meta.get("output_tokens") or 0)
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
            finish_reason=str(data.get("stop_reason") or "end_turn"),
            raw_metadata={"stop_reason": data.get("stop_reason")},
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
            models=[
                "claude-sonnet-4-20250514",
                "claude-3-7-sonnet-latest",
                "claude-3-5-haiku-latest",
            ],
            error=None,
        )
