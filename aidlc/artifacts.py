"""Artifact model: frontmatter parsing, schema validation, IDs and versions.

An artifact is a Markdown file with YAML frontmatter. This module knows about
one artifact at a time; rules that span artifacts live in trace.py and
validate.py.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Artifact type -> ID prefix.
TYPES: dict[str, str] = {
    "discovery": "DISC",
    "requirement": "REQ",
    "criteria": "AC",
    "asset": "ASSET",
    "eval": "EVAL",
    "handoff": "HND",
    "decomposition": "DEC",
    "risk": "RISK",
    "privacy_assessment": "PIA",
}

STATUSES = ("draft", "in_review", "approved", "rejected", "stale")

# Which types may be parents of which. Every edge points "up" the lifecycle,
# so the trace graph cannot contain cycles. Risk is a root: revising it
# changes gate requirements, it does not make content artifacts stale.
ALLOWED_PARENTS: dict[str, frozenset[str]] = {
    "discovery": frozenset(),
    "requirement": frozenset({"discovery"}),
    "criteria": frozenset({"requirement"}),
    "asset": frozenset({"criteria"}),
    "eval": frozenset({"criteria", "asset"}),
    "handoff": frozenset({
        "discovery", "requirement", "criteria", "asset", "eval", "risk", "privacy_assessment",
    }),
    "decomposition": frozenset({"handoff"}),
    "risk": frozenset(),
    "privacy_assessment": frozenset({"discovery", "risk"}),
}

# Where each type lives inside a feature folder.
LOCATIONS: dict[str, str] = {
    "discovery": "discovery.md",
    "requirement": "requirements/{id}.md",
    "criteria": "criteria/{id}.md",
    "asset": "assets/{id}.md",
    "eval": "evals/{id}.md",
    "handoff": "handoff/{id}/handoff.md",
    "decomposition": "decomposition/{id}.md",
    "risk": "risk.md",
    "privacy_assessment": "privacy_assessment.md",
}

CORE_KEYS = (
    "id", "type", "feature", "title", "version", "status",
    "owner", "parents", "approvals", "updated_at",
)

FEATURE_ID_RE = re.compile(r"^FEAT-\d{3,}$")
FEATURE_DIR_RE = re.compile(r"^(FEAT-\d{3,})(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$")
ARTIFACT_ID_RE = re.compile(r"^([A-Z]+)-(\d{3,})$")
# GitHub usernames: alphanumerics and single hyphens, max 39 chars.
USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")

# Threshold metrics that are rates and must sit in [0, 1].
RATE_METRICS = frozenset({"accuracy", "precision", "recall", "f1", "urgent_recall"})

FRONTMATTER_FENCE = "---"


@dataclass(frozen=True)
class Issue:
    """A validation finding, phrased for a PM to read."""

    severity: str  # "error" | "warning"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity}: {self.where}: {self.message}"


@dataclass(frozen=True)
class ParentRef:
    id: str
    version: int


@dataclass(frozen=True)
class Approval:
    by: str
    version: int
    at: datetime


@dataclass(frozen=True)
class Artifact:
    id: str
    type: str
    feature: str
    title: str
    version: int
    status: str
    owner: str
    parents: tuple[ParentRef, ...]
    approvals: tuple[Approval, ...]
    updated_at: datetime
    extra: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    path: Path | None = None

    @property
    def approved_current(self) -> tuple[Approval, ...]:
        """Approvals that count: those given for the current version."""
        return tuple(a for a in self.approvals if a.version == self.version)


class ArtifactError(ValueError):
    """Raised when a file cannot be read as a valid artifact."""

    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("; ".join(str(i) for i in issues))


# --- time ----------------------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def format_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


# --- IDs and paths -------------------------------------------------------

def id_prefix(artifact_type: str) -> str:
    return TYPES[artifact_type]


def type_for_id(artifact_id: str) -> str | None:
    m = ARTIFACT_ID_RE.match(artifact_id)
    if not m:
        return None
    for t, prefix in TYPES.items():
        if prefix == m.group(1):
            return t
    return None


def next_id(artifact_type: str, used_ids: Iterable[str]) -> str:
    """Next sequential ID for a type. `used_ids` should include retired IDs
    (e.g. from the audit log) so a deleted ID is never handed out again."""
    prefix = id_prefix(artifact_type)
    highest = 0
    for used in used_ids:
        m = ARTIFACT_ID_RE.match(used)
        if m and m.group(1) == prefix:
            highest = max(highest, int(m.group(2)))
    return f"{prefix}-{highest + 1:03d}"


def relative_path(artifact_type: str, artifact_id: str) -> str:
    """Path of an artifact relative to its feature folder."""
    return LOCATIONS[artifact_type].format(id=artifact_id)


def feature_id_from_dir(name: str) -> str | None:
    m = FEATURE_DIR_RE.match(name)
    return m.group(1) if m else None


# --- frontmatter ---------------------------------------------------------

def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Split a document into (yaml, body). None if it has no frontmatter."""
    text = text.replace("\r\n", "\n")
    if not text.startswith(FRONTMATTER_FENCE + "\n"):
        return None
    rest = text[len(FRONTMATTER_FENCE) + 1:]
    if rest.startswith(FRONTMATTER_FENCE + "\n"):
        return "", rest[len(FRONTMATTER_FENCE) + 1:]
    end = rest.find("\n" + FRONTMATTER_FENCE + "\n")
    if end == -1:
        if rest.endswith("\n" + FRONTMATTER_FENCE):
            return rest[: -len(FRONTMATTER_FENCE) - 1], ""
        return None
    return rest[:end], rest[end + len(FRONTMATTER_FENCE) + 2:]


