from abc import ABC, abstractmethod

from content_studio.providers.llm.types import LLMRequest, LLMResponse, ProviderHealth


class BaseLLMProvider(ABC):
    """Provider-independent interface for local and cloud LLM backends."""

    provider_name: str
    is_cloud: bool = False

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Execute a chat completion request and return a normalized LLMResponse."""

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Return connectivity status and discoverable models for this provider."""
