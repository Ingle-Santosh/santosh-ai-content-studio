import httpx
import pytest

from content_studio.providers.search import BaseSearchProvider, SearchResult
from content_studio.providers.youtube import (
    PublicYouTubeSearchProvider,
    YouTubeDataAPIProvider,
    extract_youtube_video_id,
    parse_iso8601_duration,
)


class _StubYTSearch(BaseSearchProvider):
    provider_name = "stub"

    async def search(self, _query: str, *, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="Fallback Title",
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                snippet="Practical walkthrough of RAG pipelines.",
                provider="stub",
            ),
            SearchResult(
                title="Non-YouTube link",
                url="https://example.com/blog",
                snippet="Should be ignored",
                provider="stub",
            ),
        ][:max_results]


def test_youtube_id_and_iso8601_duration_helpers() -> None:
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ?t=30") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://example.com/watch?v=dQw4w9WgXcQ") is None

    assert parse_iso8601_duration("PT15M33S") == 933
    assert parse_iso8601_duration("PT1H2M5S") == 3725
    assert parse_iso8601_duration("invalid") is None


@pytest.mark.asyncio
async def test_youtube_data_api_provider() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={"items": [{"id": {"videoId": "abcDEF12345"}}]},
            )
        if request.url.path.endswith("/videos"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "abcDEF12345",
                            "snippet": {
                                "title": "RAG vs CAG in Production",
                                "channelTitle": "Tech Academy",
                                "publishedAt": "2026-01-15T10:00:00Z",
                                "description": "Full trade-off comparison.",
                            },
                            "contentDetails": {"duration": "PT18M10S"},
                            "statistics": {
                                "viewCount": "42500",
                                "likeCount": "1900",
                                "commentCount": "120",
                            },
                        }
                    ]
                },
            )
        return httpx.Response(404)

    provider = YouTubeDataAPIProvider(
        api_key="yt-test-key",
        transport=httpx.MockTransport(handler),
    )
    videos = await provider.search_videos("RAG vs CAG", max_results=3)
    assert len(videos) == 1
    assert videos[0].youtube_video_id == "abcDEF12345"
    assert videos[0].channel_name == "Tech Academy"
    assert videos[0].duration_seconds == 1090
    assert videos[0].view_count == 42500
    assert videos[0].provider == "youtube_data_api"


@pytest.mark.asyncio
async def test_public_youtube_provider_never_fabricates_metrics() -> None:
    def oembed_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oembed":
            return httpx.Response(
                200,
                json={
                    "title": "Verified oEmbed Title",
                    "author_name": "Data Engineering Channel",
                },
            )
        return httpx.Response(404)

    provider = PublicYouTubeSearchProvider(
        search_provider=_StubYTSearch(),
        transport=httpx.MockTransport(oembed_handler),
    )
    videos = await provider.search_videos("RAG pipelines", max_results=5)
    assert len(videos) == 1
    assert videos[0].title == "Verified oEmbed Title"
    assert videos[0].channel_name == "Data Engineering Channel"
    # Unavailable metrics remain None — never invented
    assert videos[0].view_count is None
    assert videos[0].like_count is None
    assert videos[0].duration_seconds is None
