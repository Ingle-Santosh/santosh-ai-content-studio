from abc import ABC, abstractmethod

from pydantic import BaseModel


class GeneratedImage(BaseModel):
    content: bytes
    extension: str
    mime_type: str
    provider: str
    prompt_used: str


class BaseImageProvider(ABC):
    """Provider-independent interface for concept visuals and illustrations."""

    provider_name: str

    @abstractmethod
    async def generate_image(
        self,
        *,
        title: str,
        prompt: str,
        width: int = 1280,
        height: int = 720,
    ) -> GeneratedImage:
        """Generate an educational concept visual and return raw bytes + metadata."""
