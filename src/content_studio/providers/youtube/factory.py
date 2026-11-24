from content_studio.config.settings import Settings
from content_studio.providers.search import BaseSearchProvider, build_search_provider
from content_studio.providers.youtube.base import BaseYouTubeProvider
from content_studio.providers.youtube.data_api import YouTubeDataAPIProvider
from content_studio.providers.youtube.public_provider import PublicYouTubeSearchProvider


def build_youtube_provider(
    app_settings: Settings,
    *,
    search_provider: BaseSearchProvider | None = None,
) -> BaseYouTubeProvider:
    if (app_settings.YOUTUBE_API_KEY or "").strip():
        return YouTubeDataAPIProvider(
            api_key=app_settings.YOUTUBE_API_KEY or "",
            timeout_seconds=app_settings.RESEARCH_FETCH_TIMEOUT_SECONDS,
        )
    return PublicYouTubeSearchProvider(
        search_provider=search_provider or build_search_provider(app_settings),
        timeout_seconds=app_settings.RESEARCH_FETCH_TIMEOUT_SECONDS,
    )
