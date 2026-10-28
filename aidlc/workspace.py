"""Feature workspaces: create features and artifacts, edit and revise them.

File operations only. Git is the caller's job (cli.py drives gitops.py), so
everything here can be tested on a plain folder.
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import jinja2
import yaml

from aidlc import artifacts as art
from aidlc import audit, reviewers, risk, trace
from aidlc.artifacts import ALLOWED_PARENTS, Artifact, ArtifactError, ParentRef
from aidlc.config import Config, Tier, tier_rank
from aidlc.validate import FEATURE_FILE, FEATURES_DIR, StatusChange, load_feature, refresh_statuses

TEMPLATES = Path(__file__).parent / "templates"

# Order artifacts are normally written in, for summaries.
STAGES = ("risk", "discovery", "requirement", "criteria", "asset", "eval", "privacy_assessment",
          "handoff", "decomposition")

DEFAULT_TITLES = {"risk": "Risk profile", "privacy_assessment": "Privacy assessment"}


class WorkspaceError(ValueError):
    """Something the PM asked for cannot be done; the message says why."""


@dataclass(frozen=True)
class Feature:
    id: str
    title: str
    owner: str
    created_at: datetime
    path: Path


@dataclass(frozen=True)
class Edit:
    before: Artifact
    after: Artifact
    status_changes: list[StatusChange]
    downstream: list[str]


@dataclass(frozen=True)
class RiskRevision:
    before: Artifact
    after: Artifact
    tier_before: Tier
    tier_after: Tier        # governing tier after the revision
    computed: str
    reasons: list[str]


# --- features ------------------------------------------------------------

def slugify(title: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:limit].rstrip("-") or "feature"


def _feature_from_dir(path: Path) -> Feature | None:
    feature_id = art.feature_id_from_dir(path.name)
    if feature_id is None:
        return None
    meta_path = path / FEATURE_FILE
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    created = meta.get("created_at")
    return Feature(
        id=feature_id,
        title=str(meta.get("title") or path.name.removeprefix(feature_id).strip("-").replace("-", " ")),
        owner=str(meta.get("owner") or ""),
        created_at=created if isinstance(created, datetime) else datetime.min,
        path=path,
    )


def list_features(root: Path) -> list[Feature]:
    base = root / FEATURES_DIR
    if not base.is_dir():
        return []
    found = (_feature_from_dir(p) for p in sorted(base.iterdir()) if p.is_dir())
    return [f for f in found if f is not None]


def get_feature(root: Path, feature_id: str) -> Feature:
    for f in list_features(root):
        if f.id == feature_id:
            return f
    raise WorkspaceError(f"There is no feature {feature_id} here. Run /status to see your features.")


def next_feature_id(root: Path, branches: Iterable[str] = ()) -> str:
    """Next FEAT id, counting folders and feature branches (local or remote),
    so two PMs on different branches do not pick the same number."""
    used = [f.id for f in list_features(root)]
    used += [b.rsplit("/", 1)[-1] for b in branches]
    numbers = [int(m.group(1)) for u in used if (m := re.match(r"^FEAT-(\d+)$", u))]
    return f"FEAT-{max(numbers, default=0) + 1:03d}"


def write_feature_file(feature: Feature) -> Path:
    path = feature.path / FEATURE_FILE
    data = {"id": feature.id, "title": feature.title, "owner": feature.owner,
            "created_at": art.format_ts(feature.created_at)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def artifacts_of(root: Path, feature: Feature) -> list[Artifact]:
    """Every readable artifact in the feature (problems are validate's job)."""
    _, items, _ = load_feature(feature.path, root)
    return items


def find_artifact(items: list[Artifact], artifact_id: str) -> Artifact:
    for a in items:
        if a.id == artifact_id:
            return a
    raise WorkspaceError(f"There is no {artifact_id} in this feature.")


def used_ids(root: Path, feature: Feature, items: list[Artifact]) -> set[str]:
    """IDs in use now plus every ID the audit log has seen, so none is reused."""
    ids = {a.id for a in items}
    ids.update(e["id"] for e in audit.read_entries(root)
               if e.get("feature") == feature.id and isinstance(e.get("id"), str))
    return ids


# --- templates -----------------------------------------------------------

def _env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
        autoescape=False,
    )
    # JSON is valid YAML, and safely quotes any title a PM can type.
    env.filters["yaml"] = lambda v: json.dumps(v, ensure_ascii=False)
    return env


