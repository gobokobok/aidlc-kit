"""Handoff: the one hard gate, and the package engineers pick up.

`/handoff` works in two passes. When everything in the feature is approved,
current and passing its evals, it builds the package (HND-xxx) and asks for it
to be accepted. Once the package itself is accepted, it merges and tags.
"""

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from aidlc import artifacts as art
from aidlc import reviewers, risk, trace
from aidlc.artifacts import Artifact, Issue, ParentRef
from aidlc.config import Config, Tier
from aidlc.evals import runner
from aidlc.review import join
from aidlc.workspace import Feature, render, sort_key, tier_requirements, used_ids

# What a feature must contain before it can be handed off.
REQUIRED_TYPES = ("risk", "discovery", "requirement", "criteria", "asset", "eval")
# Produced at or after handoff, so not part of what is handed off.
AFTER_HANDOFF = ("handoff", "decomposition")
TAG_FORMAT = "{feature}/handoff-v{n}"

COMMAND_FOR = {"risk": "/risk", "discovery": "/discover", "requirement": "/requirement",
               "criteria": "/criteria", "asset": "/asset", "eval": "/eval",
               "privacy_assessment": "/privacy"}


@dataclass(frozen=True)
class Blocker:
    item: str
    problem: str
    resolution: str  # who can resolve it, and how

    def __str__(self) -> str:
        return f"{self.item}: {self.problem}. {self.resolution}"


def content_items(items: list[Artifact]) -> list[Artifact]:
    return sorted((a for a in items if a.type not in AFTER_HANDOFF), key=sort_key)


def _approvers(config: Config, check: reviewers.RoleCheck) -> str:
    label = reviewers.role_label(check.role)
    if check.role == "any_reviewer":
        return "Anyone other than the author can approve it with /approve."
    if not check.candidates:
        return (f"Nobody has the {label} role in aidlc.yaml yet; whoever looks after that file "
                "must add someone.")
    return f"{join(list(check.candidates))} ({label}) can approve it with /approve."


def gate(
    config: Config,
    items: list[Artifact],
    eval_state: str,
    validation_errors: list[Issue] = (),
) -> list[Blocker]:
    """Everything that stops the feature's content from being handed off,
    each with who can resolve it. Empty means the content may be handed off."""
    blockers: list[Blocker] = []
    content = content_items(items)
    tier = risk.feature_tier(items, config)
    present = {a.type for a in content}
    owner = next((a.owner for a in content if a.type == "risk"), content[0].owner if content else "the PM")

    for i in validation_errors:
        blockers.append(Blocker(i.where, i.message, f"{owner} can fix it (see /status)."))

    for t in REQUIRED_TYPES:
        if t not in present:
            blockers.append(Blocker("Feature", f"there is no {t.replace('_', ' ')} yet",
                                    f"{owner} can add it with {COMMAND_FOR[t]}."))
    profile = next((a for a in content if a.type == "risk"), None)
    if profile is not None and tier is None:
        blockers.append(Blocker(profile.id, "the risk profile is incomplete, so there is no tier",
                                f"{profile.owner} can complete it with /risk."))
    if tier:
        for needed in tier.required_artifacts:
            if needed not in present:
                blockers.append(Blocker("Feature", f"{tier.display} needs a {needed.replace('_', ' ')}",
                                        f"{owner} can write it with {COMMAND_FOR.get(needed, '/status')}."))
        if tier.human_in_loop:
            for a in content:
                if a.type == "asset" and not str(a.extra.get("human_review_step") or "").strip():
                    blockers.append(Blocker(a.id, f"{tier.display} needs a person to check the AI output, "
                                                  "and no human review step is described",
                                            f"{a.owner} can add it with /change {a.id} --human-review-step."))

    for a in content:
        label = f"{a.id} v{a.version}"
        if a.status == "draft":
            blockers.append(Blocker(label, "is a draft that was never submitted",
                                    f"{a.owner} can send it for review with /submit."))
            continue
        if a.status == "stale":
            blockers.append(Blocker(label, "is out of date because something it builds on changed",
                                    f"{a.owner} can update it with /change {a.id}."))
            continue
        if a.status == "rejected":
            note = next((r for r in reversed(a.extra.get("rejections", [])) if r.get("version") == a.version), None)
            why = f" ({note['by']}: {note['reason']})" if note else ""
            blockers.append(Blocker(label, f"was rejected{why}",
                                    f"{a.owner} can revise it with /change {a.id}, then /submit."))
            continue
        for check in reviewers.pending(config, a, tier):
            extra = "" if check.reason == "routing" else f", which {config.tier(check.reason).display} adds"
            blockers.append(Blocker(label, f"still needs {reviewers.role_label(check.role)} approval{extra}",
                                    _approvers(config, check)))

    if "eval" in present:
        words = {"none": "there is no golden set", "missing": "the golden set has not been run",
                 "out_of_date": "the eval report is older than the current prompt, criteria or golden set",
                 "failing": "the evals fail (see evals/report.md)"}
        if eval_state in words:
            blockers.append(Blocker("Evals", words[eval_state], f"{owner} can run /eval."))

    return blockers


