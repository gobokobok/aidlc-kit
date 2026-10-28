"""Engineer decomposition: a technical plan scaffolded from the handoff
package. Each task names the criteria it satisfies; tasks with none are
flagged, and criteria that no task covers are called out.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aidlc.artifacts import Artifact
from aidlc.evals.runner import fenced_block

TASK_ID_RE = re.compile(r"^T-\d{3,}$")
FLAG_MARKERS = ("satisfies no criterion", "no task satisfies")


def is_flag(message: str) -> bool:
    return any(m in message for m in FLAG_MARKERS)


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    criteria: tuple[str, ...]


def parse_tasks(body: str) -> tuple[list[Task], list[str]]:
    """Tasks from the yaml block under `## Tasks`, and plain-language problems."""
    block = fenced_block(body, "Tasks")
    if block is None:
        return [], ["has no task list: put the tasks in a ```yaml block under '## Tasks'"]
    try:
        raw = yaml.safe_load(block)
    except yaml.YAMLError:
        return [], ["the task list is not valid YAML"]
    if not isinstance(raw, list) or not raw:
        return [], ["the task list must be a list of tasks"]
    tasks, problems, seen = [], [], set()
    for n, t in enumerate(raw, 1):
        if not isinstance(t, dict):
            problems.append(f"task #{n} must be a set of fields (id, title, criteria)")
            continue
        tid, title = t.get("id"), t.get("title")
        if not isinstance(tid, str) or not TASK_ID_RE.match(tid):
            problems.append(f"task #{n} needs an id like T-001")
            continue
        if tid in seen:
            problems.append(f"task {tid} is listed more than once")
        seen.add(tid)
        if not isinstance(title, str) or not title.strip():
            problems.append(f"task {tid} needs a title")
            continue
        crit = t.get("criteria") or []
        if not isinstance(crit, list) or not all(isinstance(c, str) for c in crit):
            problems.append(f"task {tid}: criteria must be a list of criterion IDs")
            continue
        tasks.append(Task(tid, title.strip(), tuple(crit)))
    return tasks, problems


def check(dec: Artifact, criteria_ids: set[str]) -> list[tuple[str, str]]:
    """(severity, message) findings. A task that satisfies no criterion is
    flagged (a warning, shown to the author and in the review request) rather
    than blocked: the reviewer decides whether the work is needed."""
    tasks, problems = parse_tasks(dec.body)
    out = [("error", p) for p in problems]
    covered: set[str] = set()
    for t in tasks:
        if not t.criteria:
            out.append(("warning", f"task {t.id} \"{t.title}\" satisfies no criterion; link it to one or "
                                   "drop it"))
        for c in t.criteria:
            if c not in criteria_ids:
                out.append(("error", f"task {t.id} points at {c}, which is not a criterion in this feature"))
            covered.add(c)
    if tasks and not problems:
        for c in sorted(criteria_ids - covered):
            out.append(("warning", f"no task satisfies {c}"))
    return out


def tasks_yaml(criteria: list[Artifact]) -> str:
    """Starter tasks: one per criterion, plus the regression gate."""
    rows: list[dict[str, Any]] = [
        {"id": f"T-{n:03d}", "title": f"Build and verify: {c.title}", "criteria": [c.id]}
        for n, c in enumerate(criteria, 1)
    ]
    rows.append({"id": f"T-{len(criteria) + 1:03d}",
                 "title": "Run the golden set in CI as the regression gate",
                 "criteria": [c.id for c in criteria]})
    return yaml.safe_dump(rows, sort_keys=False, allow_unicode=True, default_flow_style=None).rstrip("\n")


def components(requirements: list[Artifact]) -> list[str]:
    return [f"{r.id} {r.title}: which component delivers it (to fill in)" for r in requirements] or [
        "Name the components (to fill in)"]


def read_manifest(folder: Path) -> dict[str, Any]:
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