def render(a_type: str, **ctx: Any) -> Artifact:
    """Render a type's template (frontmatter + body) and parse it."""
    ctx.setdefault("extra", {})
    ctx.setdefault("type", a_type)
    if isinstance(ctx.get("now"), datetime):
        ctx["now"] = art.format_ts(ctx["now"])
    return art.parse(_env().get_template(f"{a_type}.md").render(**ctx))


def template_body(a_type: str) -> str:
    """The body skeleton for a type, to guide whoever drafts it."""
    if not (TEMPLATES / f"{a_type}.md").is_file() or a_type == "risk":
        raise WorkspaceError(f"There is no drafting template for {a_type}.")
    return render(a_type, id=f"{art.TYPES[a_type]}-001", feature="FEAT-001", title="Title",
                  owner="owner", parents=[], now=art.utc_now()).body.lstrip("\n")


# --- creating and editing artifacts --------------------------------------

def default_parents(items: list[Artifact], a_type: str) -> list[str]:
    """Sensible parents when the PM names none: the discovery for a
    requirement, every criterion for an asset, the single candidate otherwise."""
    allowed = ALLOWED_PARENTS[a_type]
    if a_type in ("asset", "privacy_assessment"):
        return [a.id for a in items if a.type in allowed]
    candidates = [a.id for a in items if a.type in allowed]
    return candidates if len(candidates) == 1 else []


def _resolve_parents(items: list[Artifact], a_type: str, parent_ids: list[str]) -> list[ParentRef]:
    by_id = trace.index(items)
    refs = []
    for pid in dict.fromkeys(parent_ids):
        parent = by_id.get(pid)
        if parent is None:
            raise WorkspaceError(f"There is no {pid} in this feature to link to.")
        if parent.type not in ALLOWED_PARENTS[a_type]:
            allowed = " or ".join(sorted(ALLOWED_PARENTS[a_type])) or "nothing"
            raise WorkspaceError(f"A {a_type} links to a {allowed}, not to {pid} (a {parent.type}).")
        refs.append(ParentRef(parent.id, parent.version))
    return refs


