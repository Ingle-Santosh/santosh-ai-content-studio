import pytest

from content_studio.config.settings import settings
from content_studio.contracts.assets import (
    AnimationSpecLLMOutput,
    AnimationStep,
    ScreenshotAnnotation,
)
from content_studio.services.animation_renderer import (
    render_animation_html,
    validate_sanitized_html,
)
from content_studio.services.code_sandbox import (
    check_python_ast_safety,
    run_python_isolated,
    run_sql_isolated,
)
from content_studio.services.diagram_renderer import (
    render_fallback_svg,
    validate_mermaid_syntax,
)
from content_studio.services.screenshot_utils import (
    render_annotation_overlay_svg,
    validate_uploaded_screenshot,
)


def test_mermaid_validation_and_fallback_svg_rendering() -> None:
    good = (
        'flowchart TD\n    A["User Query"] -->|Embed| B["Vector DB"]\n    B --> C["LLM Answer"]\n'
    )
    assert validate_mermaid_syntax(good) == []

    svg = render_fallback_svg(good, title="RAG Flow")
    assert svg.startswith("<svg ")
    assert "Vector DB" in svg
    assert "Embed" in svg
    assert "<path " in svg

    assert validate_mermaid_syntax("invalidHeader\nA --> B") != []
    assert validate_mermaid_syntax("flowchart TD\n  A[") != []
    assert validate_mermaid_syntax("") != []


def test_animation_renderer_sanitizes_xss_payloads() -> None:
    spec = AnimationSpecLLMOutput(
        title='RAG <script>alert("xss")</script> Pipeline',
        subtitle="Safe step-by-step walkthrough",
        steps=[
            AnimationStep(
                label="Chunking",
                description="Split docs into overlapping chunks </script><script>evil()</script>",
                highlight_text="chunk_size = 512",
            ),
            AnimationStep(
                label="Retrieval",
                description="Fetch top-k relevant vectors via cosine similarity.",
            ),
        ],
    )
    rendered = render_animation_html(settings.BASE_DIR, spec)
    assert validate_sanitized_html(rendered) == []
    assert "<script>alert(" not in rendered
    assert "</script><script>" not in rendered

    # Direct security validator catches forbidden constructs
    bad_html = '<!DOCTYPE html><html><script src="https://evil.test/x.js"></script></html>'
    issues = validate_sanitized_html(bad_html)
    assert any("External <script src=" in issue for issue in issues)


@pytest.mark.asyncio
async def test_isolated_code_sandbox_executes_safe_and_blocks_unsafe() -> None:
    safe_py = "nums = [1, 2, 3, 4]\nprint('sum =', sum(nums))\n"
    ok = await run_python_isolated(safe_py)
    assert ok.passed is True
    assert "sum = 10" in ok.stdout

    # Dangerous subprocess / os access is statically blocked before execution
    unsafe_py = "import os\nos.system('echo pwned')\n"
    blocked = await run_python_isolated(unsafe_py)
    assert blocked.passed is False
    assert any("Blocked import: 'os'" in r for r in blocked.blocked_reasons)
    assert check_python_ast_safety("eval('1+1')") != []

    # Infinite loop hits timeout cleanly
    timeout_res = await run_python_isolated("while True:\n    pass\n", timeout_seconds=0.4)
    assert timeout_res.passed is False
    assert any("Timeout" in r for r in timeout_res.blocked_reasons)

    # SQLite in-memory SQL validation
    sql_ok = await run_sql_isolated(
        "CREATE TABLE sales (id INT, amt INT);"
        "INSERT INTO sales VALUES (1, 100), (2, 250);"
        "SELECT id, amt, SUM(amt) OVER (ORDER BY id) AS running_total FROM sales;"
    )
    assert sql_ok.passed is True
    assert "running_total" in sql_ok.stdout
    assert "350" in sql_ok.stdout

    sql_blocked = await run_sql_isolated("ATTACH DATABASE '/tmp/x.db' AS x;")
    assert sql_blocked.passed is False


def test_screenshot_magic_bytes_validation_and_annotations() -> None:
    valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    ext, mime = validate_uploaded_screenshot(valid_png)
    assert ext == ".png"
    assert mime == "image/png"

    with pytest.raises(ValueError, match="Unsupported screenshot format"):
        validate_uploaded_screenshot(b"not a real image")

    overlay = render_annotation_overlay_svg(
        [ScreenshotAnnotation(x=100, y=120, width=300, height=80, label="Key Metric")]
    )
    assert "<svg " in overlay
    assert "Key Metric" in overlay
