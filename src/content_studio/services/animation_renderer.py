import html
import json
import re
from pathlib import Path

from content_studio.contracts.assets import AnimationSpecLLMOutput

_FORBIDDEN_HTML_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("External <script src=...> is forbidden", re.compile(r"<script[^>]+src=", re.IGNORECASE)),
    ("eval() is forbidden in generated HTML", re.compile(r"\beval\s*\(", re.IGNORECASE)),
    ("innerHTML assignment is forbidden", re.compile(r"\.innerHTML\s*=", re.IGNORECASE)),
    ("document.write is forbidden", re.compile(r"document\.write\s*\(", re.IGNORECASE)),
    ("javascript: URI is forbidden", re.compile(r"javascript\s*:", re.IGNORECASE)),
    ("<iframe> elements are forbidden", re.compile(r"<iframe\b", re.IGNORECASE)),
    (
        "Inline event handler attributes are forbidden",
        re.compile(r"\son(?:error|load|click|mouseover)\s*=", re.IGNORECASE),
    ),
)


def render_animation_html(base_dir: Path, spec: AnimationSpecLLMOutput) -> str:
    """Render an AnimationSpec into a sanitized, self-contained HTML5/CSS/JS file."""
    template_path = base_dir / "templates" / "animations" / "step_walkthrough.html"
    template = template_path.read_text(encoding="utf-8")

    safe_title = html.escape(spec.title.strip())
    safe_subtitle = html.escape(spec.subtitle.strip())
    steps_payload = [
        {
            "label": step.label.strip(),
            "description": step.description.strip(),
            "highlight_text": step.highlight_text.strip() if step.highlight_text else None,
        }
        for step in spec.steps
    ]
    # Escape '<' inside embedded JSON so </script> breakout is impossible
    safe_steps_json = json.dumps(steps_payload, ensure_ascii=False).replace("<", "\\u003c")

    rendered = (
        template.replace("__TITLE__", safe_title)
        .replace("__SUBTITLE__", safe_subtitle)
        .replace("__STEPS_JSON__", safe_steps_json)
    )
    return rendered


def validate_sanitized_html(html_content: str) -> list[str]:
    """Verify generated HTML complies with local-first XSS & sandboxing rules."""
    issues: list[str] = []
    if not html_content.strip():
        return ["HTML animation content is empty."]
    if "<!doctype html>" not in html_content.lower():
        issues.append("Missing HTML5 <!DOCTYPE html> declaration.")
    for message, pattern in _FORBIDDEN_HTML_PATTERNS:
        if pattern.search(html_content):
            issues.append(message)
    return issues