# --- the package -------------------------------------------------------------

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nest(body: str) -> str:
    """An artifact body as a subsection: drop its H1, push headings down two levels."""
    lines = [line for line in body.strip("\n").splitlines()]
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(("##" + line) if re.match(r"^#{1,4} ", line) else line for line in lines).strip("\n")


def trace_graph(content: list[Artifact]) -> dict[str, Any]:
    by_id = trace.index(content)

    def chains(start: str) -> list[list[str]]:
        node = by_id[start]
        ups = [p.id for p in node.parents if p.id in by_id]
        if not ups:
            return [[start]]
        return [[start, *rest] for up in ups for rest in chains(up)]

    return {
        "nodes": [{"id": a.id, "type": a.type, "version": a.version, "title": a.title, "status": a.status}
                  for a in content],
        "edges": [{"from": a.id, "to": p.id, "version": p.version} for a in content for p in a.parents],
        "chains": {a.id: chains(a.id) for a in content if a.type == "criteria"},
    }


def handoff_number(handoff_id: str) -> int:
    return int(handoff_id.split("-")[1])


def tag_name(feature_id: str, handoff_id: str) -> str:
    return TAG_FORMAT.format(feature=feature_id, n=handoff_number(handoff_id))


def open_handoff(items: list[Artifact], handed_off: set[str]) -> Artifact | None:
    """The latest handoff package not yet merged and tagged, if any."""
    pending = [a for a in items if a.type == "handoff" and a.id not in handed_off]
    return max(pending, key=lambda a: handoff_number(a.id)) if pending else None


def is_current(package: Artifact, items: list[Artifact]) -> bool:
    return {(p.id, p.version) for p in package.parents} == {(a.id, a.version) for a in content_items(items)}


