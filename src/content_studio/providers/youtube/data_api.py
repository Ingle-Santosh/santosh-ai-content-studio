import httpx

from content_studio.providers.youtube.base import (
    BaseYouTubeProvider,
    YouTubeProviderError,
    YouTubeVideoMetadata,
    extract_youtube_video_id,
    parse_iso8601_duration,
)


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


class YouTubeDataAPIProvider(BaseYouTubeProvider):
    """Official YouTube Data API v3 provider for public video search and metadata."""

    provider_name = "youtube_data_api"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://www.googleapis.com/youtube/v3",
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        cleaned = api_key.strip()
        if not cleaned:
            raise YouTubeProviderError("YOUTUBE_API_KEY is required for YouTubeDataAPIProvider.")
        self._api_key = cleaned
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    async def _fetch_video_details(self, video_ids: list[str]) -> list[YouTubeVideoMetadata]:
        if not video_ids:
            return []
        try:
            async with self._build_client() as client:
                resp = await client.get(
                    "/videos",
                    params={
                        "part": "snippet,contentDetails,statistics",
                        "id": ",".join(video_ids),
                        "key": self._api_key,
                    },
                )
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise YouTubeProviderError(f"YouTube videos.list failed: {exc}") from exc

        results: list[YouTubeVideoMetadata] = []
        for item in payload.get("items", []):
            vid = str(item.get("id") or "")
            if not vid:
                continue
            snippet = item.get("snippet") or {}
            details = item.get("contentDetails") or {}
            stats = item.get("statistics") or {}
            results.append(
                YouTubeVideoMetadata(
                    youtube_video_id=vid,
                    url=f"https://www.youtube.com/watch?v={vid}",
                    title=str(snippet.get("title") or ""),
                    channel_name=str(snippet.get("channelTitle") or ""),
                    published_at=snippet.get("publishedAt"),
                    duration_seconds=parse_iso8601_duration(details.get("duration")),
                    view_count=_safe_int(stats.get("viewCount")),
                    like_count=_safe_int(stats.get("likeCount")),
                    comment_count=_safe_int(stats.get("commentCount")),
                    description=snippet.get("description"),
                    provider=self.provider_name,
                )
            )
        return results

    async def search_videos(
        self, query: str, *, max_results: int = 5
    ) -> list[YouTubeVideoMetadata]:
        cleaned = query.strip()
        if not cleaned:
            return []
        try:
            async with self._build_client() as client:
                resp = await client.get(
                    "/search",
                    params={
                        "part": "snippet",
                        "q": cleaned,
                        "type": "video",
                        "maxResults": max_results,
                        "key": self._api_key,
                    },
                )
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise YouTubeProviderError(f"YouTube search.list failed: {exc}") from exc

        video_ids: list[str] = []
        for item in payload.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            if vid and vid not in video_ids:
                video_ids.append(str(vid))
        return await self._fetch_video_details(video_ids[:max_results])

    async def fetch_video_by_url(self, url: str) -> YouTubeVideoMetadata | None:
        vid = extract_youtube_video_id(url)
        if not vid:
            return None
        items = await self._fetch_video_details([vid])
        return items[0] if items else None
