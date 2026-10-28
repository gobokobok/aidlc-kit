"""Trace graph layout: discovery → requirements → criteria → prompt → evals → tasks.

Returns plain coordinates, so the template only draws what it is given.
"""

from typing import Any

from aidlc.artifacts import Artifact
from aidlc.decompose import Task

COLUMNS = (("discovery", "Discovery"), ("requirement", "Requirements"), ("criteria", "Criteria"),
           ("asset", "Prompt"), ("eval", "Golden set"), ("task", "Tasks"))
NODE_W, NODE_H = 176, 44
COL_GAP, ROW_GAP = 56, 14
PAD_X, PAD_TOP = 16, 44
MAX_TITLE = 24


def short(text: str) -> str:
    return text if len(text) <= MAX_TITLE else text[:MAX_TITLE - 1].rstrip() + "…"


def layout(content: list[Artifact], tasks: list[Task]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    by_column: dict[str, list[dict[str, Any]]] = {key: [] for key, _ in COLUMNS}
    for a in content:
        if a.type in by_column:
            by_column[a.type].append({
                "id": a.id, "label": f"{a.id} v{a.version}", "title": short(a.title), "full": a.title,
                "status": a.status, "type": a.type})
    for t in tasks:
        by_column["task"].append({"id": t.id, "label": t.id, "title": short(t.title), "full": t.title,
                                  "status": "approved", "type": "task"})
    for c, (key, _) in enumerate(COLUMNS):
        for r, node in enumerate(by_column[key]):
            node["x"] = PAD_X + c * (NODE_W + COL_GAP)
            node["y"] = PAD_TOP + r * (NODE_H + ROW_GAP)
            nodes.append(node)
    where = {n["id"]: n for n in nodes}
    edges: list[dict[str, str]] = []

    def link(child: str, parent: str) -> None:
        if child in where and parent in where:
            a, b = where[child], where[parent]
            x1, y1 = a["x"], a["y"] + NODE_H / 2
            x2, y2 = b["x"] + NODE_W, b["y"] + NODE_H / 2
            mid = (x1 + x2) / 2
            edges.append({"from": child, "to": parent,
                          "d": f"M{x1:.0f} {y1:.0f} C{mid:.0f} {y1:.0f} {mid:.0f} {y2:.0f} {x2:.0f} {y2:.0f}"})

    for a in content:
        for p in a.parents:
            link(a.id, p.id)
    for t in tasks:
        for c in t.criteria:
            link(t.id, c)
    rows = max((len(v) for v in by_column.values()), default=0)
    return {
        "nodes": nodes, "edges": edges,
        "columns": [{"label": label, "x": PAD_X + c * (NODE_W + COL_GAP)} for c, (_, label) in enumerate(COLUMNS)],
        "width": PAD_X * 2 + len(COLUMNS) * NODE_W + (len(COLUMNS) - 1) * COL_GAP,
        "height": PAD_TOP + max(rows, 1) * (NODE_H + ROW_GAP),
        "node_w": NODE_W, "node_h": NODE_H,
    }
