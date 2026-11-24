import html
import textwrap

from content_studio.providers.image.base import BaseImageProvider, GeneratedImage


class LocalSVGImageProvider(BaseImageProvider):
    """Zero-cost local-first SVG concept visual provider for slide graphics & illustrations."""

    provider_name = "local_svg_concept"

    async def generate_image(
        self,
        *,
        title: str,
        prompt: str,
        width: int = 1280,
        height: int = 720,
    ) -> GeneratedImage:
        wrapped_title = textwrap.wrap(title.strip(), width=34)[:3]
        wrapped_desc = textwrap.wrap(prompt.strip(), width=64)[:5]

        title_lines = "\n".join(
            f'  <text x="96" y="{210 + i * 56}" fill="#f8fafc" font-family="sans-serif" '
            f'font-size="44" font-weight="700">{html.escape(line)}</text>'
            for i, line in enumerate(wrapped_title)
        )
        desc_start_y = 240 + len(wrapped_title) * 56
        desc_lines = "\n".join(
            f'  <text x="96" y="{desc_start_y + i * 36}" fill="#cbd5e1" '
            f'font-family="sans-serif" font-size="22">{html.escape(line)}</text>'
            for i, line in enumerate(wrapped_desc)
        )

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}">\n'
            "  <defs>\n"
            '    <linearGradient id="bgGrad" x1="0" y1="0" x2="1" y2="1">\n'
            '      <stop offset="0%" stop-color="#0f172a"/>\n'
            '      <stop offset="100%" stop-color="#1e293b"/>\n'
            "    </linearGradient>\n"
            "  </defs>\n"
            f'  <rect width="{width}" height="{height}" fill="url(#bgGrad)"/>\n'
            '  <circle cx="1120" cy="140" r="220" fill="#38bdf8" opacity="0.08"/>\n'
            '  <circle cx="1060" cy="580" r="180" fill="#818cf8" opacity="0.10"/>\n'
            '  <rect x="64" y="64" width="1152" height="592" rx="24" '
            'fill="#0b1220" fill-opacity="0.72" stroke="#334155" stroke-width="2"/>\n'
            '  <text x="96" y="132" fill="#38bdf8" font-family="sans-serif" '
            'font-size="16" font-weight="700" letter-spacing="3">'
            "SANTOSH ANALYTICS · CONCEPT VISUAL</text>\n"
            f"{title_lines}\n"
            f"{desc_lines}\n"
            "</svg>\n"
        )
        return GeneratedImage(
            content=svg.encode("utf-8"),
            extension=".svg",
            mime_type="image/svg+xml",
            provider=self.provider_name,
            prompt_used=prompt,
        )
