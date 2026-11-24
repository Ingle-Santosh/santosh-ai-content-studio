import httpx

from content_studio.providers.search import BaseSearchProvider, SearchProviderError
from content_studio.providers.youtube.base import (
    BaseYouTubeProvider,
    YouTubeVideoMetadata,
    extract_youtube_video_id,
)


class PublicYouTubeSearchProvider(BaseYouTubeProvider):
    """Zero-API-key competitor discovery via web search + YouTube public oEmbed.

    Leaves unavailable performance metrics (views, likes, comments, duration) as None
    rather than fabricating values.
    """

    provider_name = "public_search"

    def __init__(
        self,
        *,
        search_provider: BaseSearchProvider,
        oembed_base_url: str = "https://www.youtube.com",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._search_provider = search_provider
        self._oembed_base_url = oembed_base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def _fetch_oembed(self, canonical_url: str) -> dict[str, str]:
        try:
            async with httpx.AsyncClient(
                base_url=self._oembed_base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                resp = await client.get(
                    "/oembed",
                    params={"url": canonical_url, "format": "json"},
                )
                if resp.status_code != 200:
                    return {}
                data = resp.json()
                return {
                    "title": str(data.get("title") or ""),
                    "author_name": str(data.get("author_name") or ""),
                }
        except (httpx.HTTPError, ValueError):
            return {}

    async def search_videos(
        self, query: str, *, max_results: int = 5
    ) -> list[YouTubeVideoMetadata]:
        cleaned = query.strip()
        if not cleaned:
            return []

        try:
            raw_results = await self._search_provider.search(
                f"site:youtube.com/watch {cleaned}",
                max_results=max_results * 2,
            )
        except SearchProviderError:
            return []

        videos: list[YouTubeVideoMetadata] = []
        seen_ids: set[str] = set()
        for item in raw_results:
            vid = extract_youtube_video_id(item.url)
            if not vid or vid in seen_ids:
                continue
            seen_ids.add(vid)
            canonical_url = f"https://www.youtube.com/watch?v={vid}"
            oembed = await self._fetch_oembed(canonical_url)
            videos.append(
                YouTubeVideoMetadata(
                    youtube_video_id=vid,
                    url=canonical_url,
                    title=oembed.get("title") or item.title or canonical_url,
                    channel_name=oembed.get("author_name") or "",
                    published_at=item.published_date,
                    description=item.snippet or None,
                    provider=self.provider_name,
                )
            )
            if len(videos) >= max_results:
                break
        return videos

    async def fetch_video_by_url(self, url: str) -> YouTubeVideoMetadata | None:
        vid = extract_youtube_video_id(url)
        if not vid:
            return None
        canonical_url = f"https://www.youtube.com/watch?v={vid}"
        oembed = await self._fetch_oembed(canonical_url)
        return YouTubeVideoMetadata(
            youtube_video_id=vid,
            url=canonical_url,
            title=oembed.get("title") or canonical_url,
            channel_name=oembed.get("author_name") or "",
            provider="manual",
        )
