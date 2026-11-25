import html
import re
import textwrap

from content_studio.providers.image.base import BaseImageProvider, GeneratedImage


class LocalSVGImageProvider(BaseImageProvider):
    """Zero-cost local-first 16:9 slide visual provider for YouTube educational graphics."""

    provider_name = "local_svg_concept"

    async def generate_image(
        self,
        *,
        title: str,
        prompt: str,
        width: int = 1280,
        height: int = 720,
    ) -> GeneratedImage:
        wrapped_title = textwrap.wrap(title.strip(), width=34)[:2]

        # Extract up to 3 clean takeaway points from the prompt for structured visual cards
        raw_points = [
            seg.strip()
            for seg in re.split(r"(?<=[.!?])\s+|\n+|;\s*", prompt.strip())
            if len(seg.strip()) >= 8
        ]
        if not raw_points:
            raw_points = [prompt.strip() or title.strip()]
        points = raw_points[:3]

        title_lines = "\n".join(
            f'  <text x="108" y="{198 + i * 58}" fill="#f8fafc" '
            'font-family="Segoe UI, system-ui, sans-serif" font-size="44" font-weight="800">'
            f"{html.escape(line)}</text>"
            for i, line in enumerate(wrapped_title)
        )

        card_accents = ("#38bdf8", "#818cf8", "#34d399")
        cards_svg_parts: list[str] = []
        cards_top = 240 + len(wrapped_title) * 58
        card_gap = 22
        card_count = len(points)
        total_w = 1064
        card_w = (total_w - card_gap * (card_count - 1)) // card_count
        card_h = max(180, 620 - cards_top)

        for idx, pt in enumerate(points):
            cx = 108 + idx * (card_w + card_gap)
            accent = card_accents[idx % len(card_accents)]
            max_chars = max(20, (card_w - 48) // 11)
            wrapped_pt = textwrap.wrap(pt, width=max_chars)[:5]
            pt_lines = "\n".join(
                f'  <text x="{cx + 24}" y="{cards_top + 76 + j * 28}" fill="#e2e8f0" '
                'font-family="Segoe UI, system-ui, sans-serif" font-size="18">'
                f"{html.escape(ln)}</text>"
                for j, ln in enumerate(wrapped_pt)
            )
            cards_svg_parts.append(
                f'  <rect x="{cx}" y="{cards_top}" width="{card_w}" height="{card_h}" rx="16" '
                f'fill="#111c34" stroke="{accent}" stroke-opacity="0.65" stroke-width="1.5"/>\n'
                f'  <rect x="{cx}" y="{cards_top}" width="{card_w}" height="6" rx="3" '
                f'fill="{accent}"/>\n'
                f'  <text x="{cx + 24}" y="{cards_top + 40}" fill="{accent}" '
                'font-family="Segoe UI, system-ui, sans-serif" font-size="13" font-weight="700" '
                f'letter-spacing="1.8">KEY CONCEPT 0{idx + 1}</text>\n'
                f"{pt_lines}"
            )

        cards_svg = "\n".join(cards_svg_parts)

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}">\n'
            "  <defs>\n"
            '    <linearGradient id="bgGrad" x1="0" y1="0" x2="1" y2="1">\n'
            '      <stop offset="0%" stop-color="#070d19"/>\n'
            '      <stop offset="100%" stop-color="#13203b"/>\n'
            "    </linearGradient>\n"
            '    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">\n'
            '      <circle cx="2" cy="2" r="1.2" fill="#334155" opacity="0.45"/>\n'
            "    </pattern>\n"
            "  </defs>\n"
            f'  <rect width="{width}" height="{height}" fill="url(#bgGrad)"/>\n'
            f'  <rect width="{width}" height="{height}" fill="url(#grid)"/>\n'
            '  <circle cx="1140" cy="110" r="240" fill="#38bdf8" opacity="0.09"/>\n'
            '  <circle cx="1090" cy="610" r="200" fill="#818cf8" opacity="0.09"/>\n'
            '  <rect x="64" y="54" width="1152" height="612" rx="24" '
            'fill="#0b1324" fill-opacity="0.82" stroke="#1e293b" stroke-width="2"/>\n'
            '  <rect x="64" y="54" width="10" height="612" rx="5" fill="#38bdf8"/>\n'
            '  <text x="108" y="122" fill="#38bdf8" '
            'font-family="Segoe UI, system-ui, sans-serif" font-size="15" font-weight="700" '
            'letter-spacing="3">SANTOSH ANALYTICS · VISUAL CONCEPT SLIDE</text>\n'
            f"{title_lines}\n"
            f"{cards_svg}\n"
            '  <text x="108" y="646" fill="#64748b" '
            'font-family="Segoe UI, system-ui, sans-serif" font-size="13">'
            "Santosh Analytics AI Content Studio · 16:9 Production Slide</text>\n"
            "</svg>\n"
        )
        return GeneratedImage(
            content=svg.encode("utf-8"),
            extension=".svg",
            mime_type="image/svg+xml",
            provider=self.provider_name,
            prompt_used=prompt,
        )
