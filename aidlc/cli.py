"""Command-line entry point: `aidlc <command>`.

Every command ends with one or two plain sentences: what happened and what
to do next. Git output is never shown unless `--verbose` is given. Slash
commands in `.claude/commands/` are thin wrappers over these commands.
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
from aidlc import review, reviewers, risk, workspace
from aidlc.artifacts import Artifact
from aidlc.config import Config, find_root, load_config
from aidlc.gitops import MAIN_BRANCH, GitError, GitOps, commit_message, feature_branch
from aidlc.validate import refresh_statuses, validate_repo
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
    "asset": "Next: run /submit to ask for a review (evals arrive with /eval).",
    "privacy_assessment": "Next: run /submit so the reviewers can check it.",
}


def create_extra(args: argparse.Namespace) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    thresholds = parse_thresholds(getattr(args, "threshold", None))
    if thresholds:
        extra["thresholds"] = thresholds
    if getattr(args, "human_review_step", None):
        extra["human_review_step"] = args.human_review_step.strip()
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


def cmd_reviewers(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = resolve_feature(ctx, args.feature)
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
    feature = resolve_feature(ctx, args.feature)
    items = sorted(workspace.artifacts_of(ctx.root, feature), key=workspace.sort_key)
    tier = tier_of(ctx, items)
    ctx.say(f"{feature.id} {feature.title} · {tier.display if tier else 'no valid risk profile yet'}")
    for a in items:
        ctx.say(f"  {f'{a.id} v{a.version}':<14} {a.status:<9}  {a.title}")
    problems = feature_problems(ctx, feature)
    if problems:
        ctx.say(f"{len(problems)} problem(s) need fixing:")
        for i in problems:
            ctx.say(f"  ✗ {i.where}: {i.message}")
    ctx.say(workspace.next_step(items, tier, ctx.config))
    return 0


def cmd_submit(ctx: Ctx, args: argparse.Namespace) -> int:
    feature = open_feature(ctx, args.feature)
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
        ctx.say("There is nothing new to submit. " + workspace.next_step(items, tier, ctx.config))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aidlc", description="AIDLC Kit workflow commands.")
    parser.add_argument("--root", default=".", help="repository folder (default: current folder)")
    parser.add_argument("--verbose", action="store_true", help="show Git details when something fails")
    sub = parser.add_subparsers(dest="command", required=True)

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
    except (WorkspaceError, GitError) as exc:
        ctx.say(str(exc))
        if args.verbose and getattr(exc, "detail", ""):
            ctx.say(exc.detail)
        return 1


if __name__ == "__main__":
    sys.exit(main())
