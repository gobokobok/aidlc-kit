"""What the viewer shows, worked out from the repository.

Pure data: nothing here writes files or calls Git. The caller passes the
handoff tags it found, so the model can be built from a plain folder.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aidlc import audit, decompose, handoff, reviewers, workspace
from aidlc.artifacts import Artifact
from aidlc.config import Config, Tier, load_config
from aidlc.evals import runner
from aidlc.risk import feature_tier
from aidlc.validate import validate_repo

TYPE_LABELS = {
    "risk": "Risk profile", "discovery": "Discovery", "requirement": "Requirement", "criteria": "Criteria",
    "asset": "Prompt", "eval": "Golden set", "privacy_assessment": "Privacy assessment",
    "handoff": "Handoff package", "decomposition": "Technical plan",
}
EVAL_WORDS = {
    "none": "No golden set yet", "missing": "Not run yet", "out_of_date": "Out of date",
    "failing": "Failing", "passing": "Passing",
}


@dataclass(frozen=True)
class RoleView:
    label: str
    satisfied: bool
    people: tuple[str, ...]  # who approved, or who could
    added_by: str | None     # tier name when the tier added this role


@dataclass(frozen=True)
class ArtifactView:
    id: str
    type: str
    type_label: str
    title: str
    version: int
    status: str
    owner: str
    updated: str
    approvals: tuple[tuple[str, str], ...]
    roles: tuple[RoleView, ...]
    path: str
    note: str = ""


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    state: str   # done | active | todo | failed
    detail: str


@dataclass(frozen=True)
class Blocker:
    where: str
    problem: str
    who: str


@dataclass(frozen=True)
class FeatureView:
    id: str
    title: str
    owner: str
    tier: str | None           # "T2"
    tier_text: str             # "Tier 2 (Medium)" or "No tier yet"
    stages: tuple[Stage, ...]
    blockers: tuple[Blocker, ...]
    next_step: str
    handed_off: tuple[str, ...]
    artifacts: tuple[ArtifactView, ...]
    risk_facts: tuple[tuple[str, str], ...]
    eval_state: str
    eval_text: str
    report: dict[str, Any] | None
    graph: dict[str, Any]
    chains: tuple[tuple[str, ...], ...]
    audit: tuple[dict[str, Any], ...]
    problems: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Site:
    name: str
    generated_at: str
    commit: str | None
    source_url: str | None
    features: tuple[FeatureView, ...]
    audit: tuple[dict[str, Any], ...]


def stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC")


def stage_state(items: list[Artifact], approved_ok: set[str]) -> tuple[str, str]:
    """done / active / todo for a group of artifacts."""
    if not items:
        return "todo", "not started"
    if all(a.status == "approved" and a.id in approved_ok for a in items):
        return "done", f"{len(items)} approved" if len(items) > 1 else "approved"
    states = sorted({a.status for a in items} - {"approved"})
    if any(a.status in ("rejected", "stale") for a in items):
        bad = [a.status for a in items if a.status in ("rejected", "stale")][0]
        return "active", bad
    return "active", ", ".join(s.replace("_", " ") for s in states) or "waiting for reviewers"


def stages_of(items: list[Artifact], tier: Tier | None, config: Config, eval_state: str,
              handed: set[str]) -> tuple[Stage, ...]:
    complete = {a.id for a in items if reviewers.roles_complete(config, a, tier)}
    out: list[Stage] = []
    for key, label, types in (("risk", "Risk", ("risk",)), ("discovery", "Discovery", ("discovery",)),
                              ("requirement", "Requirements", ("requirement",)),
                              ("criteria", "Criteria", ("criteria",)),
                              ("asset", "Prompt", ("asset",))):
        state, detail = stage_state([a for a in items if a.type in types], complete)
        out.append(Stage(key, label, state, detail))
    if tier and "privacy_assessment" in tier.required_artifacts or any(a.type == "privacy_assessment" for a in items):
        state, detail = stage_state([a for a in items if a.type == "privacy_assessment"], complete)
        out.append(Stage("privacy", "Privacy", state, detail))
    if eval_state == "passing":
        out.append(Stage("eval", "Evals", "done", "passing"))
    elif eval_state == "failing":
        out.append(Stage("eval", "Evals", "failed", "failing"))
    elif eval_state == "none":
        out.append(Stage("eval", "Evals", "todo", "not started"))
    else:
        out.append(Stage("eval", "Evals", "active", EVAL_WORDS[eval_state].lower()))
    package = [a for a in items if a.type == "handoff"]
    if handed:
        out.append(Stage("handoff", "Handoff", "done", ", ".join(sorted(handed))))
    elif package:
        out.append(Stage("handoff", "Handoff", "active", package[-1].status.replace("_", " ")))
    else:
        out.append(Stage("handoff", "Handoff", "todo", "not started"))
    state, detail = stage_state([a for a in items if a.type == "decomposition"], complete)
    out.append(Stage("plan", "Plan", state, detail))
    return tuple(out)


def role_views(config: Config, a: Artifact, tier: Tier | None) -> tuple[RoleView, ...]:
    return tuple(
        RoleView(reviewers.role_label(c.role), c.satisfied, c.approved_by or c.candidates,
                 None if c.reason == "routing" else c.reason)
        for c in reviewers.role_checks(config, a, tier))


def relative(a: Artifact, root: Path) -> str:
    return a.path.relative_to(root).as_posix() if a.path else ""


def artifact_view(a: Artifact, config: Config, tier: Tier | None, root: Path) -> ArtifactView:
    rejection = next((r for r in reversed(a.extra.get("rejections", [])) if r.get("version") == a.version), None)
    return ArtifactView(
        id=a.id, type=a.type, type_label=TYPE_LABELS.get(a.type, a.type), title=a.title, version=a.version,
        status=a.status, owner=a.owner, updated=stamp(a.updated_at),
        approvals=tuple((ap.by, stamp(ap.at)) for ap in a.approved_current),
        roles=role_views(config, a, tier),
        path=relative(a, root),
        note=f"rejected by {rejection['by']}: {rejection['reason']}" if rejection else "")


def risk_facts(items: list[Artifact]) -> tuple[tuple[str, str], ...]:
    profile = next((a for a in items if a.type == "risk"), None)
    if profile is None:
        return ()
    x = profile.extra
    rows = [
        ("Data", ", ".join(x.get("data_classes", [])) or "none"),
        ("AI output", str(x.get("autonomy", "")).replace("_", " ")),
        ("Audience", str(x.get("audience", "")).replace("_", " ")),
        ("Regulated decision", "yes" if x.get("regulated_decision") else "no"),
    ]
    if x.get("rationale"):
        rows.append(("Why", str(x["rationale"])))
    return tuple(rows)


def feature_view(root: Path, config: Config, feature: workspace.Feature, items: list[Artifact],
                 tags: list[str], entries: list[dict[str, Any]], problems: list[str]) -> FeatureView:
    from aidlc.site.graph import layout

    items = sorted(items, key=workspace.sort_key)
    tier = feature_tier(items, config)
    evals_dir = feature.path / "evals"
    eval_state = runner.report_state(evals_dir, items, tier)
    handed = handoff.handed_off_ids(feature.id, tags)
    blockers: list[Blocker] = []
    if not handed:
        blockers = [Blocker(b.item, b.problem, b.resolution)
                    for b in handoff.gate(config, items, eval_state)]
    plan = next((a for a in items if a.type == "decomposition"), None)
    tasks = decompose.parse_tasks(plan.body)[0] if plan else []
    content = handoff.content_items(items)
    graph = layout(content, tasks)
    chains = handoff.trace_graph(content)["chains"]
    return FeatureView(
        id=feature.id, title=feature.title, owner=feature.owner,
        tier=tier.name if tier else None, tier_text=tier.display if tier else "No tier yet",
        stages=stages_of(items, tier, config, eval_state, handed),
        blockers=tuple(blockers),
        next_step=handoff.next_step(config, items, handed) or workspace.next_step(items, tier, config, eval_state),
        handed_off=tuple(sorted(handed)),
        artifacts=tuple(artifact_view(a, config, tier, root) for a in items),
        risk_facts=risk_facts(items),
        eval_state=eval_state, eval_text=EVAL_WORDS[eval_state],
        report=runner.read_report(evals_dir),
        graph=graph,
        chains=tuple(tuple(c) for cs in chains.values() for c in cs),
        audit=tuple(sorted((e for e in entries if e.get("feature") == feature.id),
                           key=lambda e: (e.get("at", ""), e.get("id", "")), reverse=True)),
        problems=tuple(problems),
    )


def build_site(root: Path, tags: list[str], now: datetime, commit: str | None = None,
               source_url: str | None = None) -> Site:
    config, _ = load_config(root)
    report = validate_repo(root)
    entries = audit.read_entries(root)
    views = []
    for feature in workspace.list_features(root):
        items = [a for a in report.artifacts if a.feature == feature.id]
        problems = [f"{i.where}: {i.message}" for i in report.issues
                    if i.severity == "error" and (i.where.startswith(f"features/{feature.path.name}")
                                                  or i.where.startswith(feature.id))]
        views.append(feature_view(root, config, feature, items, tags, entries, problems))
    return Site(
        name=config.display_name, generated_at=stamp(now), commit=commit, source_url=source_url,
        features=tuple(views),
        audit=tuple(sorted(entries, key=lambda e: (e.get("at", ""), e.get("id", "")), reverse=True)),
    )
