from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    title: str = Field(default="")
    url: str = Field(min_length=1)
    snippet: str = Field(default="")
    provider: str = Field(default="unknown")
    published_date: str | None = None


class SearchProviderError(RuntimeError):
    """Raised when a web search provider fails or returns an invalid response."""


class BaseSearchProvider(ABC):
    """Provider-independent interface for web search discovery."""

    provider_name: str

    @abstractmethod
    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        """Execute a web search query and return normalized SearchResult items."""
