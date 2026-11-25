import asyncio
import html
import re
import shutil
import tempfile
import textwrap
from collections import deque
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
    r"(?:-->|---|-\.->|==>|->>)\s*(?:\|([^|]*)\|\s*)?"
    r"([A-Za-z0-9_]+)(?:\s*[\[\(\{][\"']?([^\]\)\}\"]+)[\"']?[\]\)\}])?"
)
_NODE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[\[\(\{][\"']?([^\]\)\}\"]+)[\"']?[\]\)\}]")

_LAYER_PALETTE: tuple[tuple[str, str], ...] = (
    ("#38bdf8", "#0ea5e9"),  # Sky (entry / input)
    ("#818cf8", "#6366f1"),  # Indigo (core processing)
    ("#a78bfa", "#8b5cf6"),  # Violet (policy / logic)
    ("#34d399", "#10b981"),  # Emerald (output / data)
    ("#fbbf24", "#f59e0b"),  # Amber (highlight / audit)
)


def _has_balanced_brackets(text: str) -> bool:
    pairs = {"[": "]", "(": ")", "{": "}"}
    closers = set(pairs.values())
    stack: list[str] = []
    for ch in text:
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in closers:
            if not stack or stack[-1] != ch:
                return False
            stack.pop()
    return len(stack) == 0


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

    for idx, line in enumerate(lines[1:], start=2):
        if line.startswith("%%"):
            continue
        if not _has_balanced_brackets(line):
            issues.append(f"Line {idx} has unbalanced or truncated brackets: {line!r}.")
            break

    if first.startswith(("flowchart", "graph")):
        nodes, edges = _extract_nodes_and_edges(mermaid_code)
        if not nodes or (len(nodes) < 2 and not edges):
            issues.append(
                "Flowchart/graph diagram must define at least 2 connected nodes (e.g., A --> B)."
            )

    return issues


def _extract_nodes_and_edges(
    mermaid_code: str,
) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    nodes: dict[str, str] = {}
    edges: list[tuple[str, str, str]] = []

    for line in mermaid_code.splitlines()[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(("%%", "subgraph", "end", "style", "classDef")):
            continue
        edge_match = _EDGE_RE.match(stripped)
        if edge_match:
            src_id, src_label, edge_label, dst_id, dst_label = edge_match.groups()
            if src_id not in nodes or src_label:
                nodes[src_id] = (src_label or nodes.get(src_id) or src_id).strip()
            if dst_id not in nodes or dst_label:
                nodes[dst_id] = (dst_label or nodes.get(dst_id) or dst_id).strip()
            edges.append((src_id, dst_id, (edge_label or "").strip()))
            continue

        node_match = _NODE_RE.match(stripped)
        if node_match:
            nid, nlabel = node_match.groups()
            nodes[nid] = nlabel.strip()

    return nodes, edges


def _assign_layers(
    node_ids: list[str],
    edges: list[tuple[str, str, str]],
) -> list[list[str]]:
    """Assign topological layers (ranks) via BFS from root nodes for clean DAG layouts."""
    indegree: dict[str, int] = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for src, dst, _ in edges:
        if src in adj and dst in indegree and src != dst:
            adj[src].append(dst)
            indegree[dst] += 1

    layer_of: dict[str, int] = {}
    queue: deque[str] = deque(nid for nid in node_ids if indegree[nid] == 0)
    if not queue:
        queue.append(node_ids[0])

    for root in queue:
        layer_of[root] = 0

    while queue:
        curr = queue.popleft()
        curr_layer = layer_of[curr]
        for nxt in adj[curr]:
            proposed = curr_layer + 1
            if nxt not in layer_of:
                layer_of[nxt] = proposed
                queue.append(nxt)
            elif proposed > layer_of[nxt] and proposed < len(node_ids):
                layer_of[nxt] = proposed

    # Any disconnected component nodes get placed sequentially
    max_layer = max(layer_of.values(), default=0)
    for nid in node_ids:
        if nid not in layer_of:
            layer_of[nid] = max_layer

    grouped: dict[int, list[str]] = {}
    for nid in node_ids:
        grouped.setdefault(layer_of[nid], []).append(nid)
    return [grouped[idx] for idx in sorted(grouped.keys())]


def render_fallback_svg(mermaid_code: str, *, title: str = "Architecture Diagram") -> str:
    """Broadcast-quality pure-Python layered DAG SVG renderer (works without Node/mmdc)."""
    first_line = next(
        (ln.strip() for ln in mermaid_code.splitlines() if ln.strip()),
        "flowchart TD",
    )
    is_horizontal = bool(re.search(r"\b(LR|RL)\b", first_line))
    nodes, edges = _extract_nodes_and_edges(mermaid_code)
    node_ids = list(nodes.keys())

    if not node_ids:
        lines = [line for line in mermaid_code.strip().splitlines() if line.strip()][:14]
        height = max(320, 150 + len(lines) * 28)
        text_rows = "\n".join(
            f'  <text x="64" y="{134 + i * 28}" fill="#e2e8f0" font-family="ui-monospace, '
            f'Consolas, monospace" font-size="14">{html.escape(line[:92])}</text>'
            for i, line in enumerate(lines)
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 {height}" '
            f'width="1120" height="{height}">\n'
            "  <defs>\n"
            '    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">\n'
            '      <stop offset="0%" stop-color="#0b1120"/>\n'
            '      <stop offset="100%" stop-color="#111c34"/>\n'
            "    </linearGradient>\n"
            "  </defs>\n"
            f'  <rect width="1120" height="{height}" rx="20" fill="url(#bg)"/>\n'
            '  <text x="52" y="46" fill="#38bdf8" font-family="Segoe UI, system-ui, sans-serif" '
            'font-size="12" font-weight="700" letter-spacing="2.5">'
            "SANTOSH ANALYTICS · TECHNICAL DIAGRAM</text>\n"
            f'  <text x="52" y="78" fill="#f8fafc" font-family="Segoe UI, system-ui, sans-serif" '
            f'font-size="24" font-weight="700">{html.escape(title[:76])}</text>\n'
            f'  <rect x="44" y="100" width="1032" height="{height - 128}" rx="12" '
            'fill="#0f172a" stroke="#334155" stroke-width="1.5"/>\n'
            f"{text_rows}\n"
            "</svg>\n"
        )

    layers = _assign_layers(node_ids, edges)
    box_w, box_h = 250, 78
    gap_x, gap_y = 76, 86
    header_h = 128
    pad_x, pad_y = 72, 64

    max_per_layer = max(len(layer) for layer in layers)
    num_layers = len(layers)

    if is_horizontal:
        content_w = num_layers * box_w + max(0, num_layers - 1) * gap_x
        content_h = max_per_layer * box_h + max(0, max_per_layer - 1) * gap_y
    else:
        content_w = max_per_layer * box_w + max(0, max_per_layer - 1) * gap_x
        content_h = num_layers * box_h + max(0, num_layers - 1) * gap_y

    svg_w = max(1080, content_w + pad_x * 2)
    svg_h = max(460, header_h + content_h + pad_y)

    positions: dict[str, tuple[int, int]] = {}
    node_layer_idx: dict[str, int] = {}

    for l_idx, layer in enumerate(layers):
        count = len(layer)
        if is_horizontal:
            start_x = (svg_w - content_w) // 2
            x = start_x + l_idx * (box_w + gap_x)
            col_h = count * box_h + max(0, count - 1) * gap_y
            start_y = header_h + (content_h - col_h) // 2
            for pos_idx, nid in enumerate(layer):
                positions[nid] = (x, start_y + pos_idx * (box_h + gap_y))
                node_layer_idx[nid] = l_idx
        else:
            row_w = count * box_w + max(0, count - 1) * gap_x
            start_x = (svg_w - row_w) // 2
            y = header_h + l_idx * (box_h + gap_y)
            for pos_idx, nid in enumerate(layer):
                positions[nid] = (start_x + pos_idx * (box_w + gap_x), y)
                node_layer_idx[nid] = l_idx

    wrapped_title = textwrap.wrap(title.strip(), width=64)[:2]
    title_svg = "\n".join(
        f'  <text x="56" y="{78 + i * 30}" fill="#f8fafc" '
        'font-family="Segoe UI, system-ui, sans-serif" font-size="24" font-weight="700">'
        f"{html.escape(line)}</text>"
        for i, line in enumerate(wrapped_title)
    )

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" '
        f'width="{svg_w}" height="{svg_h}">',
        "  <defs>",
        '    <linearGradient id="bgGrad" x1="0" y1="0" x2="1" y2="1">',
        '      <stop offset="0%" stop-color="#090f1d"/>',
        '      <stop offset="100%" stop-color="#131f38"/>',
        "    </linearGradient>",
        '    <pattern id="dotGrid" width="28" height="28" patternUnits="userSpaceOnUse">',
        '      <circle cx="2" cy="2" r="1.2" fill="#334155" opacity="0.45"/>',
        "    </pattern>",
        '    <filter id="cardShadow" x="-10%" y="-10%" width="120%" height="130%">',
        '      <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#000000" '
        'flood-opacity="0.42"/>',
        "    </filter>",
        '    <marker id="arrow" viewBox="0 0 12 12" refX="10" refY="6" '
        'markerWidth="8" markerHeight="8" orient="auto">',
        '      <path d="M 1 1 L 11 6 L 1 11 z" fill="#38bdf8"/>',
        "    </marker>",
        "  </defs>",
        f'  <rect width="{svg_w}" height="{svg_h}" rx="20" fill="url(#bgGrad)"/>',
        f'  <rect width="{svg_w}" height="{svg_h}" rx="20" fill="url(#dotGrid)"/>',
        f'  <circle cx="{svg_w - 110}" cy="70" r="170" fill="#38bdf8" opacity="0.07"/>',
        '  <rect x="56" y="34" width="6" height="16" rx="3" fill="#38bdf8"/>',
        '  <text x="72" y="47" fill="#38bdf8" font-family="Segoe UI, system-ui, sans-serif" '
        'font-size="12" font-weight="700" letter-spacing="2.4">'
        "SANTOSH ANALYTICS · ARCHITECTURE DIAGRAM</text>",
        title_svg,
    ]

    # Draw border-to-border curved edges FIRST so cards sit crisp on top,
    # while arrowheads terminate right at the target card border (100% visible!)
    edge_label_svg: list[str] = []
    for src_id, dst_id, edge_label in edges:
        if src_id not in positions or dst_id not in positions:
            continue
        sx, sy = positions[src_id]
        dx, dy = positions[dst_id]

        if is_horizontal:
            if dx >= sx:
                x1, y1 = sx + box_w, sy + box_h // 2
                x2, y2 = dx - 4, dy + box_h // 2
            else:
                x1, y1 = sx, sy + box_h // 2
                x2, y2 = dx + box_w + 4, dy + box_h // 2
            mid_x = (x1 + x2) // 2
            path_d = f"M {x1} {y1} C {mid_x} {y1}, {mid_x} {y2}, {x2} {y2}"
            label_x, label_y = mid_x, (y1 + y2) // 2 - 10
        else:
            if dy > sy:
                x1, y1 = sx + box_w // 2, sy + box_h
                x2, y2 = dx + box_w // 2, dy - 4
                mid_y = (y1 + y2) // 2
                path_d = f"M {x1} {y1} C {x1} {mid_y}, {x2} {mid_y}, {x2} {y2}"
                label_x, label_y = (x1 + x2) // 2, mid_y
            elif dy == sy:
                if dx >= sx:
                    x1, y1 = sx + box_w, sy + box_h // 2
                    x2, y2 = dx - 4, dy + box_h // 2
                else:
                    x1, y1 = sx, sy + box_h // 2
                    x2, y2 = dx + box_w + 4, dy + box_h // 2
                path_d = f"M {x1} {y1} L {x2} {y2}"
                label_x, label_y = (x1 + x2) // 2, y1 - 12
            else:
                x1, y1 = sx + box_w // 2, sy
                x2, y2 = dx + box_w // 2, dy + box_h + 4
                ctrl_x = max(x1, x2) + 80
                path_d = f"M {x1} {y1} C {ctrl_x} {y1}, {ctrl_x} {y2}, {x2} {y2}"
                label_x, label_y = ctrl_x - 20, (y1 + y2) // 2

        parts.append(
            f'  <path d="{path_d}" fill="none" stroke="#38bdf8" stroke-width="2.5" '
            'marker-end="url(#arrow)" opacity="0.92"/>'
        )
        if edge_label:
            short_lbl = edge_label[:24]
            pill_w = max(56, len(short_lbl) * 7 + 20)
            edge_label_svg.append(
                f'  <rect x="{label_x - pill_w // 2}" y="{label_y - 12}" width="{pill_w}" '
                'height="22" rx="11" fill="#0f172a" stroke="#38bdf8" stroke-width="1"/>\n'
                f'  <text x="{label_x}" y="{label_y + 3}" fill="#bae6fd" '
                'font-family="Segoe UI, system-ui, sans-serif" font-size="11" '
                f'font-weight="600" text-anchor="middle">{html.escape(short_lbl)}</text>'
            )

    # Render layered cards with top accent stripes and multi-line wrapped labels
    for nid in node_ids:
        x, y = positions[nid]
        accent, _deep = _LAYER_PALETTE[node_layer_idx.get(nid, 0) % len(_LAYER_PALETTE)]
        wrapped_lbl = textwrap.wrap(nodes[nid], width=24)[:3] or [nid]
        line_h = 19
        text_start_y = y + (box_h - (len(wrapped_lbl) - 1) * line_h) // 2 + 6
        label_svg = "\n".join(
            f'  <text x="{x + box_w // 2}" y="{text_start_y + i * line_h}" fill="#f8fafc" '
            'font-family="Segoe UI, system-ui, sans-serif" font-size="14" font-weight="600" '
            f'text-anchor="middle">{html.escape(line)}</text>'
            for i, line in enumerate(wrapped_lbl)
        )
        parts.extend(
            [
                f'  <rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="12" '
                f'fill="#162238" stroke="{accent}" stroke-width="1.75" filter="url(#cardShadow)"/>',
                f'  <rect x="{x}" y="{y}" width="{box_w}" height="6" rx="3" fill="{accent}"/>',
                label_svg,
            ]
        )

    parts.extend(edge_label_svg)
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
