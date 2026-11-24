import html

from content_studio.contracts.assets import ScreenshotAnnotation

_MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_uploaded_screenshot(
    data: bytes,
    *,
    max_bytes: int = _MAX_SCREENSHOT_BYTES,
) -> tuple[str, str]:
    """Validate screenshot binary magic bytes and size; return (extension, mime_type)."""
    if not data:
        raise ValueError("Uploaded screenshot file is empty.")
    if len(data) > max_bytes:
        raise ValueError(f"Uploaded screenshot exceeds maximum size of {max_bytes} bytes.")

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"

    raise ValueError("Unsupported screenshot format. Only PNG, JPEG, and WEBP are allowed.")


def render_annotation_overlay_svg(
    annotations: list[ScreenshotAnnotation],
    *,
    width: int = 1280,
    height: int = 720,
) -> str:
    """Render non-destructive SVG callout boxes for screenshot highlights."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">'
    ]
    for ann in annotations:
        color = ann.color if ann.color.startswith("#") else "#ff5722"
        label_y = max(24, ann.y - 8)
        parts.extend(
            [
                f'  <rect x="{ann.x}" y="{ann.y}" width="{ann.width}" height="{ann.height}" '
                f'rx="6" fill="none" stroke="{html.escape(color)}" stroke-width="4"/>',
                f'  <text x="{ann.x}" y="{label_y}" fill="{html.escape(color)}" '
                'font-family="sans-serif" font-size="18" font-weight="700">'
                f"{html.escape(ann.label)}</text>",
            ]
        )
    parts.append("</svg>\n")
    return "\n".join(parts)