def check_thresholds(value: Any, where: str) -> list[Issue]:
    """Thresholds are a mapping of metric name -> number."""
    if not isinstance(value, dict):
        return [Issue("error", where, "thresholds must be a list of `metric: number` lines")]
    issues = []
    for name, limit in value.items():
        if not isinstance(name, str) or not re.match(r"^[a-z][a-z0-9_]*$", name):
            issues.append(Issue("error", where, f"threshold name {name!r} must be lower_snake_case"))
            continue
        if isinstance(limit, bool) or not isinstance(limit, (int, float)):
            issues.append(Issue("error", where, f"threshold {name} must be a number, got {limit!r}"))
        elif name in RATE_METRICS and not 0 <= limit <= 1:
            issues.append(Issue("error", where, f"threshold {name} is a rate and must be between 0 and 1"))
        elif name.startswith(("max_", "min_")) and limit < 0:
            issues.append(Issue("error", where, f"threshold {name} cannot be negative"))
    return issues


def looser_than(name: str, value: float, floor: float) -> bool:
    """Whether a threshold is less strict than a required minimum. For
    `max_*` metrics a higher limit is looser; for the rest, a lower one."""
    return value > floor if name.startswith("max_") else value < floor


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def check_meta(meta: Any, where: str) -> list[Issue]:
    """Schema check for one artifact's frontmatter. Pure; no repo context."""
    if not isinstance(meta, dict):
        return [Issue("error", where, "frontmatter must be a set of `key: value` lines")]

    issues: list[Issue] = []

    def err(msg: str) -> None:
        issues.append(Issue("error", where, msg))

    missing = [k for k in CORE_KEYS if k not in meta]
    if missing:
        err(f"missing required field(s): {', '.join(missing)}")

    a_type = meta.get("type")
    if "type" in meta and a_type not in TYPES:
        err(f"type {a_type!r} is not one of: {', '.join(TYPES)}")
        a_type = None

    a_id = meta.get("id")
    if "id" in meta:
        if not isinstance(a_id, str) or not ARTIFACT_ID_RE.match(a_id):
            err(f"id {a_id!r} must look like REQ-001")
        elif a_type and not a_id.startswith(TYPES[a_type] + "-"):
            err(f"id {a_id} does not match type {a_type} (expected {TYPES[a_type]}-xxx)")

    feature = meta.get("feature")
    if "feature" in meta and (not isinstance(feature, str) or not FEATURE_ID_RE.match(feature)):
        err(f"feature {feature!r} must look like FEAT-001")

    title = meta.get("title")
    if "title" in meta and (not isinstance(title, str) or not title.strip()):
        err("title must be a non-empty line of text")

    version = meta.get("version")
    if "version" in meta and (not _is_int(version) or version < 1):
        err(f"version must be a whole number of 1 or more, got {version!r}")
        version = None

    status = meta.get("status")
    if "status" in meta and status not in STATUSES:
        err(f"status {status!r} is not one of: {', '.join(STATUSES)}")

    owner = meta.get("owner")
    if "owner" in meta and (not isinstance(owner, str) or not USERNAME_RE.match(owner)):
        err(f"owner {owner!r} must be a GitHub username")

    if "updated_at" in meta and _parse_ts(meta["updated_at"]) is None:
        err("updated_at must be a timestamp with a timezone, like 2026-10-29T09:12:00Z")

    parents = meta.get("parents")
    if "parents" in meta:
        if parents is None:
            parents = []
        if not isinstance(parents, list):
            err("parents must be a list")
        else:
            for i, p in enumerate(parents, 1):
                if not isinstance(p, dict) or set(p) != {"id", "version"}:
                    err(f"parent #{i} must be {{id: XXX-001, version: N}}")
                    continue
                if not isinstance(p["id"], str) or not ARTIFACT_ID_RE.match(p["id"]):
                    err(f"parent #{i} id {p['id']!r} must look like REQ-001")
                if not _is_int(p["version"]) or p["version"] < 1:
                    err(f"parent #{i} version must be a whole number of 1 or more")

    approvals = meta.get("approvals")
    if "approvals" in meta:
        if approvals is None:
            approvals = []
        if not isinstance(approvals, list):
            err("approvals must be a list")
        else:
            for i, ap in enumerate(approvals, 1):
                if not isinstance(ap, dict) or set(ap) != {"by", "version", "at"}:
                    err(f"approval #{i} must be {{by: username, version: N, at: timestamp}}")
                    continue
                if not isinstance(ap["by"], str) or not USERNAME_RE.match(ap["by"]):
                    err(f"approval #{i} 'by' must be a GitHub username")
                if not _is_int(ap["version"]) or ap["version"] < 1:
                    err(f"approval #{i} version must be a whole number of 1 or more")
                if _parse_ts(ap["at"]) is None:
                    err(f"approval #{i} 'at' must be a timestamp with a timezone")

    if "thresholds" in meta:
        issues.extend(check_thresholds(meta["thresholds"], where))

    return issues


