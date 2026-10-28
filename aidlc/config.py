"""Kit configuration (`aidlc.yaml`) and repository root discovery."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from aidlc.artifacts import USERNAME_RE, Issue, check_thresholds

CONFIG_FILE = "aidlc.yaml"
DEFAULT_NAME = "AIDLC Kit"


@dataclass(frozen=True)
class Config:
    display_name: str = DEFAULT_NAME
    roles: dict[str, tuple[str, ...]] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)


def find_root(start: Path) -> Path:
    """Nearest folder at or above `start` holding aidlc.yaml, else `start`."""
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / CONFIG_FILE).is_file():
            return folder
    return start


def check_config(raw: Any) -> list[Issue]:
    where = CONFIG_FILE
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [Issue("error", where, "must be a set of `key: value` lines")]
    issues: list[Issue] = []
    name = raw.get("display_name", DEFAULT_NAME)
    if not isinstance(name, str) or not name.strip():
        issues.append(Issue("error", where, "display_name must be a non-empty line of text"))
    roles = raw.get("roles", {})
    if not isinstance(roles, dict):
        issues.append(Issue("error", where, "roles must map a role name to a list of usernames"))
    else:
        for role, users in roles.items():
            if not isinstance(users, list) or not all(
                isinstance(u, str) and USERNAME_RE.match(u) for u in users
            ):
                issues.append(Issue("error", where, f"roles.{role} must be a list of GitHub usernames"))
    if "thresholds" in raw:
        issues.extend(check_thresholds(raw["thresholds"], where))
    return issues


def load_config(root: Path) -> tuple[Config, list[Issue]]:
    """Load aidlc.yaml. A missing file means defaults; an invalid one
    returns defaults plus the issues found."""
    path = root / CONFIG_FILE
    if not path.is_file():
        return Config(), []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return Config(), [Issue("error", CONFIG_FILE, "is not valid YAML")]
    issues = check_config(raw)
    if issues or raw is None:
        return Config(), issues
    return Config(
        display_name=raw.get("display_name", DEFAULT_NAME).strip(),
        roles={r: tuple(u) for r, u in raw.get("roles", {}).items()},
        thresholds=dict(raw.get("thresholds", {})),
    ), []