def build(root: Path, config: Config, feature: Feature, items: list[Artifact], owner: str,
          now: datetime, commit: str, handed_off: set[str]) -> Artifact:
    """Write the package for the current, approved content. Reuses the open
    package (as a new version) or starts the next HND."""
    content = content_items(items)
    tier = risk.feature_tier(items, config)
    existing = open_handoff(items, handed_off)
    hnd_id = existing.id if existing else art.next_id("handoff", used_ids(root, feature, items))
    folder = feature.path / "handoff" / hnd_id
    if folder.exists():
        for child in folder.iterdir():
            if child.name != "handoff.md":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    folder.mkdir(parents=True, exist_ok=True)

    by_type = {t: [a for a in content if a.type == t] for t in art.TYPES}
    evals_dir = feature.path / "evals"
    report = runner.read_report(evals_dir) or {}

    # spec.md
    lines = [f"# {feature.title} ({feature.id}): specification", "",
             f"Handoff {hnd_id} · {tier.display if tier else 'no tier'} · {art.format_ts(now)}", ""]
    for d in by_type["discovery"]:
        lines += [f"## Why ({d.id} v{d.version})", "", _nest(d.body), ""]
    lines += ["## What", ""]
    for r in by_type["requirement"]:
        lines += [f"### {r.id} v{r.version}: {r.title}", "", _nest(r.body), ""]
    lines += ["## Done means", ""]
    for c in by_type["criteria"]:
        thresholds, _ = runner.effective_thresholds(c, config, tier)
        limits = "; ".join(f"{n.removeprefix('max_')} {'≤' if n.startswith('max_') else '≥'} "
                           f"{v}" for n, v in thresholds.items())
        traces = ", ".join(p.id for p in c.parents)
        lines += [f"### {c.id} v{c.version}: {c.title}", "", f"Traces to {traces}. Thresholds: {limits}.", "",
                  _nest(c.body), ""]
    lines += ["## Risk and controls", ""]
    lines += [f"- {line}" for line in (tier_requirements(tier) if tier else [])]
    for a in by_type["asset"]:
        if a.extra.get("human_review_step"):
            lines.append(f"- Human review ({a.id}): {a.extra['human_review_step']}")
    lines += ["", "## AI behaviour", ""]
    for a in by_type["asset"]:
        model = a.extra.get("model") or config.evals.get("model") or "not set"
        lines.append(f"- {a.id} v{a.version} {a.title} (model: {model}): see `assets/{a.id}.md`")
    verdict = "pass" if report.get("pass") else "fail"
    lines += ["", "## Evidence", "",
              f"- Evals: {verdict}, {report.get('golden', {}).get('cases', 0)} cases; see `eval-report.md` "
              "and `golden.yaml`. The golden set is the regression gate for the implementation.", ""]
    (folder / "spec.md").write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")

    # frozen copies
    for a in by_type["risk"]:
        shutil.copyfile(a.path, folder / "risk.md")
    if by_type["privacy_assessment"]:
        shutil.copyfile(by_type["privacy_assessment"][0].path, folder / "privacy_assessment.md")
    (folder / "assets").mkdir()
    for a in by_type["asset"]:
        shutil.copyfile(a.path, folder / "assets" / f"{a.id}.md")
    shutil.copyfile(evals_dir / runner.GOLDEN_FILE, folder / "golden.yaml")
    shutil.copyfile(evals_dir / runner.REPORT_MD, folder / "eval-report.md")
    (folder / "trace.json").write_text(json.dumps(trace_graph(content), indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")

    files = {p.relative_to(folder).as_posix(): _sha(p) for p in sorted(folder.rglob("*"))
             if p.is_file() and p.name not in ("handoff.md", "manifest.json")}
    version = existing.version + 1 if existing and art.has_been_reviewed(existing) else (
        existing.version if existing else 1)
    manifest = {
        "feature": feature.id, "title": feature.title, "handoff": {"id": hnd_id, "version": version},
        "tier": tier.name if tier else None, "generated_at": art.format_ts(now), "commit": commit,
        "items": [{"id": a.id, "type": a.type, "version": a.version, "owner": a.owner,
                   "approvers": sorted({ap.by for ap in a.approved_current}),
                   "file": a.path.relative_to(feature.path).as_posix(), "sha256": _sha(a.path)}
                  for a in content],
        "eval": {"pass": bool(report.get("pass")), "golden_sha256": report.get("golden", {}).get("sha256")},
        "files": files,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")

    parents = tuple(ParentRef(a.id, a.version) for a in content)
    summary = [f"{a.id} v{a.version}: {a.title} (approved by {join(sorted({ap.by for ap in a.approved_current}))})"
               for a in content]
    ctx = dict(tier=tier.display if tier else "no tier", items=summary, cases=report.get("golden", {}).get("cases", 0),
               tag=tag_name(feature.id, hnd_id))
    if existing is None:
        package = render("handoff", id=hnd_id, feature=feature.id, title=f"Handoff: {feature.title}", owner=owner,
                         now=now, parents=[{"id": p.id, "version": p.version} for p in parents],
                         extra={"tier": tier.name if tier else None}, **ctx)
        package = replace(package, path=folder / "handoff.md", status="in_review")
    else:
        body = render("handoff", id=hnd_id, feature=feature.id, title=existing.title, owner=existing.owner,
                      now=now, parents=[], extra={}, **ctx).body
        package = art.apply_edit(existing, now, parents=parents, body=body,
                                 extra={**existing.extra, "tier": tier.name if tier else None})
        package = replace(package, status="in_review")
    art.save(package)
    return package


def verify_bundle(folder: Path) -> list[str]:
    """Frozen files must still match the manifest."""
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        return ["the handoff package has no manifest.json"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["manifest.json is not valid JSON"]
    problems = []
    for rel, sha in manifest.get("files", {}).items():
        path = folder / rel
        if not path.is_file():
            problems.append(f"{rel} is missing from the handoff package")
        elif _sha(path) != sha:
            problems.append(f"{rel} was changed after the package was built; packages are frozen")
    return problems


def package_blockers(config: Config, package: Artifact, items: list[Artifact]) -> list[Blocker]:
    """What stops a built package from being merged."""
    label = f"{package.id} v{package.version}"
    if not is_current(package, items):
        return [Blocker(label, "no longer matches the feature (something changed after it was built)",
                        "Run /handoff again to rebuild it.")]
    if package.status == "rejected":
        return [Blocker(label, "was rejected", "Address the comments, then run /handoff again to rebuild it.")]
    tier: Tier | None = risk.feature_tier(items, config)
    return [Blocker(label, f"is waiting for {reviewers.role_label(c.role)} to accept it", _approvers(config, c))
            for c in reviewers.pending(config, package, tier)]


def handed_off_ids(feature_id: str, tags: list[str]) -> set[str]:
    """HND IDs that have been merged and tagged, from tags like FEAT-001/handoff-v1."""
    found = set()
    for tag in tags:
        m = re.fullmatch(re.escape(feature_id) + r"/handoff-v(\d+)", tag)
        if m:
            found.add(f"HND-{int(m.group(1)):03d}")
    return found


def next_step(config: Config, items: list[Artifact], handed_off: set[str]) -> str | None:
    """What follows once all content is approved and its evals pass."""
    open_package = open_handoff(items, handed_off)
    if open_package:
        if not is_current(open_package, items):
            return f"{open_package.id} no longer matches the feature: run /handoff to rebuild it."
        waiting = package_blockers(config, open_package, items)
        if waiting:
            who = join(sorted({b.resolution.split(" can ")[0] for b in waiting if " can " in b.resolution}))
            return (f"{open_package.id} is waiting for {who or 'its reviewers'} to accept it with /approve; "
                    "then run /handoff to merge and tag it.")
        return f"{open_package.id} is approved: run /handoff to merge and tag it."
    done = sorted((a for a in items if a.type == "handoff" and a.id in handed_off),
                  key=lambda a: handoff_number(a.id))
    if done:
        last = done[-1]
        if not is_current(last, items):
            return f"The feature changed since {last.id}: run /handoff to build a new package."
        if not any(a.type == "decomposition" and any(p.id == last.id for p in a.parents) for a in items):
            return f"Handed off as {last.id}. Next: an engineer runs /decompose to plan the build."
        return f"Handed off as {last.id} and planned. Engineering can start building from the plan."
    return None
