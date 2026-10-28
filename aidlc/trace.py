"""Trace graph: parent links, staleness and downstream impact.

All functions work on the artifacts of a single feature, indexed by ID.
"""

from collections.abc import Iterable

from aidlc.artifacts import Artifact, ParentRef


def index(artifacts: Iterable[Artifact]) -> dict[str, Artifact]:
    """Index one feature's artifacts by ID. Later duplicates are ignored;
    the validator reports them."""
    by_id: dict[str, Artifact] = {}
    for a in artifacts:
        by_id.setdefault(a.id, a)
    return by_id


def stale_parents(a: Artifact, by_id: dict[str, Artifact]) -> list[tuple[ParentRef, int]]:
    """Parents that have moved on since `a` was written against them,
    as (recorded ref, current version). Missing parents are ignored here."""
    out = []
    for ref in a.parents:
        parent = by_id.get(ref.id)
        if parent is not None and parent.version > ref.version:
            out.append((ref, parent.version))
    return out


def is_stale(a: Artifact, by_id: dict[str, Artifact]) -> bool:
    return bool(stale_parents(a, by_id))


def expected_status(a: Artifact, by_id: dict[str, Artifact]) -> str:
    """The status the validator should write. Staleness is computed, never
    hand-set: a stale artifact that has caught up drops back to draft,
    because it changed and needs a fresh review."""
    if is_stale(a, by_id):
        return "stale"
    if a.status == "stale":
        return "draft"
    return a.status


def children(by_id: dict[str, Artifact]) -> dict[str, list[str]]:
    """Map of artifact ID -> IDs that list it as a parent, sorted."""
    out: dict[str, list[str]] = {i: [] for i in by_id}
    for a in by_id.values():
        for ref in a.parents:
            out.setdefault(ref.id, []).append(a.id)
    return {k: sorted(v) for k, v in out.items()}


def downstream(artifact_id: str, by_id: dict[str, Artifact]) -> list[str]:
    """Every artifact that depends on `artifact_id`, directly or not."""
    kids = children(by_id)
    seen: set[str] = set()
    stack = list(kids.get(artifact_id, []))
    while stack:
        current = stack.pop()
        if current not in seen:
            seen.add(current)
            stack.extend(kids.get(current, []))
    return sorted(seen)