def create_artifact(
    root: Path,
    feature: Feature,
    a_type: str,
    title: str,
    owner: str,
    now: datetime,
    parent_ids: list[str] | None = None,
    body: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Artifact:
    items = artifacts_of(root, feature)
    if "{id}" not in art.LOCATIONS[a_type] and any(a.type == a_type for a in items):
        raise WorkspaceError(f"This feature already has a {a_type.replace('_', ' ')}; use /change to edit it.")
    if parent_ids is None:
        parent_ids = default_parents(items, a_type)
    if not parent_ids and ALLOWED_PARENTS[a_type]:
        options = ", ".join(a.id for a in items if a.type in ALLOWED_PARENTS[a_type])
        raise WorkspaceError(
            f"Which item does this {a_type} build on? Name one with --parent"
            + (f" (choose from {options})." if options else "; there is none yet."))
    refs = _resolve_parents(items, a_type, parent_ids)
    new_id = art.next_id(a_type, used_ids(root, feature, items))
    a = render(
        a_type, id=new_id, feature=feature.id, title=title.strip(), owner=owner, now=now,
        parents=[{"id": r.id, "version": r.version} for r in refs], extra=extra or {},
    )
    if body is not None and body.strip():
        a = replace(a, body="\n" + body.strip("\n") + "\n")
    a = replace(a, path=feature.path / art.relative_path(a_type, new_id))
    art.save(a)
    return a


def edit_artifact(
    root: Path,
    feature: Feature,
    artifact_id: str,
    now: datetime,
    title: str | None = None,
    body: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Edit:
    """Edit an artifact. Its parent links move to the parents' current
    versions (the edit is made in light of them), a reviewed version becomes a
    new version, and direct children of a new version become stale."""
    items = artifacts_of(root, feature)
    before = find_artifact(items, artifact_id)
    if before.type == "risk":
        raise WorkspaceError("The risk profile is changed with /risk, so the tier is worked out again.")
    by_id = trace.index(items)
    changes: dict[str, Any] = {
        "parents": tuple(ParentRef(p.id, by_id[p.id].version) if p.id in by_id else p
                         for p in before.parents),
    }
    if title is not None:
        changes["title"] = title.strip()
    if body is not None:
        changes["body"] = "\n" + body.strip("\n") + "\n"
    if extra:
        changes["extra"] = {**before.extra, **extra}
    after = art.apply_edit(before, now, **changes)
    art.save(after)
    return Edit(before, after, refresh_statuses(root), trace.downstream(artifact_id, trace.index(items)))


# --- risk ----------------------------------------------------------------

def tier_requirements(tier: Tier) -> list[str]:
    """What a tier asks for, in plain sentences."""
    lines = []
    if tier.extra_reviewers:
        roles = ", ".join(reviewers.role_label(r) for r in tier.extra_reviewers)
        lines.append(f"Every item also needs approval from: {roles}.")
    for needed in tier.required_artifacts:
        lines.append(f"A {needed.replace('_', ' ')} must be written and approved.")
    for name, floor in tier.min_thresholds.items():
        word = "at most" if name.startswith("max_") else "at least"
        lines.append(f"Criteria must set {name} to {word} {floor}.")
    if tier.human_in_loop:
        lines.append("A person must check the AI output before it takes effect.")
    return lines or ["Nothing beyond the normal reviews."]


def _risk_fields(answers: risk.Answers, rationale: str, declared: str,
                 approved_tier: str | None) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "data_classes": list(answers.data_classes),
        "autonomy": answers.autonomy,
        "audience": answers.audience,
        "regulated_decision": answers.regulated_decision,
        "declared_tier": declared,
        "rationale": rationale.strip(),
    }
    if approved_tier:
        fields["approved_tier"] = approved_tier
    return fields


def _declared_tier(computed: str, raise_to: str | None, config: Config) -> str:
    if raise_to is None:
        return computed
    if raise_to not in config.risk_tiers:
        raise WorkspaceError(f"{raise_to} is not a tier; choose from {', '.join(config.risk_tiers)}.")
    if tier_rank(raise_to) < tier_rank(computed):
        raise WorkspaceError(
            f"The answers make this {config.tier(computed).display}. You can raise the tier, "
            "but not set it lower than the answers give.")
    return raise_to


def _risk_body(profile: Artifact, config: Config) -> str:
    rendered = render(
        "risk", id=profile.id, feature=profile.feature, title=profile.title, owner=profile.owner,
        now=profile.updated_at, parents=[], extra={},
        summary=risk.describe(profile, config),
        requirements=tier_requirements(risk.effective_tier(profile, config)),
    )
    return rendered.body


def create_feature(
    root: Path,
    config: Config,
    title: str,
    owner: str,
    answers: risk.Answers,
    rationale: str,
    now: datetime,
    raise_to: str | None = None,
    branches: Iterable[str] = (),
) -> tuple[Feature, Artifact]:
    """Open a feature folder with feature.yaml and its risk profile (RISK-001)."""
    if not title.strip():
        raise WorkspaceError("Give the feature a short name.")
    problems = risk.check_answers(_risk_fields(answers, rationale, "T1", None))
    if problems:
        raise WorkspaceError("Some risk answers are missing or unclear: " + "; ".join(problems) + ".")
    _declared_tier(risk.compute_tier(answers)[0], raise_to, config)  # fail before writing anything
    feature_id = next_feature_id(root, branches)
    feature = Feature(feature_id, title.strip(), owner, now,
                      root / FEATURES_DIR / f"{feature_id}-{slugify(title)}")
    write_feature_file(feature)
    return feature, create_risk_profile(root, config, feature, owner, answers, rationale, now, raise_to)


def create_risk_profile(
    root: Path,
    config: Config,
    feature: Feature,
    owner: str,
    answers: risk.Answers,
    rationale: str,
    now: datetime,
    raise_to: str | None = None,
) -> Artifact:
    problems = risk.check_answers(_risk_fields(answers, rationale, "T1", None))
    if problems:
        raise WorkspaceError("Some risk answers are missing or unclear: " + "; ".join(problems) + ".")
    declared = _declared_tier(risk.compute_tier(answers)[0], raise_to, config)
    new_id = art.next_id("risk", used_ids(root, feature, artifacts_of(root, feature)))
    profile = render("risk", id=new_id, feature=feature.id, title=DEFAULT_TITLES["risk"],
                     owner=owner, now=now, parents=[], summary=[], requirements=[],
                     extra=_risk_fields(answers, rationale, declared, None))
    profile = replace(profile, path=feature.path / art.relative_path("risk", new_id))
    profile = replace(profile, body=_risk_body(profile, config))
    art.save(profile)
    return profile


def revise_risk(
    root: Path,
    config: Config,
    feature: Feature,
    now: datetime,
    answers: dict[str, Any],
    rationale: str | None = None,
    raise_to: str | None = None,
) -> RiskRevision:
    """Re-answer some questions. Unanswered ones keep their old values; an
    earlier raise is kept unless a new --tier is given."""
    items = artifacts_of(root, feature)
    profiles = [a for a in items if a.type == "risk"]
    if not profiles:
        raise WorkspaceError("This feature has no risk profile to revise.")
    before = profiles[0]
    merged = {**before.extra, **{k: v for k, v in answers.items() if v is not None}}
    problems = risk.check_answers(merged)
    if problems:
        raise WorkspaceError("Some risk answers are missing or unclear: " + "; ".join(problems) + ".")
    new_answers = risk.Answers(tuple(merged["data_classes"]), merged["autonomy"],
                               merged["audience"], merged["regulated_decision"])
    computed, reasons = risk.compute_tier(new_answers)
    if raise_to is None and not risk.check_answers(before.extra):
        # Keep an earlier deliberate raise (declared above what was computed).
        old = before.extra.get("declared_tier")
        old_computed, _ = risk.compute_tier(risk.answers_of(before))
        if old in config.risk_tiers and tier_rank(old) > tier_rank(old_computed):
            raise_to = old if tier_rank(old) > tier_rank(computed) else None
    declared = _declared_tier(computed, raise_to, config)
    tier_before = risk.effective_tier(before, config)
    fields = _risk_fields(new_answers, rationale if rationale is not None else str(merged.get("rationale", "")),
                          declared, before.extra.get("approved_tier"))
    after = art.apply_edit(before, now, extra={**before.extra, **fields})
    after = replace(after, body=_risk_body(after, config))
    art.save(after)
    return RiskRevision(before, after, tier_before, risk.effective_tier(after, config), computed, reasons)


# --- golden set ----------------------------------------------------------

@dataclass(frozen=True)
class GoldenSave:
    artifact: Artifact
    changed: bool
    cases: int


def save_golden(root: Path, feature: Feature, owner: str, now: datetime,
                text: str | None = None) -> GoldenSave:
    """Write golden.yaml (when `text` is given) and record it in the eval
    artifact: its hash, the criteria and assets it covers, a summary. A
    reviewed golden set that changes becomes a new version."""
    from aidlc.evals import runner  # local: evals depends on workspace-free modules only

    evals_dir = feature.path / "evals"
    golden = evals_dir / runner.GOLDEN_FILE
    items = artifacts_of(root, feature)
    criteria = {a.id for a in items if a.type == "criteria"}
    assets = sorted(a.id for a in items if a.type == "asset")
    if text is None:
        if not golden.is_file():
            raise WorkspaceError("There is no golden set yet; draft the cases first.")
        text = golden.read_text(encoding="utf-8")
    text = text.strip("\n") + "\n"
    cases, problems = runner.parse_golden(text, criteria, set(assets))
    if problems:
        more = f" (and {len(problems) - 5} more)" if len(problems) > 5 else ""
        raise WorkspaceError("The golden set needs fixing: " + "; ".join(problems[:5]) + more + ".")
    evals_dir.mkdir(parents=True, exist_ok=True)
    golden.write_text(text, encoding="utf-8")

    covered = sorted({c for case in cases for c in case.criteria})
    by_id = trace.index(items)
    parents = tuple(ParentRef(i, by_id[i].version) for i in covered + assets)
    per_criterion = [f"{cid}: {sum(cid in c.criteria for c in cases)} case(s)" for cid in covered]
    missing = sorted(criteria - set(covered))
    per_criterion += [f"{cid}: no cases yet" for cid in missing]
    tags = sorted({t for c in cases for t in c.tags})
    sha = runner.golden_sha(text)
    ctx = dict(cases=len(cases), per_criterion=per_criterion, tags=", ".join(tags) or "none")

    existing = next((a for a in items if a.type == "eval"), None)
    if existing is None:
        new_id = art.next_id("eval", used_ids(root, feature, items))
        a = render("eval", id=new_id, feature=feature.id, title="Golden set", owner=owner, now=now,
                   parents=[{"id": r.id, "version": r.version} for r in parents],
                   extra={"golden_sha256": sha}, **ctx)
        a = replace(a, path=feature.path / art.relative_path("eval", new_id))
        art.save(a)
        return GoldenSave(a, True, len(cases))
    if existing.extra.get("golden_sha256") == sha and existing.parents == parents:
        return GoldenSave(existing, False, len(cases))
    body = render("eval", id=existing.id, feature=feature.id, title=existing.title, owner=existing.owner,
                  now=now, parents=[], extra={}, **ctx).body
    after = art.apply_edit(existing, now, parents=parents, body=body,
                           extra={**existing.extra, "golden_sha256": sha})
    art.save(after)
    return GoldenSave(after, True, len(cases))


# --- hand edits ----------------------------------------------------------

def _content(a: Artifact) -> tuple:
    return (a.title, a.body, a.parents, {k: v for k, v in a.extra.items() if k != "approved_tier"})


def normalize_hand_edits(root: Path, changed: list[tuple[Path, str | None]], now: datetime) -> list[Artifact]:
    """A PM may edit artifact files directly in the IDE. If they changed a
    version that was already reviewed, turn the edit into a new version so the
    old approval cannot cover new content. `changed` holds (path, text at
    last commit or None for new files)."""
    bumped = []
    for path, old_text in changed:
        if old_text is None or not path.is_file() or path.suffix != ".md":
            continue
        try:
            old, new = art.parse(old_text), art.load(path)
        except ArtifactError:
            continue  # validate reports unreadable files
        if (new.id == old.id and new.version == old.version
                and art.has_been_reviewed(old) and _content(new) != _content(old)):
            fixed = art.apply_edit(replace(new, status=old.status, approvals=old.approvals), now)
            art.save(fixed)
            bumped.append(fixed)
    return bumped


# --- state ---------------------------------------------------------------

EVAL_STEPS = {
    "none": "Run /eval to build the golden set and test the prompt against the criteria.",
    "missing": "Run /eval: the golden set has not been run yet.",
    "out_of_date": "Run /eval: the prompt, criteria or golden set changed since the last run.",
    "failing": "Evals fail (see evals/report.md): improve the prompt or the cases, then /eval again.",
}


def next_step(items: list[Artifact], tier: Tier | None, config: Config,
              eval_state: str = "passing") -> str:
    """The one thing the PM should do next, in a sentence. `eval_state` is
    runner.report_state(...) for the feature."""
    present = {a.type for a in items}
    for a_type, command, what in (
        ("risk", "/risk", "answer the risk questions"),
        ("discovery", "/discover", "write the discovery brief"),
        ("requirement", "/requirement", "write the first requirement"),
        ("criteria", "/criteria", "make the requirements testable"),
        ("asset", "/asset", "define the AI behaviour"),
    ):
        if a_type not in present:
            return f"Run {command} to {what}."
    if tier:
        for needed in tier.required_artifacts:
            if needed not in present:
                return f"{tier.display} needs a {needed.replace('_', ' ')}: run /privacy."
    # A stale golden set is brought up to date by /eval itself.
    stale = [a.id for a in items if a.status == "stale" and a.type != "eval"]
    if stale:
        return f"Update {', '.join(stale)} with /change: something they build on has changed."
    if eval_state == "passing" and any(a.type == "eval" and a.status == "stale" for a in items):
        eval_state = "out_of_date"
    rejected = [a.id for a in items if a.status == "rejected"]
    if rejected:
        return f"Address the review comments on {', '.join(rejected)} with /change, then /submit."
    if eval_state in EVAL_STEPS:
        return EVAL_STEPS[eval_state]
    if any(a.status == "draft" for a in items):
        return "Run /submit to ask for a review."
    waiting = [a for a in items if a.status == "in_review"
               or (a.status == "approved" and not reviewers.roles_complete(config, a, tier))]
    if waiting:
        return "Waiting for reviewers; run /reviewers to see who still has to approve what."
    return "Everything is approved and the evals pass. Next: /handoff."


def sort_key(a: Artifact) -> tuple[int, str]:
    return (STAGES.index(a.type), a.id)
