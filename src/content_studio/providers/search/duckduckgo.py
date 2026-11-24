import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from content_studio.providers.search.base import (
    BaseSearchProvider,
    SearchProviderError,
    SearchResult,
)

_RESULT_LINK_RE = re.compile(
    r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|'
    r'<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html_text(raw: str) -> str:
    text = _TAG_RE.sub("", raw)
    return " ".join(html.unescape(text).split())


def _decode_ddg_url(href: str) -> str:
    unescaped = html.unescape(href.strip())
    if unescaped.startswith("//"):
        unescaped = f"https:{unescaped}"
    parsed = urlparse(unescaped)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        target = qs.get("uddg", [None])[0]
        if target:
            return unquote(target)
    return unescaped


class DuckDuckGoSearchProvider(BaseSearchProvider):
    """Zero-API-key web search provider using DuckDuckGo's HTML endpoint."""

    provider_name = "duckduckgo"

    def __init__(
        self,
        *,
        base_url: str = "https://html.duckduckgo.com",
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        cleaned = query.strip()
        if not cleaned:
            return []

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SantoshAnalyticsContentStudio/0.4"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
                follow_redirects=True,
            ) as client:
                response = await client.post("/html/", data={"q": cleaned}, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchProviderError(f"DuckDuckGo search failed for {cleaned!r}: {exc}") from exc

        return self.parse_html(response.text, max_results=max_results)

    def parse_html(self, html_body: str, *, max_results: int = 5) -> list[SearchResult]:
        links = _RESULT_LINK_RE.findall(html_body)
        snippets = [_clean_html_text(m[0] or m[1]) for m in _SNIPPET_RE.findall(html_body)]

        results: list[SearchResult] = []
        for idx, (raw_href, raw_title) in enumerate(links):
            url = _decode_ddg_url(raw_href)
            if not url.startswith(("http://", "https://")):
                continue
            title = _clean_html_text(raw_title)
            snippet = snippets[idx] if idx < len(snippets) else ""
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    provider=self.provider_name,
                )
            )
            if len(results) >= max_results:
                break
        return results
