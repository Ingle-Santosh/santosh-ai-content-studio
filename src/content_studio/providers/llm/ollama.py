import time
from typing import Any

import httpx

from content_studio.providers.llm.base import BaseLLMProvider
from content_studio.providers.llm.types import (
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMTransientError,
    LLMUsage,
    ProviderHealth,
)


class OllamaProvider(BaseLLMProvider):
    """Local-first LLM adapter communicating with Ollama's REST API."""

    provider_name = "ollama"
    is_cloud = False

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        default_timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_timeout = default_timeout
        self._transport = transport

    def _build_client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            transport=self._transport,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        timeout = request.timeout_seconds or self._default_timeout
        options: dict[str, Any] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens

        body: dict[str, Any] = {
            "model": request.model,
            "messages": [msg.model_dump() for msg in request.messages],
            "stream": False,
            "options": options,
        }
        if request.json_schema is not None:
            body["format"] = request.json_schema
        elif request.json_mode:
            body["format"] = "json"

        start = time.perf_counter()
        try:
            async with self._build_client(timeout) as client:
                response = await client.post("/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Ollama request to model '{request.model}' timed out after {timeout}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMTransientError(f"Failed to reach Ollama at {self._base_url}: {exc}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code >= 500 or response.status_code == 429:
            raise LLMTransientError(
                f"Ollama returned transient HTTP {response.status_code}: {response.text[:300]}"
            )
        if response.status_code >= 400:
            raise LLMProviderError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError("Ollama returned invalid JSON response.") from exc

        message = data.get("message")
        if not isinstance(message, dict) or "content" not in message:
            raise LLMProviderError(f"Unexpected Ollama response format: {data!r}")

        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        completion_tokens = int(data.get("eval_count") or 0)

        return LLMResponse(
            provider=self.provider_name,
            model=str(data.get("model") or request.model),
            content=str(message["content"]),
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost_usd=0.0,
                latency_ms=latency_ms,
            ),
            finish_reason=str(data.get("done_reason") or ("stop" if data.get("done") else "")),
            raw_metadata={"done": data.get("done", True)},
        )

    async def health_check(self) -> ProviderHealth:
        try:
            async with self._build_client(timeout=3.0) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return ProviderHealth(
                provider=self.provider_name,
                is_cloud=self.is_cloud,
                available=False,
                base_url=self._base_url,
                models=[],
                error=str(exc),
            )

        models = [
            str(item["name"])
            for item in payload.get("models", [])
            if isinstance(item, dict) and "name" in item
        ]
        return ProviderHealth(
            provider=self.provider_name,
            is_cloud=self.is_cloud,
            available=True,
            base_url=self._base_url,
            models=models,
            error=None,
        )
