import httpx
import pytest

from content_studio.providers.search import DuckDuckGoSearchProvider, TavilySearchProvider
from content_studio.services.web_extractor import (
    WebExtractor,
    compute_url_hash,
    extract_domain,
    normalize_url,
)


def test_url_normalization_and_deduplication_hash() -> None:
    u1 = "HTTPS://Example.COM:443/docs/rag/?utm_source=twitter&b=2&a=1#section"
    u2 = "https://example.com/docs/rag?a=1&b=2&fbclid=abc123"
    assert normalize_url(u1) == "https://example.com/docs/rag?a=1&b=2"
    assert normalize_url(u2) == "https://example.com/docs/rag?a=1&b=2"
    assert compute_url_hash(normalize_url(u1)) == compute_url_hash(normalize_url(u2))
    assert extract_domain("https://www.docs.python.org/3/") == "docs.python.org"

    with pytest.raises(ValueError, match="Unsupported or invalid URL"):
        normalize_url("ftp://example.com/file")


@pytest.mark.asyncio
async def test_duckduckgo_and_tavily_search_providers() -> None:
    ddg_html = """
    <html><body>
      <div class="result">
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.example.com%2Frag">
          RAG Architecture Guide
        </a>
        <a class="result__snippet">Retrieval Augmented Generation combines search with LLMs.</a>
      </div>
      <div class="result">
        <a class="result__a" href="https://blog.example.org/cag">CAG Overview</a>
        <div class="result__snippet">Cache Augmented Generation preloads context.</div>
      </div>
    </body></html>
    """
    ddg = DuckDuckGoSearchProvider(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200, text=ddg_html))
    )
    ddg_results = await ddg.search("RAG vs CAG", max_results=5)
    assert len(ddg_results) == 2
    assert ddg_results[0].url == "https://docs.example.com/rag"
    assert ddg_results[0].title == "RAG Architecture Guide"
    assert "Retrieval Augmented Generation" in ddg_results[0].snippet

    captured_auth: list[str] = []

    def tavily_handler(request: httpx.Request) -> httpx.Response:
        captured_auth.append(request.headers.get("authorization", ""))
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Tavily RAG Paper",
                        "url": "https://arxiv.org/abs/2005.11401",
                        "content": "Original RAG paper summary.",
                    }
                ]
            },
        )

    tavily = TavilySearchProvider(
        api_key="tvly-test-key",
        transport=httpx.MockTransport(tavily_handler),
    )
    tavily_results = await tavily.search("RAG paper", max_results=3)
    assert captured_auth == ["Bearer tvly-test-key"]
    assert len(tavily_results) == 1
    assert tavily_results[0].provider == "tavily"


@pytest.mark.asyncio
async def test_web_extractor_handles_html_errors_and_timeouts() -> None:
    article_html = """
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <title>Understanding RAG Pipelines</title>
        <meta name="author" content="Santosh" />
      </head>
      <body>
        <article>
          <h1>Understanding RAG Pipelines</h1>
          <p>Retrieval-Augmented Generation grounds LLM answers in external documents.</p>
          <p>Chunking, embeddings, and hybrid search improve recall for technical queries.</p>
        </article>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/article":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=article_html,
            )
        if request.url.path == "/missing":
            return httpx.Response(404, text="Not Found")
        if request.url.path == "/pdf":
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")
        if request.url.path == "/timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")

    extractor = WebExtractor(transport=httpx.MockTransport(handler))

    ok_page = await extractor.fetch_and_extract("https://example.com/article")
    assert ok_page.succeeded is True
    assert ok_page.http_status == 200
    assert ok_page.word_count >= 10
    assert ok_page.checksum_sha256 is not None
    assert "Retrieval-Augmented Generation" in ok_page.text

    not_found = await extractor.fetch_and_extract("https://example.com/missing")
    assert not_found.succeeded is False
    assert not_found.http_status == 404
    assert not_found.error is not None

    binary = await extractor.fetch_and_extract("https://example.com/pdf")
    assert binary.succeeded is False
    assert "Unsupported content-type" in (binary.error or "")

    timed_out = await extractor.fetch_and_extract("https://example.com/timeout")
    assert timed_out.succeeded is False
    assert "Timed out" in (timed_out.error or "")
