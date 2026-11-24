import asyncio
import html
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
import trafilatura
from pydantic import BaseModel

from content_studio.utils.hashing import sha256_text

_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "ref",
        "ref_src",
    }
)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def normalize_url(url: str) -> str:
    """Canonicalize URL for deterministic deduplication across tracking params/fragments."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Unsupported or invalid URL: {url!r}")

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    filtered_qs = sorted(
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS
    )
    query = urlencode(filtered_qs)
    return urlunparse((scheme, netloc, path, "", query, ""))


def compute_url_hash(normalized_url: str) -> str:
    return sha256_text(normalized_url)


def extract_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown"


class ExtractedPage(BaseModel):
    url: str
    final_url: str
    http_status: int | None = None
    title: str | None = None
    author: str | None = None
    published_date: str | None = None
    language: str | None = None
    text: str = ""
    word_count: int = 0
    checksum_sha256: str | None = None
    extraction_method: str = "trafilatura"
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.word_count > 0


def _fallback_html_text(raw_html: str) -> tuple[str | None, str]:
    title_match = _TITLE_RE.search(raw_html)
    title = " ".join(html.unescape(title_match.group(1)).split()) if title_match else None
    stripped = _SCRIPT_STYLE_RE.sub(" ", raw_html)
    stripped = _TAG_RE.sub(" ", stripped)
    text = " ".join(html.unescape(stripped).split())
    return title, text


def _extract_from_html_sync(
    raw_html: str, url: str
) -> tuple[str | None, str | None, str | None, str | None, str, str]:
    extracted = trafilatura.extract(
        raw_html,
        url=url,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )
    meta = trafilatura.extract_metadata(raw_html, default_url=url)
    title = meta.title if meta and meta.title else None
    author = meta.author if meta and meta.author else None
    published_date = meta.date if meta and meta.date else None
    language = meta.language if meta and meta.language else None

    if extracted and extracted.strip():
        return title, author, published_date, language, extracted.strip(), "trafilatura"

    fallback_title, fallback_text = _fallback_html_text(raw_html)
    return (
        title or fallback_title,
        author,
        published_date,
        language,
        fallback_text,
        "html_fallback",
    )


class WebExtractor:
    """Async deterministic webpage fetcher and Trafilatura content extractor."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_bytes: int = 2_000_000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._transport = transport

    async def fetch_and_extract(self, url: str) -> ExtractedPage:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SantoshAnalyticsContentStudio/0.4"
            ),
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            return ExtractedPage(
                url=url,
                final_url=url,
                error=f"Timed out fetching URL after {self._timeout_seconds}s.",
            )
        except httpx.HTTPError as exc:
            return ExtractedPage(url=url, final_url=url, error=f"HTTP fetch error: {exc}")

        final_url = str(response.url)
        if response.status_code >= 400:
            return ExtractedPage(
                url=url,
                final_url=final_url,
                http_status=response.status_code,
                error=f"Remote server returned HTTP {response.status_code}.",
            )

        content_type = response.headers.get("content-type", "").lower()
        if (
            content_type
            and "html" not in content_type
            and "text/" not in content_type
            and "xml" not in content_type
        ):
            return ExtractedPage(
                url=url,
                final_url=final_url,
                http_status=response.status_code,
                error=f"Unsupported content-type for text extraction: {content_type}",
            )

        raw_bytes = response.content[: self._max_bytes]
        raw_text = raw_bytes.decode(response.encoding or "utf-8", errors="replace")

        if "text/plain" in content_type:
            cleaned = raw_text.strip()
            if not cleaned:
                return ExtractedPage(
                    url=url,
                    final_url=final_url,
                    http_status=response.status_code,
                    extraction_method="plain_text",
                    error="Empty text response.",
                )
            return ExtractedPage(
                url=url,
                final_url=final_url,
                http_status=response.status_code,
                text=cleaned,
                word_count=len(cleaned.split()),
                checksum_sha256=sha256_text(cleaned),
                extraction_method="plain_text",
            )

        title, author, published_date, language, text, method = await asyncio.to_thread(
            _extract_from_html_sync, raw_text, final_url
        )
        if not text:
            return ExtractedPage(
                url=url,
                final_url=final_url,
                http_status=response.status_code,
                title=title,
                extraction_method=method,
                error="No extractable main text found in page.",
            )

        return ExtractedPage(
            url=url,
            final_url=final_url,
            http_status=response.status_code,
            title=title,
            author=author,
            published_date=published_date,
            language=language,
            text=text,
            word_count=len(text.split()),
            checksum_sha256=sha256_text(text),
            extraction_method=method,
        )
