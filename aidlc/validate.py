"""Repository-wide validation: everything CI `validate` checks.

Loading touches the filesystem; the rules themselves (`check_feature`) are
pure functions over already-loaded artifacts.
"""

from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from aidlc import artifacts as art
from aidlc import trace
from aidlc.artifacts import ALLOWED_PARENTS, LOCATIONS, Artifact, ArtifactError, Issue
from aidlc.config import load_config

FEATURES_DIR = "features"


@dataclass(frozen=True)
class Report:
    artifacts: tuple[Artifact, ...]
    issues: tuple[Issue, ...]

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class StatusChange:
    artifact: Artifact
    old: str
    new: str


def feature_dirs(root: Path) -> list[Path]:
    base = root / FEATURES_DIR
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))


def _expected_id(artifact_type: str, rel: Path) -> str | None:
    """The ID implied by a file's location, if the location encodes one."""
    if "{id}" not in LOCATIONS[artifact_type]:
        return None
    return rel.parent.name if artifact_type == "handoff" else rel.stem


def _label(a: Artifact) -> str:
    return f"{a.feature}/{a.id}"


def load_feature(feature_dir: Path, root: Path) -> tuple[str | None, list[Artifact], list[Issue]]:
    """Load every artifact in a feature folder and check it sits where it should."""
    feature_id = art.feature_id_from_dir(feature_dir.name)
    rel_dir = feature_dir.relative_to(root)
    if feature_id is None:
        return None, [], [Issue(
            "error", str(rel_dir),
            "feature folder name must look like FEAT-001 or FEAT-001-short-name",
        )]

    loaded: list[Artifact] = []
    issues: list[Issue] = []
    for a_type, pattern in LOCATIONS.items():
        for path in sorted(feature_dir.glob(pattern.format(id="*"))):
            where = str(path.relative_to(root))
            try:
                a = art.load(path)
            except ArtifactError as exc:
                issues.extend(replace(i, where=where) for i in exc.issues)
                continue
            if a.type != a_type:
                issues.append(Issue(
                    "error", where,
                    f"file is stored as a {a_type} but says `type: {a.type}`",
                ))
                continue
            expected = _expected_id(a_type, path.relative_to(feature_dir))
            if expected is not None and expected != a.id:
                issues.append(Issue(
                    "error", where, f"file location says {expected} but the file says `id: {a.id}`",
                ))
            if a.feature != feature_id:
                issues.append(Issue(
                    "error", where, f"file is in {feature_id} but says `feature: {a.feature}`",
                ))
            loaded.append(a)
    return feature_id, loaded, issues


def check_feature(items: list[Artifact]) -> list[Issue]:
    """Cross-artifact rules for one feature. Pure."""
    issues: list[Issue] = []
    counts = Counter(a.id for a in items)
    for dup, n in counts.items():
        if n > 1:
            issues.append(Issue("error", dup, f"ID {dup} is used by {n} artifacts; IDs must be unique"))
    by_id = trace.index(items)

    for a in items:
        where = _label(a)

        def err(msg: str) -> None:
            issues.append(Issue("error", where, msg))

        def warn(msg: str) -> None:
            issues.append(Issue("warning", where, msg))

        # Parent links
        if not a.parents and ALLOWED_PARENTS[a.type]:
            msg = f"has no parent; a {a.type} should link to a {' or '.join(sorted(ALLOWED_PARENTS[a.type]))}"
            (warn if a.status == "draft" else err)(msg)
        for ref, n in Counter(p.id for p in a.parents).items():
            if n > 1:
                warn(f"lists parent {ref} more than once")
        for ref in a.parents:
            parent = by_id.get(ref.id)
            if ref.id == a.id:
                err("lists itself as a parent")
            elif parent is None:
                err(f"links to {ref.id}, which does not exist in {a.feature}")
            elif parent.type not in ALLOWED_PARENTS[a.type]:
                err(f"a {a.type} cannot have a {parent.type} ({ref.id}) as its parent")
            elif ref.version > parent.version:
                err(f"links to {ref.id} v{ref.version}, but {ref.id} is only at v{parent.version}")

        # Approvals
        for ap in a.approvals:
            if ap.by == a.owner:
                err(f"{ap.by} approved their own artifact; the approver must be someone else")
            if ap.version > a.version:
                err(f"approval by {ap.by} is for v{ap.version}, which does not exist yet (current v{a.version})")
            elif ap.version < a.version:
                warn(f"approval by {ap.by} was for v{ap.version} and no longer counts for v{a.version}")
        if a.status == "approved" and not any(ap.by != a.owner for ap in a.approved_current):
            err(f"is marked approved but nobody other than the owner approved v{a.version}")

        # Computed status
        expected = trace.expected_status(a, by_id)
        if expected != a.status:
            if expected == "stale":
                moved = ", ".join(f"{r.id} is now v{cur} (linked to v{r.version})"
                                  for r, cur in trace.stale_parents(a, by_id))
                err(f"is out of date because {moved}; run `aidlc validate --write` to mark it stale")
            else:
                err(f"is marked stale but is up to date with its parents; "
                    f"run `aidlc validate --write` to return it to {expected}")

        if a.type == "criteria" and "thresholds" not in a.extra:
            warn("criteria has no thresholds; the defaults in aidlc.yaml will apply")

    return issues


def load_repo(root: Path) -> tuple[list[Artifact], list[Issue]]:
    items: list[Artifact] = []
    issues: list[Issue] = []
    seen_features: dict[str, Path] = {}
    for fdir in feature_dirs(root):
        feature_id, loaded, found = load_feature(fdir, root)
        issues.extend(found)
        if feature_id is None:
            continue
        if feature_id in seen_features:
            issues.append(Issue(
                "error", str(fdir.relative_to(root)),
                f"{feature_id} is already used by {seen_features[feature_id].name}",
            ))
        seen_features.setdefault(feature_id, fdir)
        items.extend(loaded)
    return items, issues


def validate_repo(root: Path) -> Report:
    _, issues = load_config(root)
    items, found = load_repo(root)
    issues.extend(found)
    for feature_id in sorted({a.feature for a in items}):
        issues.extend(check_feature([a for a in items if a.feature == feature_id]))
    return Report(tuple(items), tuple(issues))


def refresh_statuses(root: Path) -> list[StatusChange]:
    """Write computed staleness into each artifact's status. Content,
    version and updated_at are left alone."""
    items, _ = load_repo(root)
    changes: list[StatusChange] = []
    for feature_id in sorted({a.feature for a in items}):
        group = [a for a in items if a.feature == feature_id]
        by_id = trace.index(group)
        for a in group:
            new = trace.expected_status(a, by_id)
            if new != a.status:
                art.save(replace(a, status=new))
                changes.append(StatusChange(a, a.status, new))
    return changes
