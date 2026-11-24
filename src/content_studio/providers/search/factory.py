from content_studio.config.settings import Settings
from content_studio.providers.search.base import BaseSearchProvider
from content_studio.providers.search.duckduckgo import DuckDuckGoSearchProvider
from content_studio.providers.search.tavily import TavilySearchProvider


def build_search_provider(app_settings: Settings) -> BaseSearchProvider:
    provider_name = app_settings.SEARCH_PROVIDER.strip().lower()
    if provider_name == "tavily" and (app_settings.SEARCH_API_KEY or "").strip():
        return TavilySearchProvider(
            api_key=app_settings.SEARCH_API_KEY or "",
            timeout_seconds=app_settings.RESEARCH_FETCH_TIMEOUT_SECONDS,
        )
    return DuckDuckGoSearchProvider(
        timeout_seconds=app_settings.RESEARCH_FETCH_TIMEOUT_SECONDS,
    )
