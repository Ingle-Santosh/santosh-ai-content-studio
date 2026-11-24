import re
from abc import ABC, abstractmethod
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field

_ISO_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_youtube_video_id(url: str) -> str | None:
    """Extract canonical 11-character YouTube video ID from standard public URLs."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    candidate: str | None = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "youtube-nocookie.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2:
                candidate = parts[1]

    if candidate and _YT_ID_RE.fullmatch(candidate):
        return candidate
    return None


def parse_iso8601_duration(duration: str | None) -> int | None:
    """Parse YouTube ISO-8601 duration (e.g. 'PT15M33S') into total seconds."""
    if not duration:
        return None
    match = _ISO_DURATION_RE.match(duration.strip())
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


class YouTubeVideoMetadata(BaseModel):
    youtube_video_id: str = Field(min_length=5, max_length=32)
    url: str = Field(min_length=1)
    title: str = Field(default="")
    channel_name: str = Field(default="")
    published_at: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    view_count: int | None = Field(default=None, ge=0)
    like_count: int | None = Field(default=None, ge=0)
    comment_count: int | None = Field(default=None, ge=0)
    description: str | None = None
    provider: str = Field(default="public_search")


class YouTubeProviderError(RuntimeError):
    """Raised when public YouTube metadata discovery fails."""


class BaseYouTubeProvider(ABC):
    """Provider-independent interface for publicly accessible YouTube video metadata."""

    provider_name: str

    @abstractmethod
    async def search_videos(
        self, query: str, *, max_results: int = 5
    ) -> list[YouTubeVideoMetadata]:
        """Search public YouTube videos and return verified metadata (never fabricate stats)."""

    @abstractmethod
    async def fetch_video_by_url(self, url: str) -> YouTubeVideoMetadata | None:
        """Fetch public metadata for a specific YouTube video URL."""
