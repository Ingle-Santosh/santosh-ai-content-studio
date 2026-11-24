import json

import httpx
import pytest
from pydantic import BaseModel, Field

from content_studio.providers.llm import (
    GeminiProvider,
    LLMConfigurationError,
    LLMMessage,
    LLMProviderError,
    LLMRequest,
    LLMTimeoutError,
    LLMTransientError,
    OllamaProvider,
    StructuredOutputError,
    parse_structured_output,
)


class _SampleBrief(BaseModel):
    angle: str = Field(min_length=3)
    key_points: list[str] = Field(min_length=1)


@pytest.mark.asyncio
async def test_ollama_provider_generate_and_health() -> None:
    captured_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            captured_payload.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                json={
                    "model": "qwen2.5-coder:14b",
                    "message": {"role": "assistant", "content": '{"angle": "Deep Dive"}'},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 120,
                    "eval_count": 45,
                },
            )
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": "qwen2.5-coder:14b"}, {"name": "llama3.1:8b"}]},
            )
        return httpx.Response(404)

    provider = OllamaProvider(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )

    resp = await provider.generate(
        LLMRequest(
            model="qwen2.5-coder:14b",
            messages=[LLMMessage(role="user", content="Explain RAG")],
            json_mode=True,
        )
    )
    assert resp.provider == "ollama"
    assert resp.usage.prompt_tokens == 120
    assert resp.usage.completion_tokens == 45
    assert resp.usage.estimated_cost_usd == 0.0
    assert captured_payload["format"] == "json"

    health = await provider.health_check()
    assert health.available is True
    assert "qwen2.5-coder:14b" in health.models


@pytest.mark.asyncio
async def test_ollama_provider_error_classification() -> None:
    def transient_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="overloaded")

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    def bad_request_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="model not found")

    req = LLMRequest(model="missing", messages=[LLMMessage(role="user", content="hi")])

    with pytest.raises(LLMTransientError):
        await OllamaProvider(transport=httpx.MockTransport(transient_handler)).generate(req)

    with pytest.raises(LLMTimeoutError):
        await OllamaProvider(transport=httpx.MockTransport(timeout_handler)).generate(req)

    with pytest.raises(LLMProviderError):
        await OllamaProvider(transport=httpx.MockTransport(bad_request_handler)).generate(req)


@pytest.mark.asyncio
async def test_gemini_provider_generate_headers_and_cost() -> None:
    captured_headers: dict[str, str] = {}
    captured_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        captured_body.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": '{"angle": "Cloud Synthesis"}'}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 1000,
                    "candidatesTokenCount": 500,
                },
            },
        )

    provider = GeminiProvider(
        api_key="test-secret-key",
        transport=httpx.MockTransport(handler),
    )
    resp = await provider.generate(
        LLMRequest(
            model="gemini-2.5-flash",
            messages=[
                LLMMessage(role="system", content="You are an educator."),
                LLMMessage(role="user", content="Compare RAG vs CAG"),
            ],
            json_mode=True,
        )
    )
    assert captured_headers.get("x-goog-api-key") == "test-secret-key"
    assert captured_body["generationConfig"]["responseMimeType"] == "application/json"
    assert "systemInstruction" in captured_body
    assert resp.provider == "gemini"
    assert resp.usage.prompt_tokens == 1000
    assert resp.usage.completion_tokens == 500
    assert resp.usage.estimated_cost_usd > 0.0

    # Missing key raises LLMConfigurationError
    unconfigured = GeminiProvider(api_key=None)
    with pytest.raises(LLMConfigurationError):
        await unconfigured.generate(
            LLMRequest(model="gemini-2.5-flash", messages=[LLMMessage(role="user", content="hi")])
        )


def test_parse_structured_output_handles_fences_and_rejects_invalid() -> None:
    fenced = (
        "Sure! Here is your JSON:\n"
        '```json\n{"angle": "Practical RAG", "key_points": ["Chunking"]}\n```'
    )
    parsed = parse_structured_output(fenced, _SampleBrief)
    assert parsed.angle == "Practical RAG"
    assert parsed.key_points == ["Chunking"]

    with pytest.raises(StructuredOutputError):
        parse_structured_output('{"angle": "x", "key_points": []}', _SampleBrief)

    with pytest.raises(StructuredOutputError):
        parse_structured_output("not json at all", _SampleBrief)
