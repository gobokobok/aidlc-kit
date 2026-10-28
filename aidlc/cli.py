"""Command-line entry point: `aidlc <command>`.

Every command ends with one or two plain sentences: what happened and what
to do next. Git output is never shown unless `--verbose` is given. The chat
commands that `aidlc init` writes for each assistant are thin wrappers over
these commands.
"""

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from aidlc import artifacts as art
from aidlc import assistants, audit, blocks, ci, review, reviewers, risk, workspace
from aidlc.artifacts import Artifact, ArtifactError
from aidlc.config import CONFIG_FILE, Config, find_root, load_config, parse_config
from aidlc.evals import model as eval_model
from aidlc.evals import runner
from aidlc.gitops import MAIN_BRANCH, GitError, GitOps, commit_message, feature_branch
from aidlc.validate import load_feature, refresh_statuses, validate_repo
from aidlc.workspace import Feature, WorkspaceError

CREATE_COMMANDS = {
    "discover": "discovery",
    "requirement": "requirement",
    "criteria": "criteria",
    "asset": "asset",
    "privacy": "privacy_assessment",
}


@dataclass
class Ctx:
    root: Path
    config: Config
    ops: GitOps
    now: datetime
    out: TextIO
    stdin: TextIO

    def say(self, text: str = "") -> None:
        print(text, file=self.out)


# --- shared steps --------------------------------------------------------

def prepare(ctx: Ctx, feature_id: str | None = None) -> None:
    """Before any operation: save pending work, then pull with rebase."""
    if not ctx.ops.is_repo():
        raise GitError("This folder is not a Git repository yet. Ask an engineer to set up "
                       "the kit once (see README), then try again.")
    changed = ctx.ops.changed_paths()
    if changed:
        pairs = [(ctx.root / p, ctx.ops.file_at_head(p)) for p in changed if p.startswith("features/")]
        for a in workspace.normalize_hand_edits(ctx.root, pairs, ctx.now):
            ctx.say(f"You edited {a.id} directly after it was reviewed, so it is now v{a.version} "
                    "and needs review again.")
        refresh_statuses(ctx.root)
        ctx.ops.commit_all(commit_message(feature_id or "AIDLC", "Save work in progress"))
    ctx.ops.pull_rebase()


def resolve_feature(ctx: Ctx, explicit: str | None) -> Feature:
    if explicit:
        return workspace.get_feature(ctx.root, explicit)
    branch = ctx.ops.current_branch() if ctx.ops.is_repo() else ""
    if branch.startswith("feat/"):
        return workspace.get_feature(ctx.root, branch.removeprefix("feat/"))
    features = workspace.list_features(ctx.root)
    if len(features) == 1:
        return features[0]
    if not features:
        raise WorkspaceError("There is no feature yet. Start one with /new-feature.")
    names = ", ".join(f"{f.id} ({f.title})" for f in features)
    raise WorkspaceError(f"Which feature do you mean? Name one with --feature: {names}.")


def open_feature(ctx: Ctx, explicit: str | None) -> Feature:
    """Resolve the feature, save pending work and make sure we are on its branch."""
    feature = resolve_feature(ctx, explicit)
    prepare(ctx, feature.id)
    branch = feature_branch(feature.id)
    if ctx.ops.current_branch() != branch:
        if ctx.ops.branch_exists(branch):
            ctx.ops.switch(branch)
        else:
            ctx.ops.create_branch(branch, MAIN_BRANCH)
        ctx.ops.pull_rebase()
        feature = workspace.get_feature(ctx.root, feature.id)
    return feature


def current_user(ctx: Ctx, explicit: str | None = None) -> str:
    user = explicit or ctx.ops.github_user()
    if not art.USERNAME_RE.match(user):
        raise WorkspaceError(f"{user!r} is not a GitHub username.")
    return user


def read_body(ctx: Ctx, source: str | None) -> str | None:
    if source is None:
        return None
    if source == "-":
        return ctx.stdin.read()
    path = Path(source)
    if not path.is_file():
        raise WorkspaceError(f"I could not find the draft text file {source}.")
    return path.read_text(encoding="utf-8")


def parse_value(text: str) -> int | float:
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            raise WorkspaceError(f"{text!r} is not a number.") from None


def parse_thresholds(pairs: list[str] | None) -> dict[str, int | float] | None:
    if not pairs:
        return None
    out = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep:
            raise WorkspaceError(f"Write thresholds as name=value, like accuracy=0.9 (got {pair!r}).")
        out[name.strip()] = parse_value(value.strip())
    problems = art.check_thresholds(out, "thresholds")
    if problems:
        raise WorkspaceError(problems[0].message[0].upper() + problems[0].message[1:] + ".")
    return out


def tier_of(ctx: Ctx, items: list[Artifact]):
    return risk.feature_tier(items, ctx.config)


def save_commit(ctx: Ctx, feature: Feature, a: Artifact, summary: str) -> None:
    ctx.ops.commit(["features"], commit_message(feature.id, summary, a.id, a.version))


def to_answers(raw: dict[str, Any]) -> risk.Answers:
    return risk.Answers(tuple(raw["data_classes"]), raw["autonomy"], raw["audience"],
                        raw["regulated_decision"])


def feature_problems(ctx: Ctx, feature: Feature) -> list:
    return [i for i in validate_repo(ctx.root).errors
            if i.where.startswith(feature.id) or feature.path.name in i.where]


# --- risk answers --------------------------------------------------------

ANSWER_FLAGS = ("data_classes", "autonomy", "audience", "regulated_decision")


def parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in ("yes", "y", "true", "1"):
        return True
    if lowered in ("no", "n", "false", "0"):
        return False
    raise WorkspaceError(f"Answer yes or no (got {text!r}).")


def answers_from_args(args: argparse.Namespace) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if args.data_classes:
        out["data_classes"] = [c.strip() for c in args.data_classes.split(",") if c.strip()]
    if args.autonomy:
        out["autonomy"] = args.autonomy
    if args.audience:
        out["audience"] = args.audience
    if args.regulated_decision is not None:
        out["regulated_decision"] = parse_bool(args.regulated_decision)
    return out


