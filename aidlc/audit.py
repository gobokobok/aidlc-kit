"""Append-only audit log: `audit/log.jsonl`, written only by CI on merge.

One JSON line per artifact changed on `main`. Nothing ever rewrites or
removes a line; `check_log` proves it by comparing with an earlier commit.
"""

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from aidlc import artifacts as art
from aidlc import reviewers, risk
from aidlc.artifacts import Artifact, ArtifactError
from aidlc.config import Config

LOG = "audit/log.jsonl"
FIELDS = ("at", "feature", "id", "version", "status", "actor", "approvers", "tier",
          "roles_satisfied", "commit", "pr")
PR_IN_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")


def read_entries(root: Path) -> list[dict[str, Any]]:
    path = root / LOG
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            entries.append(value)
    return entries


def check_log(old: str | None, new: str | None, frozen: bool = False) -> list[str]:
    """Problems with the log compared with an earlier version, in plain words.
    `frozen` (pull requests): the log must not change at all."""
    old, new = old or "", new or ""
    if frozen:
        return [] if old == new else [
            f"{LOG} was changed in this pull request. Only CI writes it, after a merge."]
    old_lines, new_lines = old.splitlines(), new.splitlines()
    problems = []
    if new_lines[: len(old_lines)] != old_lines:
        first = next((i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b),
                     min(len(old_lines), len(new_lines)))
        problems.append(f"{LOG} line {first + 1} was changed or removed; the log is append-only.")
    for n, line in enumerate(new_lines[len(old_lines):], len(old_lines) + 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"{LOG} line {n} is not valid JSON.")
            continue
        missing = [f for f in FIELDS if not isinstance(value, dict) or f not in value]
        if missing:
            problems.append(f"{LOG} line {n} is missing: {', '.join(missing)}.")
    return problems


def pr_from_subject(subject: str) -> int | None:
    """GitHub's squash merge subject ends with '(#12)'."""
    m = PR_IN_SUBJECT.search(subject)
    return int(m.group(1)) if m else None


def entry(a: Artifact, items: list[Artifact], config: Config, actor: str, commit: str,
          pr: int | None, now: datetime, status: str | None = None) -> dict[str, Any]:
    tier = risk.feature_tier(items, config)
    checks = reviewers.role_checks(config, a, tier)
    return {
        "at": art.format_ts(now),
        "feature": a.feature,
        "id": a.id,
        "version": a.version,
        "status": status or a.status,
        "actor": actor,
        "approvers": sorted({ap.by for ap in a.approved_current}),
        "tier": tier.name if tier else None,
        "roles_satisfied": [c.role for c in checks if c.satisfied],
        "commit": commit,
        "pr": pr,
    }


def build_entries(
    changed: list[str],
    load_head: Callable[[str], list[Artifact]],
    read_before: Callable[[str], str | None],
    config: Config,
    actor: str,
    commit: str,
    pr: int | None,
    now: datetime,
) -> list[dict[str, Any]]:
    """Entries for changed artifact paths. `load_head(feature_dir)` gives the
    feature's artifacts after the change; `read_before(path)` the old text,
    used to record deletions."""
    out = []
    for path in sorted(p for p in changed if p.startswith("features/") and p.endswith(".md")):
        feature_dir = "/".join(path.split("/")[:2])
        items = load_head(feature_dir)
        current = next((a for a in items if a.path and a.path.as_posix().endswith("/" + path)), None)
        if current is not None:
            out.append(entry(current, items, config, actor, commit, pr, now))
            continue
        old_text = read_before(path)
        if old_text is None:
            continue
        try:
            old = art.parse(old_text)
        except ArtifactError:
            continue
        out.append(entry(old, items, config, actor, commit, pr, now, status="deleted"))
    return sorted(out, key=lambda e: (e["feature"], e["id"]))


def append(root: Path, entries: list[dict[str, Any]]) -> None:
    path = root / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    if old and not old.endswith("\n"):
        old += "\n"
    lines = "".join(json.dumps(e, ensure_ascii=False, sort_keys=False) + "\n" for e in entries)
    path.write_text(old + lines, encoding="utf-8")
