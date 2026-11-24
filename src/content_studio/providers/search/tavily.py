import httpx

from content_studio.providers.search.base import (
    BaseSearchProvider,
    SearchProviderError,
    SearchResult,
)


class TavilySearchProvider(BaseSearchProvider):
    """Configurable cloud search provider backed by the Tavily Search API."""

    provider_name = "tavily"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.tavily.com",
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        cleaned_key = api_key.strip()
        if not cleaned_key:
            raise SearchProviderError("Tavily API key is required.")
        self._api_key = cleaned_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        cleaned = query.strip()
        if not cleaned:
            return []

        payload = {
            "query": cleaned,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/search",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchProviderError(f"Tavily search failed for {cleaned!r}: {exc}") from exc

        results: list[SearchResult] = []
        for item in data.get("results", []):
            if not isinstance(item, dict) or not item.get("url"):
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title") or ""),
                    url=str(item["url"]),
                    snippet=str(item.get("content") or ""),
                    provider=self.provider_name,
                    published_date=item.get("published_date"),
                )
            )
            if len(results) >= max_results:
                break
        return results
