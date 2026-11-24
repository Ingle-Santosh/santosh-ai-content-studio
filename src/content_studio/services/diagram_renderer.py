import asyncio
import html
import re
import shutil
import tempfile
from pathlib import Path

_VALID_HEADERS: tuple[str, ...] = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "stateDiagram",
    "erDiagram",
    "classDiagram",
)
_EDGE_RE = re.compile(
    r"^\s*([A-Za-z0-9_]+)(?:\s*[\[\(\{][\"']?([^\]\)\}\"]+)[\"']?[\]\)\}])?\s*"
    r"(?:-->|---|-\.->|==>|->>)\s*(?:\|[^|]*\|\s*)?"
    r"([A-Za-z0-9_]+)(?:\s*[\[\(\{][\"']?([^\]\)\}\"]+)[\"']?[\]\)\}])?"
)
_NODE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[\[\(\{][\"']?([^\]\)\}\"]+)[\"']?[\]\)\}]")


def validate_mermaid_syntax(mermaid_code: str) -> list[str]:
    """Deterministic syntax check for Mermaid diagram source."""
    issues: list[str] = []
    lines = [line.strip() for line in mermaid_code.strip().splitlines() if line.strip()]
    if not lines:
        return ["Mermaid source is empty."]

    first = lines[0]
    if not any(first.startswith(hdr) for hdr in _VALID_HEADERS):
        issues.append(
            f"Unsupported or missing Mermaid diagram header: {first!r}. "
            f"Expected one of {', '.join(_VALID_HEADERS)}."
        )

    if len(lines) < 2:
        issues.append("Mermaid diagram must contain at least one node or relationship.")

    if "<script" in mermaid_code.lower():
        issues.append("Mermaid source must not contain <script> tags.")

    return issues


def _extract_nodes_and_edges(mermaid_code: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    nodes: dict[str, str] = {}
    edges: list[tuple[str, str]] = []

    for line in mermaid_code.splitlines()[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        edge_match = _EDGE_RE.match(stripped)
        if edge_match:
            src_id, src_label, dst_id, dst_label = edge_match.groups()
            if src_id not in nodes or src_label:
                nodes[src_id] = (src_label or nodes.get(src_id) or src_id).strip()
            if dst_id not in nodes or dst_label:
                nodes[dst_id] = (dst_label or nodes.get(dst_id) or dst_id).strip()
            edges.append((src_id, dst_id))
            continue

        node_match = _NODE_RE.match(stripped)
        if node_match:
            nid, nlabel = node_match.groups()
            nodes[nid] = nlabel.strip()

    return nodes, edges


def render_fallback_svg(mermaid_code: str, *, title: str = "Architecture Diagram") -> str:
    """Pure-Python deterministic SVG renderer for local-first operation without Node/mmdc."""
    nodes, edges = _extract_nodes_and_edges(mermaid_code)
    node_ids = list(nodes.keys())

    if not node_ids:
        # Render clean code-card SVG for diagram types without simple node/edge pairs
        lines = [line for line in mermaid_code.strip().splitlines() if line.strip()][:12]
        height = max(260, 120 + len(lines) * 26)
        text_rows = "\n".join(
            f'  <text x="52" y="{110 + i * 26}" fill="#e2e8f0" font-family="monospace" '
            f'font-size="14">{html.escape(line[:86])}</text>'
            for i, line in enumerate(lines)
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 {height}" '
            f'width="960" height="{height}">\n'
            f'  <rect width="960" height="{height}" rx="16" fill="#0f172a"/>\n'
            f'  <text x="48" y="56" fill="#38bdf8" font-family="sans-serif" '
            f'font-size="22" font-weight="700">{html.escape(title)}</text>\n'
            f'  <rect x="36" y="76" width="888" height="{height - 104}" rx="10" '
            f'fill="#1e293b" stroke="#334155"/>\n'
            f"{text_rows}\n"
            "</svg>\n"
        )

    cols = min(3, max(1, len(node_ids)))
    box_w, box_h = 240, 64
    gap_x, gap_y = 60, 72
    margin_x, margin_y = 60, 100
    rows = (len(node_ids) + cols - 1) // cols

    svg_w = max(840, margin_x * 2 + cols * box_w + (cols - 1) * gap_x)
    svg_h = max(320, margin_y + rows * box_h + (rows - 1) * gap_y + 70)

    positions: dict[str, tuple[int, int]] = {}
    for idx, nid in enumerate(node_ids):
        r, c = divmod(idx, cols)
        x = margin_x + c * (box_w + gap_x)
        y = margin_y + r * (box_h + gap_y)
        positions[nid] = (x, y)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" '
        f'width="{svg_w}" height="{svg_h}">',
        "  <defs>",
        '    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
        '      <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8"/>',
        "    </marker>",
        "  </defs>",
        f'  <rect width="{svg_w}" height="{svg_h}" rx="16" fill="#0f172a"/>',
        '  <text x="48" y="42" fill="#94a3b8" font-family="sans-serif" font-size="12" '
        'letter-spacing="2">SANTOSH ANALYTICS · DIAGRAM</text>',
        f'  <text x="48" y="72" fill="#f8fafc" font-family="sans-serif" font-size="22" '
        f'font-weight="700">{html.escape(title)}</text>',
    ]

    for src_id, dst_id in edges:
        if src_id not in positions or dst_id not in positions:
            continue
        sx, sy = positions[src_id]
        dx, dy = positions[dst_id]
        x1, y1 = sx + box_w // 2, sy + box_h // 2
        x2, y2 = dx + box_w // 2, dy + box_h // 2
        parts.append(
            f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            'stroke="#38bdf8" stroke-width="2.5" marker-end="url(#arrow)" opacity="0.85"/>'
        )

    for nid in node_ids:
        x, y = positions[nid]
        label = nodes[nid][:28]
        parts.extend(
            [
                f'  <rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="10" '
                'fill="#1e293b" stroke="#38bdf8" stroke-width="1.5"/>',
                f'  <text x="{x + box_w // 2}" y="{y + box_h // 2 + 5}" fill="#f8fafc" '
                'font-family="sans-serif" font-size="14" font-weight="600" '
                f'text-anchor="middle">{html.escape(label)}</text>',
            ]
        )

    parts.append("</svg>\n")
    return "\n".join(parts)


async def render_mermaid_to_svg(
    mermaid_code: str,
    *,
    title: str = "Architecture Diagram",
    timeout_seconds: float = 10.0,
) -> tuple[str, str]:
    """Render Mermaid to SVG via mmdc if installed, else deterministic local SVG renderer."""
    mmdc = shutil.which("mmdc")
    if mmdc:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            in_file = tmp_dir / "diagram.mmd"
            out_file = tmp_dir / "diagram.svg"
            in_file.write_text(mermaid_code, encoding="utf-8")
            try:
                proc = await asyncio.create_subprocess_exec(
                    mmdc,
                    "-i",
                    str(in_file),
                    "-o",
                    str(out_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
                if proc.returncode == 0 and out_file.is_file():
                    return out_file.read_text(encoding="utf-8"), "mmdc"
            except (OSError, TimeoutError):
                pass

    return render_fallback_svg(mermaid_code, title=title), "local_svg_renderer"