def ask(ctx: Ctx, q: risk.Question) -> Any:
    ctx.say(q.text)
    for i, o in enumerate(q.options, 1):
        ctx.say(f"  {i}. {o.text}")
    hint = "numbers separated by commas" if q.multiple else "a number"
    while True:
        print(f"Your answer ({hint}): ", end="", file=ctx.out, flush=True)
        raw = ctx.stdin.readline()
        if not raw:
            raise WorkspaceError("The questionnaire was not finished.")
        try:
            picks = [q.options[int(x) - 1].value for x in raw.replace(" ", "").split(",") if x]
        except (ValueError, IndexError):
            continue
        if picks and (q.multiple or len(picks) == 1):
            return picks if q.multiple else picks[0]


def complete_answers(ctx: Ctx, given: dict[str, Any]) -> dict[str, Any]:
    """Ask for missing answers at a terminal; otherwise say what is missing."""
    missing = [q for q in risk.QUESTIONS if q.key not in given]
    if not missing:
        return given
    if not ctx.stdin.isatty():
        flags = ", ".join("--" + q.key.replace("_", "-") for q in missing)
        raise WorkspaceError(f"The risk questionnaire is incomplete: answer {flags} "
                             "(see `aidlc risk-questions`).")
    for q in missing:
        given[q.key] = ask(ctx, q)
    return given


def tier_line(config: Config, computed: str, reasons: list[str]) -> str:
    return f"{config.tier(computed).display} because {review.join(reasons)}"


# --- commands ------------------------------------------------------------

def cmd_validate(ctx: Ctx, args: argparse.Namespace) -> int:
    if args.write:
        for change in refresh_statuses(ctx.root):
            a = change.artifact
            ctx.say(f"Marked {a.feature}/{a.id} as {change.new} (was {change.old}).")
    report = validate_repo(ctx.root)
    for issue in report.errors + report.warnings:
        ctx.say(f"  {'✗' if issue.severity == 'error' else '!'} {issue.where}: {issue.message}")
    n = len(report.artifacts)
    if report.ok:
        extra = f", with {len(report.warnings)} warning(s)" if report.warnings else ""
        ctx.say(f"All {n} artifact(s) are valid{extra}.")
        return 0
    ctx.say(f"Found {len(report.errors)} problem(s) across {n} artifact(s). Fix them and run validate again.")
    return 1


def cmd_new_feature(ctx: Ctx, args: argparse.Namespace) -> int:
    owner = current_user(ctx, args.owner)
    answers = complete_answers(ctx, answers_from_args(args))
    prepare(ctx)
    if ctx.ops.current_branch() != MAIN_BRANCH:
        ctx.ops.switch(MAIN_BRANCH)
        ctx.ops.pull_rebase()
    rationale = args.rationale or ""
    feature, profile = workspace.create_feature(
        ctx.root, ctx.config, args.title, owner,
        to_answers(answers), rationale, ctx.now, raise_to=args.tier, branches=ctx.ops.feature_branches(),
    )
    ctx.ops.create_branch(feature_branch(feature.id), MAIN_BRANCH)
    tier = risk.effective_tier(profile, ctx.config)
    ctx.ops.commit(["features"], commit_message(
        feature.id, f'Open feature "{feature.title}" with risk profile ({tier.name})',
        profile.id, profile.version))
    computed, reasons = risk.compute_tier(risk.answers_of(profile))
    why = tier_line(ctx.config, computed, reasons)
    if tier.name != computed:
        why += f", raised by you to {tier.display}"
    checkers = review.join([f"{p} ({reviewers.role_label(c.role)})"
                            for c in reviewers.role_checks(ctx.config, profile, tier)
                            for p in c.candidates]) or "a reviewer"
    ctx.say(f"Opened {feature.id} {feature.title}. It is {why}, so {checkers} will check the risk "
            f"profile. Next: run /discover with your notes.")
    if not rationale.strip():
        ctx.say("Tip: add a one-line rationale for the risk answers with /risk --rationale.")
    return 0


def cmd_create(ctx: Ctx, args: argparse.Namespace) -> int:
    a_type = CREATE_COMMANDS[args.command]
    feature = open_feature(ctx, args.feature)
    items = workspace.artifacts_of(ctx.root, feature)
    body = read_body(ctx, args.body_file)
    extra = create_extra(args)
    existing = next((a for a in items if a.type == a_type), None)
    if "{id}" not in art.LOCATIONS[a_type] and existing:
        return finish_edit(ctx, feature, workspace.edit_artifact(
            ctx.root, feature, existing.id, ctx.now, title=args.title, body=body, extra=extra),
            args.summary)
    if not args.title:
        raise WorkspaceError(f"Give the {a_type.replace('_', ' ')} a short title with --title.")
    owner = current_user(ctx)
    a = workspace.create_artifact(ctx.root, feature, a_type, args.title, owner, ctx.now,
                                  parent_ids=args.parent or None, body=body, extra=extra)
    save_commit(ctx, feature, a, args.summary or f"Add {a_type.replace('_', ' ')}: {a.title}")
    links = f", linked to {review.join([p.id for p in a.parents])}" if a.parents else ""
    ctx.say(f"Saved {a.id} \"{a.title}\" as a draft{links}. {NEXT_AFTER_CREATE[a_type]}")
    return 0


NEXT_AFTER_CREATE = {
    "discovery": "Next: run /requirement to say what the system must do.",
    "requirement": "Add more with /requirement, or run /criteria to make it testable.",
    "criteria": "Add more with /criteria, or run /asset to define the AI behaviour.",
    "asset": "Next: run /eval to test it against the criteria.",
    "privacy_assessment": "Next: run /submit so the reviewers can check it.",
}


def create_extra(args: argparse.Namespace) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    thresholds = parse_thresholds(getattr(args, "threshold", None))
    if thresholds:
        extra["thresholds"] = thresholds
    if getattr(args, "human_review_step", None):
        extra["human_review_step"] = args.human_review_step.strip()
    if getattr(args, "set_model", None):
        extra["model"] = args.set_model.strip()
    return extra