def from_meta(meta: dict[str, Any], body: str = "", path: Path | None = None) -> Artifact:
    """Build an Artifact from frontmatter. Raises ArtifactError if invalid."""
    where = str(path) if path else "<artifact>"
    issues = check_meta(meta, where)
    if any(i.severity == "error" for i in issues):
        raise ArtifactError(issues)
    return Artifact(
        id=meta["id"],
        type=meta["type"],
        feature=meta["feature"],
        title=meta["title"].strip(),
        version=meta["version"],
        status=meta["status"],
        owner=meta["owner"],
        parents=tuple(ParentRef(p["id"], p["version"]) for p in meta["parents"] or []),
        approvals=tuple(
            Approval(a["by"], a["version"], _parse_ts(a["at"])) for a in meta["approvals"] or []
        ),
        updated_at=_parse_ts(meta["updated_at"]),
        extra={k: v for k, v in meta.items() if k not in CORE_KEYS},
        body=body,
        path=path,
    )


def parse(text: str, path: Path | None = None) -> Artifact:
    """Parse a Markdown document with frontmatter into an Artifact."""
    where = str(path) if path else "<artifact>"
    parts = split_frontmatter(text)
    if parts is None:
        raise ArtifactError([Issue("error", where, "file does not start with a `---` frontmatter block")])
    raw, body = parts
    try:
        meta = yaml.safe_load(raw) if raw.strip() else {}
    except yaml.YAMLError as exc:
        line = getattr(getattr(exc, "problem_mark", None), "line", None)
        hint = f" near line {line + 2}" if line is not None else ""
        raise ArtifactError([Issue("error", where, f"frontmatter is not valid YAML{hint}")]) from exc
    return from_meta(meta, body, path)


def load(path: Path) -> Artifact:
    return parse(path.read_text(encoding="utf-8"), path)


# --- serialisation -------------------------------------------------------

class _FlowMap(dict):
    """A mapping rendered inline: `{id: REQ-001, version: 2}`."""


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        # Indent list items under their key, as people usually write YAML.
        super().increase_indent(flow, False)


_Dumper.add_representer(
    datetime, lambda d, v: d.represent_scalar("tag:yaml.org,2002:timestamp", format_ts(v))
)
_Dumper.add_representer(
    _FlowMap, lambda d, v: d.represent_mapping("tag:yaml.org,2002:map", v, flow_style=True)
)


def to_meta(a: Artifact) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "id": a.id,
        "type": a.type,
        "feature": a.feature,
        "title": a.title,
        "version": a.version,
        "status": a.status,
        "owner": a.owner,
        "parents": [_FlowMap(id=p.id, version=p.version) for p in a.parents],
        # PyYAML cannot write a bare timestamp inside an inline map, so `at`
        # is written as a quoted string; parsing accepts both forms.
        "approvals": [
            _FlowMap(by=ap.by, version=ap.version, at=format_ts(ap.at)) for ap in a.approvals
        ],
        "updated_at": a.updated_at,
    }
    meta.update(a.extra)
    return meta


def dumps(a: Artifact) -> str:
    raw = yaml.dump(to_meta(a), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)
    return f"{FRONTMATTER_FENCE}\n{raw}{FRONTMATTER_FENCE}\n{a.body}"


def save(a: Artifact, path: Path | None = None) -> Path:
    target = path or a.path
    if target is None:
        raise ValueError(f"{a.id} has no path to save to")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps(a), encoding="utf-8")
    return target


# --- versions ------------------------------------------------------------

def has_been_reviewed(a: Artifact) -> bool:
    """True if the current version has been put in front of a reviewer."""
    return a.status in ("in_review", "approved", "rejected") or bool(a.approved_current)


def apply_edit(a: Artifact, now: datetime, **changes: Any) -> Artifact:
    """Return the artifact after a content edit.

    Once a version has been reviewed it is frozen: an edit produces the next
    version, clears approvals and returns the artifact to draft. Edits to an
    unreviewed draft keep the version number.
    """
    if has_been_reviewed(a):
        changes.setdefault("version", a.version + 1)
        changes.setdefault("approvals", ())
    if a.status != "draft":
        changes.setdefault("status", "draft")
    return replace(a, updated_at=now, **changes)
