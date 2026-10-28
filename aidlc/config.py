"""Kit configuration (`aidlc.yaml`) and repository root discovery.

`aidlc.yaml` is the single source of truth for people, roles, review routing
and risk tiers. CODEOWNERS is generated from it, never edited by hand.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from aidlc.artifacts import TYPES, USERNAME_RE, Issue, check_thresholds

CONFIG_FILE = "aidlc.yaml"
DEFAULT_NAME = "AIDLC Kit"

# Role pseudo-names that are resolved, never assigned to people.
PM_PEER = "pm_peer"          # any person with role `pm` other than the author
ANY_REVIEWER = "any_reviewer"  # anyone other than the author (unrouted types)
RESERVED_ROLES = frozenset({PM_PEER, ANY_REVIEWER})

REQUIRED_TIERS = ("T1", "T2", "T3")
ROLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TIER_RE = re.compile(r"^T(\d+)$")
TIER_FIELDS = {"label", "extra_reviewers", "required_artifacts", "min_thresholds", "human_in_loop"}


@dataclass(frozen=True)
class Tier:
    name: str
    label: str
    extra_reviewers: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()
    min_thresholds: dict[str, float] = field(default_factory=dict)
    human_in_loop: bool = False

    @property
    def rank(self) -> int:
        return tier_rank(self.name)

    @property
    def display(self) -> str:
        return f"Tier {self.rank} ({self.label})"


DEFAULT_TIERS = {
    "T1": Tier("T1", "Low"),
    "T2": Tier("T2", "Medium"),
    "T3": Tier("T3", "High"),
}


@dataclass(frozen=True)
class Config:
    display_name: str = DEFAULT_NAME
    people: dict[str, tuple[str, ...]] = field(default_factory=dict)
    review_routing: dict[str, tuple[str, ...]] = field(default_factory=dict)
    risk_tiers: dict[str, Tier] = field(default_factory=lambda: dict(DEFAULT_TIERS))
    thresholds: dict[str, float] = field(default_factory=dict)

    def tier(self, name: str) -> Tier:
        return self.risk_tiers[name]


def tier_rank(name: str) -> int:
    m = TIER_RE.match(name)
    if not m:
        raise ValueError(f"not a tier name: {name!r}")
    return int(m.group(1))


def find_root(start: Path) -> Path:
    """Nearest folder at or above `start` holding aidlc.yaml, else `start`."""
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / CONFIG_FILE).is_file():
            return folder
    return start


def _role_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(r, str) and ROLE_RE.match(r) for r in value)


def check_config(raw: Any) -> list[Issue]:
    """Schema check for aidlc.yaml, plus warnings for roles nobody holds."""
    where = CONFIG_FILE
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [Issue("error", where, "must be a set of `key: value` lines")]
    issues: list[Issue] = []

    def err(msg: str) -> None:
        issues.append(Issue("error", where, msg))

    name = raw.get("display_name", DEFAULT_NAME)
    if not isinstance(name, str) or not name.strip():
        err("display_name must be a non-empty line of text")

    held: dict[str, list[str]] = {}
    people = raw.get("people", {}) or {}
    if not isinstance(people, dict):
        err("people must map a GitHub username to a list of roles")
        people = {}
    for user, roles in people.items():
        if not isinstance(user, str) or not USERNAME_RE.match(user):
            err(f"people: {user!r} is not a GitHub username")
        elif not _role_list(roles):
            err(f"people.{user} must be a list of role names like [tech_reviewer]")
        else:
            for role in roles:
                if role in RESERVED_ROLES:
                    err(f"people.{user}: {role} is worked out automatically and cannot be assigned")
                held.setdefault(role, []).append(user)

    used: dict[str, str] = {}  # role -> where it is required, for warnings
    routing = raw.get("review_routing", {}) or {}
    if not isinstance(routing, dict):
        err("review_routing must map an artifact type to a list of roles")
        routing = {}
    for a_type, roles in routing.items():
        if a_type not in TYPES:
            err(f"review_routing: {a_type!r} is not an artifact type ({', '.join(TYPES)})")
        elif not _role_list(roles) or not roles:
            err(f"review_routing.{a_type} must be a non-empty list of role names")
        else:
            for role in roles:
                used.setdefault(role, f"{a_type} artifacts")

    tiers = raw.get("risk_tiers")
    if tiers is not None:
        if not isinstance(tiers, dict):
            err("risk_tiers must map a tier name (T1, T2, T3) to its settings")
            tiers = {}
        for missing in (t for t in REQUIRED_TIERS if t not in tiers):
            err(f"risk_tiers must define {missing}")
        for t_name, spec in tiers.items():
            at = f"risk_tiers.{t_name}"
            if not isinstance(t_name, str) or not TIER_RE.match(t_name):
                err(f"risk_tiers: {t_name!r} must be named like T1")
                continue
            if not isinstance(spec, dict):
                err(f"{at} must be a set of settings")
                continue
            unknown = set(spec) - TIER_FIELDS
            if unknown:
                err(f"{at}: unknown setting(s) {', '.join(sorted(unknown))}")
            if not isinstance(spec.get("label"), str) or not spec["label"].strip():
                err(f"{at}.label must be a short name like Medium")
            extras = spec.get("extra_reviewers", [])
            if not _role_list(extras):
                err(f"{at}.extra_reviewers must be a list of role names")
            else:
                for role in extras:
                    used.setdefault(role, f"Tier {t_name}")
            required = spec.get("required_artifacts", [])
            if not isinstance(required, list) or any(r not in TYPES for r in required):
                err(f"{at}.required_artifacts must list artifact types ({', '.join(TYPES)})")
            issues.extend(check_thresholds(spec.get("min_thresholds", {}) or {}, at))
            if not isinstance(spec.get("human_in_loop", False), bool):
                err(f"{at}.human_in_loop must be true or false")

    if "thresholds" in raw:
        issues.extend(check_thresholds(raw["thresholds"], where))

    if not any(i.severity == "error" for i in issues):
        for role, needed_by in used.items():
            if role == PM_PEER:
                if len(held.get("pm", [])) < 2:
                    issues.append(Issue("warning", where, (
                        f"{needed_by} need a PM peer, but fewer than two people have role pm, "
                        "so a PM can never get a peer approval")))
            elif role not in held and role not in RESERVED_ROLES:
                issues.append(Issue("warning", where, (
                    f"{needed_by} need role {role}, but nobody in `people` has it")))
    return issues


def _build(raw: dict[str, Any]) -> Config:
    tiers = raw.get("risk_tiers")
    return Config(
        display_name=raw.get("display_name", DEFAULT_NAME).strip(),
        people={u: tuple(r) for u, r in (raw.get("people") or {}).items()},
        review_routing={t: tuple(r) for t, r in (raw.get("review_routing") or {}).items()},
        risk_tiers=dict(DEFAULT_TIERS) if tiers is None else {
            name: Tier(
                name=name,
                label=spec["label"].strip(),
                extra_reviewers=tuple(spec.get("extra_reviewers", [])),
                required_artifacts=tuple(spec.get("required_artifacts", [])),
                min_thresholds=dict(spec.get("min_thresholds") or {}),
                human_in_loop=spec.get("human_in_loop", False),
            )
            for name, spec in sorted(tiers.items(), key=lambda kv: tier_rank(kv[0]))
        },
        thresholds=dict(raw.get("thresholds") or {}),
    )


def parse_config(text: str) -> tuple[Config, list[Issue]]:
    """Parse aidlc.yaml text. Invalid config returns defaults plus the issues."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError:
        return Config(), [Issue("error", CONFIG_FILE, "is not valid YAML")]
    issues = check_config(raw)
    if raw is None or any(i.severity == "error" for i in issues):
        return Config(), issues
    return _build(raw), issues


def load_config(root: Path) -> tuple[Config, list[Issue]]:
    """Load aidlc.yaml. A missing file means defaults."""
    path = root / CONFIG_FILE
    if not path.is_file():
        return Config(), []
    return parse_config(path.read_text(encoding="utf-8"))