def finish_edit(ctx: Ctx, feature: Feature, edit: workspace.Edit, summary: str | None) -> int:
    a = edit.after
    save_commit(ctx, feature, a, summary or f"Update {a.type.replace('_', ' ')}: {a.title}")
    if a.version != edit.before.version:
        first = f"{a.id} is now v{a.version} and needs review again."
    else:
        first = f"Updated {a.id} (still v{a.version}, not yet reviewed)."
    stale = [c.artifact.id for c in edit.status_changes if c.new == "stale"]
    if stale:
        verb = "is" if len(stale) == 1 else "are"
        first += f" {review.join(stale)} {verb} now out of date; update with /change."
    elif edit.downstream and a.version != edit.before.version:
        first += f" Items that build on it: {review.join(edit.downstream)}."
    ctx.say(first)
    return 0


def cmd_change(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = open_feature(ctx, args.feature)
    body = read_body(ctx, args.body_file)
    extra = create_extra(args)
    # With no new content, this still moves parent links to their current
    # versions: the way to bring a stale item up to date.
    edit = workspace.edit_artifact(ctx.root, feature, args.id, ctx.now,
                                   title=args.title, body=body, extra=extra or None)
    return finish_edit(ctx, feature, edit, args.summary)


def cmd_risk(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = open_feature(ctx, args.feature)
    profile = next((a for a in workspace.artifacts_of(ctx.root, feature) if a.type == "risk"), None)
    given = answers_from_args(args)

    if profile is None:
        answers = complete_answers(ctx, given)
        profile = workspace.create_risk_profile(
            ctx.root, ctx.config, feature, current_user(ctx), to_answers(answers),
            args.rationale or "", ctx.now, raise_to=args.tier)
        save_commit(ctx, feature, profile, "Add risk profile")
        computed, reasons = risk.compute_tier(risk.answers_of(profile))
        ctx.say(f"Saved {profile.id}: {tier_line(ctx.config, computed, reasons)}. "
                "Next: run /submit so the risk reviewer can check the answers.")
        return 0

    if not given and args.tier is None and args.rationale is None:
        ctx.say(f"{feature.id} is {risk.effective_tier(profile, ctx.config).display}.")
        for line in risk.describe(profile, ctx.config):
            ctx.say(line)
        ctx.say("To revise, give new answers (see `aidlc risk-questions`) or raise the tier with --tier.")
        return 0

    rev = workspace.revise_risk(ctx.root, ctx.config, feature, ctx.now, given,
                                rationale=args.rationale, raise_to=args.tier)
    after, before = rev.after, rev.before
    summary = (f"Revise risk profile: {rev.tier_before.name} -> {rev.tier_after.name}"
               if rev.tier_before.name != rev.tier_after.name else "Revise risk profile")
    save_commit(ctx, feature, after, summary)
    declared = ctx.config.tier(after.extra["declared_tier"])
    head = f"{after.id} is now v{after.version}." if after.version != before.version else f"Updated {after.id}."
    ctx.say(f"{head} The answers make it {tier_line(ctx.config, rev.computed, rev.reasons)}"
            + (f"; you raised it to {declared.display}." if declared.name != rev.computed else "."))
    if declared.rank < rev.tier_before.rank:
        risk_people = review.join(list(reviewers.holders(ctx.config, "risk_reviewer", after.owner))) or "the risk reviewer"
        ctx.say(f"Lowering from {rev.tier_before.display} only takes effect once {risk_people} approves "
                f"this version; until then {rev.tier_after.display} rules apply.")
    elif rev.tier_after.rank > rev.tier_before.rank:
        ctx.say(f"The tier rose from {rev.tier_before.display} to {rev.tier_after.display}: "
                + " ".join(workspace.tier_requirements(rev.tier_after))
                + " Earlier approvals stay, but handoff waits until these are met.")
    ctx.say("Next: run /submit so the risk reviewer can check the new answers.")
    return 0


def cmd_risk_questions(ctx: Ctx, args: argparse.Namespace) -> int:
    if args.json:
        ctx.say(json.dumps([
            {"key": q.key, "flag": "--" + q.key.replace("_", "-"), "question": q.text,
             "multiple": q.multiple,
             "options": [{"value": o.value, "text": o.text} for o in q.options]}
            for q in risk.QUESTIONS], indent=2))
        return 0
    for q in risk.QUESTIONS:
        ctx.say(f"{q.text}  (--{q.key.replace('_', '-')})")
        for o in q.options:
            value = ("yes" if o.value else "no") if isinstance(o.value, bool) else o.value
            ctx.say(f"  {value}: {o.text}")
    return 0


def cmd_template(ctx: Ctx, args: argparse.Namespace) -> int:
    a_type = CREATE_COMMANDS.get(args.type, args.type)
    ctx.say(workspace.template_body(a_type).rstrip())
    return 0


def describe_check(c: reviewers.RoleCheck, config: Config) -> str:
    label = reviewers.role_label(c.role)
    why = "" if c.reason == "routing" else f", {config.tier(c.reason).display}"
    if c.satisfied:
        return f"✓ {label} ({', '.join(c.approved_by)})"
    if c.role == "any_reviewer":
        return "… anyone other than the author"
    who = ", ".join(c.candidates) if c.candidates else "nobody has this role in aidlc.yaml"
    return f"… {label}{why}: {who}"


def look_at_feature(ctx: Ctx, explicit: str | None) -> Feature:
    """For read-mostly commands: open the feature and record any approvals
    given on GitHub. Works without Git too (read only)."""
    if not ctx.ops.is_repo():
        return resolve_feature(ctx, explicit)
    feature = open_feature(ctx, explicit)
    sync_reviews(ctx, feature)
    return feature


def version_at(ctx: Ctx) -> review.VersionAt:
    cache: dict[tuple[str, str], int | None] = {}

    def lookup(commit: str, a: Artifact) -> int | None:
        rel = a.path.resolve().relative_to(ctx.root.resolve()).as_posix() if a.path else ""
        if (commit, rel) not in cache:
            text = ctx.ops.file_at(commit, rel) if commit and rel else None
            try:
                cache[commit, rel] = art.parse(text).version if text else None
            except ArtifactError:
                cache[commit, rel] = None
        return cache[commit, rel]
    return lookup


def sync_reviews(ctx: Ctx, feature: Feature) -> None:
    """Record approvals given on the GitHub screen into the files."""
    if not ctx.ops.has_remote():
        return
    try:
        pr = ctx.ops.pr_for_branch(feature_branch(feature.id))
        if pr is None or pr.state != "OPEN":
            return
        reviews = ctx.ops.pr_reviews(pr.number)
    except GitError:
        ctx.say("(I could not check GitHub for new reviews just now.)")
        return
    items = workspace.artifacts_of(ctx.root, feature)
    recorded = review.sync_github_reviews(ctx.config, items, reviews, version_at(ctx), ctx.now)
    if recorded:
        by_person: dict[str, list[str]] = {}
        for a, login in recorded:
            by_person.setdefault(login, []).append(a.id)
        summary = "; ".join(f"{login} for {review.join(ids)}" for login, ids in by_person.items())
        ctx.ops.commit(["features"], commit_message(feature.id, f"Record GitHub approvals: {summary}"))
        ctx.ops.push()
        ctx.say(f"Recorded approvals given on GitHub: {summary}.")
    for r in review.changes_requested(reviews):
        ctx.say(f"{r.login} asked for changes on GitHub: {r.body.strip() or '(no comment)'}")


def cmd_reviewers(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = look_at_feature(ctx, args.feature)
    items = sorted(workspace.artifacts_of(ctx.root, feature), key=workspace.sort_key)
    tier = tier_of(ctx, items)
    ctx.say(f"{feature.id} {feature.title}: {tier.display if tier else 'no valid risk profile yet'}")
    waiting: dict[str, list[str]] = {}
    for a in items:
        checks = reviewers.role_checks(ctx.config, a, tier)
        done = all(c.satisfied for c in checks)
        note = {"draft": " (draft, not submitted yet)", "stale": " (out of date)"}.get(a.status, "")
        mark = "✓" if done else "…"
        ctx.say(f"  {mark} {a.id} v{a.version} {a.title}{note}")
        for c in checks:
            ctx.say(f"      {describe_check(c, ctx.config)}")
            if not c.satisfied and a.status == "in_review":
                for p in c.candidates or []:
                    waiting.setdefault(f"{p} ({reviewers.role_label(c.role)})", []).append(a.id)
    if waiting:
        ctx.say("Still waiting on: " + "; ".join(f"{who} for {review.join(ids)}" for who, ids in waiting.items()) + ".")
    elif any(a.status == "draft" for a in items):
        ctx.say("Nobody is waiting yet: run /submit to send the drafts for review.")
    else:
        ctx.say("Nobody is waiting on anything.")
    return 0


def cmd_status(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = look_at_feature(ctx, args.feature)
    items = sorted(workspace.artifacts_of(ctx.root, feature), key=workspace.sort_key)
    tier = tier_of(ctx, items)
    ctx.say(f"{feature.id} {feature.title} · {tier.display if tier else 'no valid risk profile yet'}")
    for a in items:
        ctx.say(f"  {f'{a.id} v{a.version}':<14} {a.status:<9}  {a.title}")
        last = latest_rejection(a)
        if a.status == "rejected" and last:
            ctx.say(f"  {'':<14} {last['by']} said: {last['reason']}")
    state = runner.report_state(feature.path / "evals", items, tier)
    ctx.say(f"  Evals: {EVAL_STATE_WORDS[state]}")
    problems = feature_problems(ctx, feature)
    if problems:
        ctx.say(f"{len(problems)} problem(s) need fixing:")
        for i in problems:
            ctx.say(f"  ✗ {i.where}: {i.message}")
    ctx.say(workspace.next_step(items, tier, ctx.config, state))
    return 0


EVAL_STATE_WORDS = {
    "none": "no golden set yet",
    "missing": "golden set saved, not run yet",
    "out_of_date": "the last run is out of date",
    "failing": "failing (see evals/report.md)",
    "passing": "passing",
}


def latest_rejection(a: Artifact) -> dict | None:
    notes = [r for r in a.extra.get("rejections", []) if r.get("version") == a.version]
    return notes[-1] if notes else None


def cmd_submit(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = open_feature(ctx, args.feature)
    sync_reviews(ctx, feature)
    problems = feature_problems(ctx, feature)
    if problems:
        ctx.say("I can't send this for review yet:")
        for i in problems:
            ctx.say(f"  ✗ {i.where}: {i.message}")
        ctx.say("Fix these (or ask me to), then /submit again.")
        return 1
    submitter = current_user(ctx)
    submitted = review.mark_submitted(workspace.artifacts_of(ctx.root, feature))
    items = workspace.artifacts_of(ctx.root, feature)
    tier = tier_of(ctx, items)
    plan = review.plan_reviews(ctx.config, items, tier, submitter)
    if submitted:
        ctx.ops.commit(["features"], commit_message(
            feature.id, "Submit for review: " + ", ".join(f"{a.id} v{a.version}" for a in submitted)))
    elif not any(a.status == "in_review" for a in items):
        state = runner.report_state(feature.path / "evals", items, tier)
        ctx.say("There is nothing new to submit. " + workspace.next_step(items, tier, ctx.config, state))
        return 0

    if not ctx.ops.has_remote():
        ctx.say("Marked " + review.join([a.id for a in submitted]) + " as in review, but this "
                "repository is not connected to GitHub yet, so no review request was sent. "
                "Ask an engineer to connect it (see README).")
        return 0
    ctx.ops.push()
    body = review.pr_body(feature, items, ctx.config, tier, plan)
    pr = ctx.ops.pr_for_branch(feature_branch(feature.id))
    if pr is None or pr.state != "OPEN":
        pr = ctx.ops.create_pr(review.pr_title(feature), body)
    else:
        ctx.ops.update_pr(pr.number, review.pr_title(feature), body)
    ctx.ops.request_reviewers(pr.number, [r.person for r in plan.requests])
    ctx.say(review.reviewer_message(plan, tier) + f" Review request: {pr.url}")
    ctx.say("Next: wait for approvals; /reviewers shows who still has to approve what.")
    return 0


# --- evals -----------------------------------------------------------------

def cmd_golden(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = open_feature(ctx, args.feature)
    saved = workspace.save_golden(ctx.root, feature, current_user(ctx), ctx.now, read_body(ctx, args.file))
    a = saved.artifact
    if not saved.changed:
        ctx.say(f"The golden set is unchanged ({saved.cases} cases in {a.id} v{a.version}). Next: run /eval.")
        return 0
    ctx.ops.commit(["features"], commit_message(feature.id, f"Save golden set ({saved.cases} cases)", a.id, a.version))
    ctx.say(f"Saved the golden set: {saved.cases} cases, recorded as {a.id} v{a.version}. Next: run /eval.")
    return 0


def run_feature_eval(ctx: Ctx, feature: Feature, live: bool) -> dict:
    items = workspace.artifacts_of(ctx.root, feature)
    evals_dir = feature.path / "evals"
    golden = evals_dir / runner.GOLDEN_FILE
    if not golden.is_file():
        raise WorkspaceError("There is no golden set yet. Draft the cases and save them with /eval first.")
    cache = eval_model.Cache(evals_dir / runner.CACHE_DIR)
    if live:
        settings = ctx.config.evals
        client = eval_model.live_client(cache, eval_model.load_provider(settings.get("provider", "")),
                                        settings, ctx.now)
    else:
        client = eval_model.cached_client(cache)
    return runner.run(feature.id, items, golden.read_text(encoding="utf-8"), ctx.config, tier_of(ctx, items),
                      client, "live" if live else "cached", ctx.now)


def eval_summary(report: dict) -> str:
    parts = []
    for c in report["criteria"]:
        checks = ", ".join(f"{k['metric']} {k['value'] if k['value'] is not None else 'n/a'} "
                           f"(needs {'≤' if k['op'] == '<=' else '≥'} {k['limit']})" for k in c["checks"])
        parts.append(f"{c['id']} {checks}" if checks else c["id"])
    head = "Evals pass" if report["pass"] else "Evals fail"
    text = f"{head}: {'; '.join(parts)}."
    misses = [e for e in report["errors"] if "no cached answer" in e]
    other = [e for e in report["errors"] if e not in misses]
    if misses:
        text += (f" {len(misses)} case(s) have no saved answer for this exact prompt yet; a live run "
                 "(/eval --live) asks the model and costs money.")
    if other:
        text += " Problems: " + "; ".join(other[:3]) + ("; …" if len(other) > 3 else "") + "."
    for c in report["criteria"]:
        for p in c["problems"]:
            if "no golden cases" in p or "minimum" in p:
                text += f" {p[0].upper()}{p[1:]}."
    if report["failing_cases"]:
        text += f" {len(report['failing_cases'])} failing case(s) are listed in evals/report.md."
    if report.get("answered_by_fallback_model"):
        text += (" Some answers came from a fallback model after a refusal: "
                 + ", ".join(report["answered_by_fallback_model"]) + ".")
    return text


def cmd_eval(ctx: Ctx, args: argparse.Namespace) -> int:
    if args.check:
        return eval_check(ctx, args)
    feature = open_feature(ctx, args.feature)
    if args.live:
        n = len(runner.parse_golden((feature.path / "evals" / runner.GOLDEN_FILE).read_text(encoding="utf-8"))[0]) \
            if (feature.path / "evals" / runner.GOLDEN_FILE).is_file() else 0
        ctx.say(f"Asking {ctx.config.evals.get('provider') or 'the model'} for {n} case(s)…")
    # Record the golden set first, so its eval artifact links to the versions being run.
    saved = None
    if (feature.path / "evals" / runner.GOLDEN_FILE).is_file():
        saved = workspace.save_golden(ctx.root, feature, current_user(ctx), ctx.now)
    report = run_feature_eval(ctx, feature, args.live)
    runner.write_report(feature.path / "evals", report)
    summary = f"Eval run ({report['mode']}): {'pass' if report['pass'] else 'fail'}"
    if saved and saved.changed:
        ctx.ops.commit(["features"], commit_message(feature.id, summary, saved.artifact.id, saved.artifact.version))
    else:
        ctx.ops.commit(["features"], commit_message(feature.id, summary))
    ctx.say(eval_summary(report))
    if report["pass"]:
        ctx.say("Next: run /submit so reviewers see the results with the items.")
    return 0 if report["pass"] else 1


def eval_check(ctx: Ctx, args: argparse.Namespace) -> int:
    """CI: re-run every golden set from cache and compare with the committed report."""
    features = workspace.list_features(ctx.root) if args.all else [resolve_feature(ctx, args.feature)]
    failed = 0
    checked = 0
    for feature in features:
        if not (feature.path / "evals" / runner.GOLDEN_FILE).is_file():
            continue
        checked += 1
        fresh = run_feature_eval(ctx, feature, live=False)
        committed = runner.read_report(feature.path / "evals")
        if committed is None:
            ctx.say(f"  ✗ {feature.id}: there is no committed eval report; run /eval.")
            failed += 1
        elif runner.stable(committed) != runner.stable(fresh):
            ctx.say(f"  ✗ {feature.id}: evals/report.json does not match a fresh run; run /eval and commit.")
            failed += 1
        elif not fresh["pass"]:
            ctx.say(f"  ✗ {feature.id}: {eval_summary(fresh)}")
            failed += 1
        else:
            ctx.say(f"  ✓ {feature.id}: {eval_summary(fresh)}")
    if failed:
        ctx.say(f"eval: {failed} feature(s) failing; merging is blocked until they pass.")
        return 1
    ctx.say(f"eval: {checked} feature(s) checked, all passing." if checked else "eval: no golden sets yet.")
    return 0


# --- reviewer commands -----------------------------------------------------

def send_to_github(ctx: Ctx, feature: Feature, approve: bool, body: str) -> str:
    """Push recorded decisions and mirror them as a GitHub review. Returns a
    sentence for the reviewer."""
    if not ctx.ops.has_remote():
        return "This repository is not connected to GitHub, so the decision is recorded here only."
    pr = ctx.ops.pr_for_branch(feature_branch(feature.id))
    if pr is None or pr.state != "OPEN":
        ctx.ops.push()
        return "There is no open review request on GitHub yet, so it is recorded in the files only."
    ctx.ops.push()
    ctx.ops.review_pr(pr.number, approve, body)
    items = workspace.artifacts_of(ctx.root, feature)
    tier = tier_of(ctx, items)
    plan = review.plan_reviews(ctx.config, items, tier, feature.owner)
    ctx.ops.update_pr(pr.number, review.pr_title(feature), review.pr_body(feature, items, ctx.config, tier, plan))
    return "It is on the GitHub review request too."


def say_skipped(ctx: Ctx, outcome: review.Outcome) -> None:
    for aid, why in outcome.skipped:
        ctx.say(f"Skipped {aid}: {why}.")


def cmd_approve(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = open_feature(ctx, args.feature)
    user = current_user(ctx)
    problems = feature_problems(ctx, feature)
    if problems:
        ctx.say("These need fixing before anything can be approved:")
        for i in problems:
            ctx.say(f"  ✗ {i.where}: {i.message}")
        return 1
    outcome = review.approve(ctx.config, workspace.artifacts_of(ctx.root, feature), user,
                             args.ids or None, ctx.now)
    if not outcome.done:
        # Without named IDs, items that are not this reviewer's to approve are not news.
        if args.ids:
            say_skipped(ctx, outcome)
        ctx.say("Nothing was approved." if args.ids else "Nothing is waiting for you to approve.")
        return 1
    done = outcome.done
    ctx.ops.commit(["features"], commit_message(
        feature.id, f"Approved by {user}: " + ", ".join(f"{d.artifact.id} v{d.artifact.version}" for d in done)))
    what = "; ".join(
        f"{d.artifact.id} v{d.artifact.version} as {review.join([reviewers.role_label(r) for r in d.roles])}"
        for d in done)
    where = send_to_github(ctx, feature, True, f"Approved in AIDLC Kit: {what}.")
    items = workspace.artifacts_of(ctx.root, feature)
    tier = tier_of(ctx, items)
    complete = [d.artifact.id for d in done if d.complete]
    lines = [f"Approved {what}. {where}"]
    if complete:
        lines.append(f"{review.join(complete)} {'is' if len(complete) == 1 else 'are'} now fully approved.")
    for d in done:
        if not d.complete:
            current = next(a for a in items if a.id == d.artifact.id)
            pending = reviewers.pending(ctx.config, current, tier)
            lines.append(f"{d.artifact.id} still needs " + review.join(
                [f"{reviewers.role_label(c.role)} ({', '.join(c.candidates) or 'nobody yet'})" for c in pending]) + ".")
    ctx.say(" ".join(lines))
    if args.ids:
        say_skipped(ctx, outcome)
    return 0


def cmd_reject(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = open_feature(ctx, args.feature)
    user = current_user(ctx)
    outcome = review.reject(ctx.config, workspace.artifacts_of(ctx.root, feature), user,
                            args.ids, args.reason, ctx.now)
    say_skipped(ctx, outcome)
    if not outcome.done:
        ctx.say("Nothing was rejected.")
        return 1
    ids = review.join([f"{d.artifact.id} v{d.artifact.version}" for d in outcome.done])
    ctx.ops.commit(["features"], commit_message(feature.id, f"Rejected by {user}: {ids}"))
    where = send_to_github(ctx, feature, False, f"Changes requested on {ids}: {args.reason.strip()}")
    owners = review.join(sorted({d.artifact.owner for d in outcome.done}))
    ctx.say(f"Rejected {ids} with your reason; {owners} will see it in /status. {where}")
    return 0


# --- repository and CI commands --------------------------------------------

def cmd_sync_codeowners(ctx: Ctx, args: argparse.Namespace) -> int:
    path = ctx.root / ci.CODEOWNERS_PATH
    existing = path.read_text(encoding="utf-8") if path.is_file() else None
    expected = ci.codeowners(ctx.config)
    if args.check:
        if (blocks.extract(existing, blocks.HASH_MARKERS) or "") == expected.strip():
            ctx.say("CODEOWNERS matches aidlc.yaml.")
            return 0
        ctx.say("CODEOWNERS does not match aidlc.yaml. Run `aidlc sync-codeowners` and commit the result.")
        return 1
    written = assistants.write_files(ctx.root, {
        ci.CODEOWNERS_PATH: blocks.upsert(existing, expected, blocks.HASH_MARKERS)})
    if written[0].action == "unchanged":
        ctx.say("CODEOWNERS already matches aidlc.yaml.")
        return 0
    if ctx.ops.is_repo():
        ctx.ops.commit([ci.CODEOWNERS_PATH], commit_message("AIDLC", "Regenerate CODEOWNERS from aidlc.yaml"))
    ctx.say("Regenerated CODEOWNERS from aidlc.yaml.")
    return 0


def cmd_sync_ci(ctx: Ctx, args: argparse.Namespace) -> int:
    config_text = (ctx.root / CONFIG_FILE).read_text(encoding="utf-8") if (ctx.root / CONFIG_FILE).is_file() else ""
    written = assistants.write_files(ctx.root, assistants.ci_files(ctx.root, config_text, args.install))
    changed = [w.path for w in written if w.action != "unchanged"]
    if changed and ctx.ops.is_repo():
        ctx.ops.commit(changed, commit_message("AIDLC", "Update CI workflows and CODEOWNERS"))
    ctx.say(f"Updated {len(changed)} CI file(s)." if changed else "CI files are already up to date.")
    return 0


def cmd_approvals_check(ctx: Ctx, args: argparse.Namespace) -> int:
    ops = ctx.ops
    base_config = ops.file_at(args.base, CONFIG_FILE)
    config = parse_config(base_config)[0] if base_config else ctx.config
    changed_paths = ops.changed_between(args.base, "HEAD", merge_base=True)
    notes = []
    if CONFIG_FILE in changed_paths:
        notes.append(f"This pull request changes {CONFIG_FILE}; the check uses the version on the base branch.")
    feature_dirs = sorted({"/".join(p.split("/")[:2]) for p in changed_paths
                           if p.startswith("features/") and p.endswith(".md")})
    feature_items: dict[str, list[Artifact]] = {}
    changed: list[Artifact] = []
    base_tier: dict[str, str | None] = {}
    for rel_dir in feature_dirs:
        if not (ctx.root / rel_dir).is_dir():
            continue
        feature_id, items, _ = load_feature(ctx.root / rel_dir, ctx.root)
        if feature_id is None:
            continue
        feature_items[feature_id] = items
        for a in items:
            rel = a.path.resolve().relative_to(ctx.root.resolve()).as_posix()
            if rel in changed_paths:
                changed.append(a)
                if a.type == "risk":
                    old = ops.file_at(args.base, rel)
                    try:
                        base_tier[feature_id] = art.parse(old).extra.get("approved_tier") if old else None
                    except ArtifactError:
                        base_tier[feature_id] = None
    reviews = ops.pr_reviews(args.pr) if changed else []
    result = review.approvals_check(config, changed, feature_items, reviews, version_at(ctx), base_tier)
    for line in result.problems:
        ctx.say(f"  ✗ {line}")
    for line in notes + result.notes:
        ctx.say(f"  ! {line}")
    if result.ok:
        ctx.say(f"approvals_complete: all {len(result.checked)} submitted item(s) have every required approval.")
        return 0
    ctx.say(f"approvals_complete: {len(result.problems)} problem(s); merging is blocked until they are resolved.")
    return 1


def _no_base(ref: str | None, ops: GitOps) -> bool:
    return not ref or set(ref) == {"0"} or not ops.ref_exists(ref)


def cmd_audit_record(ctx: Ctx, args: argparse.Namespace) -> int:
    ops = ctx.ops
    fresh = _no_base(args.before, ops)
    changed = ops.tracked_files(args.after, "features") if fresh else ops.changed_between(args.before, args.after)
    log_path = ctx.root / audit.LOG
    old_log = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""

    def load_head(rel_dir: str) -> list[Artifact]:
        return load_feature(ctx.root / rel_dir, ctx.root)[1] if (ctx.root / rel_dir).is_dir() else []

    entries = audit.build_entries(
        changed, load_head, lambda p: None if fresh else ops.file_at(args.before, p), ctx.config,
        args.actor, args.after, args.pr or audit.pr_from_subject(ops.commit_subject(args.after)), ctx.now)
    if not entries:
        ctx.say("No artifacts changed; nothing to record.")
        return 0
    audit.append(ctx.root, entries)
    problems = audit.check_log(old_log, log_path.read_text(encoding="utf-8"))
    if problems:
        ctx.say(" ".join(problems))
        return 1
    if args.commit:
        ops.commit([audit.LOG], commit_message("AIDLC", f"Audit: {len(entries)} change(s) in {args.after[:7]}"))
        ops.push_head_to(MAIN_BRANCH)
    ctx.say(f"Recorded {len(entries)} change(s) in the audit log.")
    return 0


def cmd_audit_check(ctx: Ctx, args: argparse.Namespace) -> int:
    if _no_base(args.base, ctx.ops):
        ctx.say("No earlier version to compare the audit log with; nothing to check.")
        return 0
    path = ctx.root / audit.LOG
    problems = audit.check_log(ctx.ops.file_at(args.base, audit.LOG),
                               path.read_text(encoding="utf-8") if path.is_file() else None, args.frozen)
    for line in problems:
        ctx.say(f"  ✗ {line}")
    if problems:
        return 1
    ctx.say("The audit log is intact.")
    return 0


def cmd_init(ctx: Ctx, args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    names = list(dict.fromkeys(args.assistant or []))
    written = assistants.init(root, names, args.install)
    changed = [w for w in written if w.action != "unchanged"]
    for w in changed:
        ctx.say(f"  {w.action} {w.path}")
    ops = GitOps(root) if ctx.ops.root != root else ctx.ops
    if changed and not args.no_commit and ops.is_repo():
        ops.commit([w.path for w in changed],
                   commit_message("AIDLC", f"Set up AIDLC Kit for {review.join(names)}"))
        saved = "and saved them"
    else:
        saved = "(not committed)" if changed else ""
    head = f"Set up AIDLC Kit for {review.join(names)}" + (f" {saved}" if saved else "") + "."
    if not changed:
        head = f"AIDLC Kit for {review.join(names)} was already up to date."
    ctx.say(head + " Next: put your team in aidlc.yaml, run `aidlc validate`, and have each "
            "person run `gh auth login` once. Then a PM can start with /new-feature.")
    return 0


# --- wiring --------------------------------------------------------------

def add_answer_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--data-classes", help="comma list: " + ", ".join(risk.DATA_CLASSES))
    p.add_argument("--autonomy", choices=risk.AUTONOMY)
    p.add_argument("--audience", choices=risk.AUDIENCE)
    p.add_argument("--regulated-decision", metavar="yes|no")
    p.add_argument("--rationale", help="one sentence on why the answers fit")
    p.add_argument("--tier", help="raise the tier above the computed one, e.g. T3")


def add_content_flags(p: argparse.ArgumentParser, a_type: str | None) -> None:
    p.add_argument("--title")
    p.add_argument("--body-file", help="draft text in Markdown; '-' reads standard input")
    p.add_argument("--summary", help="short description of the change, for the history")
    if a_type in (None, "criteria"):
        p.add_argument("--threshold", action="append", metavar="NAME=VALUE",
                       help="e.g. accuracy=0.9; repeat for more")
    if a_type in (None, "asset"):
        p.add_argument("--human-review-step", help="who checks the AI output before it takes effect")
        p.add_argument("--set-model", help="model the eval runner uses for this prompt")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aidlc", description="AIDLC Kit workflow commands.")
    parser.add_argument("--root", default=".", help="repository folder (default: current folder)")
    parser.add_argument("--verbose", action="store_true", help="show Git details when something fails")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="set up this repository for the kit and your AI assistant(s)")
    p.add_argument("--assistant", action="append", choices=sorted(assistants.ASSISTANTS),
                   help="repeat for several: " + "; ".join(
                       f"{a.name} = {a.summary}" for a in assistants.ASSISTANTS.values()))
    p.add_argument("--no-commit", action="store_true", help="write the files but do not commit them")
    p.add_argument("--install", default=ci.DEFAULT_INSTALL, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("golden", help="save the golden set (test cases) and record it")
    p.add_argument("--feature")
    p.add_argument("--file", help="cases as YAML; '-' reads standard input (default: re-record golden.yaml)")
    p.set_defaults(func=cmd_golden)

    p = sub.add_parser("eval", help="run the golden set and write the eval report")
    p.add_argument("--feature")
    p.add_argument("--live", action="store_true", help="ask the configured model (costs money) and save answers")
    p.add_argument("--check", action="store_true", help="CI: re-run from saved answers, compare with the report")
    p.add_argument("--all", action="store_true", help="with --check: every feature")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("approve", help="approve items waiting for your review")
    p.add_argument("ids", nargs="*", help="item IDs (default: everything waiting for you)")
    p.add_argument("--feature")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("reject", help="reject items, saying why")
    p.add_argument("ids", nargs="+")
    p.add_argument("--reason", required=True)
    p.add_argument("--feature")
    p.set_defaults(func=cmd_reject)

    p = sub.add_parser("sync-codeowners", help="regenerate CODEOWNERS from aidlc.yaml")
    p.add_argument("--check", action="store_true", help="only check; fail if it differs")
    p.set_defaults(func=cmd_sync_codeowners)

    p = sub.add_parser("sync-ci", help="write or update the CI workflows and CODEOWNERS")
    p.add_argument("--install", default=ci.DEFAULT_INSTALL, help="command CI uses to install the kit")
    p.set_defaults(func=cmd_sync_ci)

    p = sub.add_parser("approvals-check", help="CI: every required role approved (approvals_complete)")
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--base", required=True, help="base branch ref, e.g. origin/main")
    p.set_defaults(func=cmd_approvals_check)

    p = sub.add_parser("audit", help="CI: the append-only audit log")
    audit_sub = p.add_subparsers(dest="audit_command", required=True)
    q = audit_sub.add_parser("record", help="append entries for artifacts changed on main")
    q.add_argument("--before", required=True)
    q.add_argument("--after", required=True)
    q.add_argument("--actor", required=True)
    q.add_argument("--pr", type=int)
    q.add_argument("--commit", action="store_true", help="commit and push the log to main")
    q.set_defaults(func=cmd_audit_record)
    q = audit_sub.add_parser("check", help="fail if earlier lines were changed or removed")
    q.add_argument("--base", required=True)
    q.add_argument("--frozen", action="store_true", help="pull requests: the log must not change")
    q.set_defaults(func=cmd_audit_check)

    p = sub.add_parser("validate", help="check every artifact in the repository")
    p.add_argument("--write", action="store_true", help="write computed stale/draft statuses first")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("new-feature", help="open a feature workspace and profile its risk")
    p.add_argument("--title", required=True)
    p.add_argument("--owner", help="GitHub username (default: you)")
    add_answer_flags(p)
    p.set_defaults(func=cmd_new_feature)

    for name, a_type in CREATE_COMMANDS.items():
        p = sub.add_parser(name, help=f"write a {a_type.replace('_', ' ')}")
        p.add_argument("--feature")
        p.add_argument("--parent", action="append", help="ID it builds on; repeat for more")
        add_content_flags(p, a_type)
        p.set_defaults(func=cmd_create)

    p = sub.add_parser("change", help="edit an artifact; reviewed items get a new version")
    p.add_argument("id")
    p.add_argument("--feature")
    add_content_flags(p, None)
    p.set_defaults(func=cmd_change)

    p = sub.add_parser("risk", help="show or revise the risk profile")
    p.add_argument("--feature")
    add_answer_flags(p)
    p.set_defaults(func=cmd_risk)

    p = sub.add_parser("risk-questions", help="print the risk questionnaire")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_risk_questions)

    p = sub.add_parser("template", help="print the drafting outline for a type")
    p.add_argument("type", choices=sorted({*CREATE_COMMANDS, *CREATE_COMMANDS.values()}))
    p.set_defaults(func=cmd_template)

    p = sub.add_parser("reviewers", help="who still has to approve what")
    p.add_argument("--feature")
    p.set_defaults(func=cmd_reviewers)

    p = sub.add_parser("status", help="where the feature stands and what is next")
    p.add_argument("--feature")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("submit", help="send the feature for review")
    p.add_argument("--feature")
    p.set_defaults(func=cmd_submit)

    return parser


def main(
    argv: list[str] | None = None,
    ops_factory: Callable[[Path], GitOps] = GitOps,
    now: datetime | None = None,
    out: TextIO | None = None,
    stdin: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    root = find_root(Path(args.root))
    config, _ = load_config(root)
    ctx = Ctx(root, config, ops_factory(root), now or art.utc_now(),
              out or sys.stdout, stdin or sys.stdin)
    try:
        return args.func(ctx, args)
    except (WorkspaceError, GitError, assistants.SetupError, eval_model.EvalError) as exc:
        ctx.say(str(exc))
        if args.verbose and getattr(exc, "detail", ""):
            ctx.say(exc.detail)
        return 1


if __name__ == "__main__":
    sys.exit(main())
