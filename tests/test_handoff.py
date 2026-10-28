"""The handoff gate, package integrity, technical-plan checks and git merge/tag steps."""

import json
import subprocess
from dataclasses import replace

import pytest

from aidlc import artifacts as art
from aidlc import decompose, handoff
from aidlc.config import parse_config
from aidlc.gitops import GitOps
from aidlc.validate import validate_repo

from conftest import CONFIG_YAML, T1, config, make, make_risk
from flowkit import git, log
from test_eval_flow import setup_feature
from test_evals import GOLDEN
from test_review_flow import as_user


def approved(a, *people):
    return replace(a, status="approved", approvals=tuple(art.Approval(p, a.version, T1) for p in people))


def full_chain(tier="T2"):
    """A complete, fully approved Tier 2 feature."""
    risk = approved(make_risk(tier, approved_tier=tier), "sam")
    return [
        risk,
        approved(make("DISC-001", "discovery"), "dana", "sam"),
        approved(make("REQ-001", "requirement", parents=(("DISC-001", 1),)), "bob", "priya", "sam"),
        approved(make("AC-001", "criteria", parents=(("REQ-001", 1),), thresholds={"accuracy": 0.9}),
                 "bob", "priya", "sam"),
        approved(make("ASSET-001", "asset", parents=(("AC-001", 1),)), "priya", "sam"),
        approved(make("EVAL-001", "eval", parents=(("AC-001", 1), ("ASSET-001", 1))), "jonas", "sam"),
    ]


def blockers(items, state="passing", cfg=None):
    return [str(b) for b in handoff.gate(cfg or config(), items, state)]


# --- the gate ---------------------------------------------------------------------

def test_complete_feature_passes_the_gate():
    assert blockers(full_chain()) == []


def test_gate_reports_missing_pieces_with_the_command_that_adds_them():
    out = blockers([i for i in full_chain() if i.type not in ("asset", "eval")])
    assert "Feature: there is no asset yet. alice can add it with /asset." in out
    assert "Feature: there is no eval yet. alice can add it with /eval." in out


@pytest.mark.parametrize(("status", "fragment"), [
    ("draft", "is a draft that was never submitted. alice can send it for review with /submit."),
    ("stale", "is out of date because something it builds on changed. alice can update it with /change REQ-001."),
    ("rejected", "was rejected"),
])
def test_gate_blocks_unfinished_items(status, fragment):
    items = [replace(a, status=status, approvals=()) if a.id == "REQ-001" else a for a in full_chain()]
    assert any(fragment in b for b in blockers(items)), blockers(items)


def test_rejection_reason_is_shown():
    rj = [{"by": "bob", "version": 1, "at": "2026-10-29T10:00:00Z", "reason": "Say which queue."}]
    items = [replace(a, status="rejected", approvals=(), extra={**a.extra, "rejections": rj})
             if a.id == "REQ-001" else a for a in full_chain()]
    assert any("was rejected (bob: Say which queue.)" in b for b in blockers(items))


def test_gate_names_who_can_approve_what_is_missing():
    items = [replace(a, approvals=tuple(ap for ap in a.approvals if ap.by != "priya")) if a.id == "REQ-001" else a
             for a in full_chain()]
    assert blockers(items) == ["REQ-001 v1: still needs Tech approval. priya (Tech) can approve it with /approve."]


def test_gate_says_when_nobody_holds_the_role():
    cfg, _ = parse_config(CONFIG_YAML.replace("  lee: [data_owner]\n", ""))
    items = full_chain("T3")
    out = blockers(items, cfg=cfg)
    assert any("Nobody has the Data owner role in aidlc.yaml yet" in b for b in out)


def test_tier_three_needs_privacy_assessment_and_human_review():
    out = blockers(full_chain("T3"))
    assert any("Tier 3 (High) needs a privacy assessment" in b and "/privacy" in b for b in out)
    assert any("ASSET-001: Tier 3 (High) needs a person to check the AI output" in b for b in out)


def test_gate_requires_passing_evals():
    assert blockers(full_chain(), "failing") == ["Evals: the evals fail (see evals/report.md). alice can run /eval."]
    assert "older than the current prompt" in blockers(full_chain(), "out_of_date")[0]


def test_gate_includes_validation_errors():
    from aidlc.artifacts import Issue
    out = handoff.gate(config(), full_chain(), "passing", [Issue("error", "FEAT-001/REQ-001", "links to X")])
    assert [str(b) for b in out] == ["FEAT-001/REQ-001: links to X. alice can fix it (see /status)."]


def test_risk_profile_without_a_tier_blocks():
    items = [replace(a, extra={**a.extra, "autonomy": "maybe"}) if a.type == "risk" else a for a in full_chain()]
    assert any("the risk profile is incomplete, so there is no tier" in b for b in blockers(items))


# --- tags and package state ---------------------------------------------------------

def test_handed_off_ids_from_tags():
    tags = ["FEAT-001/handoff-v1", "FEAT-001/handoff-v12", "FEAT-002/handoff-v1", "FEAT-001/other"]
    assert handoff.handed_off_ids("FEAT-001", tags) == {"HND-001", "HND-012"}
    assert handoff.tag_name("FEAT-001", "HND-003") == "FEAT-001/handoff-v3"


def test_open_handoff_and_currency():
    content = full_chain()
    refs = tuple((a.id, a.version) for a in content)
    pkg = make("HND-001", "handoff", parents=refs)
    assert handoff.is_current(pkg, content + [pkg])
    assert handoff.open_handoff([pkg], set()) is pkg and handoff.open_handoff([pkg], {"HND-001"}) is None
    moved = [replace(a, version=2) if a.id == "REQ-001" else a for a in content]
    assert not handoff.is_current(pkg, moved + [pkg])


def test_package_blockers_name_the_accepting_roles():
    content = full_chain()
    pkg = replace(make("HND-001", "handoff", parents=tuple((a.id, a.version) for a in content)),
                  status="in_review", approvals=(art.Approval("priya", 1, T1),))
    out = [str(b) for b in handoff.package_blockers(config(), pkg, content + [pkg])]
    assert out == ["HND-001 v1: is waiting for Risk to accept it. sam (Risk) can approve it with /approve."]


# --- technical plan -----------------------------------------------------------------

PLAN = """
## Tasks
```yaml
- id: T-001
  title: Build the classifier
  criteria: [AC-001]
- id: T-002
  title: Set up monitoring
  criteria: []
```
"""


def dec(body, status="draft"):
    return replace(make("DEC-001", "decomposition"), body=body, status=status)


def test_parse_tasks():
    tasks, problems = decompose.parse_tasks(PLAN)
    assert problems == [] and [(t.id, t.criteria) for t in tasks] == [("T-001", ("AC-001",)), ("T-002", ())]


@pytest.mark.parametrize(("body", "fragment"), [
    ("no tasks here", "has no task list"),
    ("## Tasks\n```yaml\n- [oops\n```", "not valid YAML"),
    ("## Tasks\n```yaml\n- id: X\n  title: t\n```", "needs an id like T-001"),
    ("## Tasks\n```yaml\n- id: T-001\n```", "needs a title"),
    ("## Tasks\n```yaml\n- {id: T-001, title: a}\n- {id: T-001, title: b}\n```", "listed more than once"),
    ("## Tasks\n```yaml\n- {id: T-001, title: a, criteria: AC-001}\n```", "criteria must be a list"),
])
def test_task_problems(body, fragment):
    assert any(fragment in p for p in decompose.parse_tasks(body)[1])


def test_untraced_tasks_are_flagged_unknown_criteria_error_uncovered_criteria_warn():
    findings = decompose.check(dec(PLAN), {"AC-001", "AC-002"})
    assert ("warning", 'task T-002 "Set up monitoring" satisfies no criterion; link it to one or drop it') in findings
    assert ("warning", "no task satisfies AC-002") in findings
    assert not any(sev == "error" for sev, _ in findings)
    bad = decompose.check(dec(PLAN.replace("[AC-001]", "[AC-009]")), {"AC-001"})
    assert ("error", "task T-001 points at AC-009, which is not a criterion in this feature") in bad
    assert all(decompose.is_flag(m) for sev, m in findings)
    assert not decompose.is_flag("something else")


def test_starter_tasks_cover_every_criterion():
    criteria = [make("AC-001", "criteria"), make("AC-002", "criteria")]
    tasks, problems = decompose.parse_tasks("## Tasks\n```yaml\n" + decompose.tasks_yaml(criteria) + "\n```")
    assert problems == [] and [t.criteria for t in tasks] == [("AC-001",), ("AC-002",), ("AC-001", "AC-002")]
    assert decompose.check(dec("## Tasks\n```yaml\n" + decompose.tasks_yaml(criteria) + "\n```"),
                           {"AC-001", "AC-002"}) == []


# --- package integrity -----------------------------------------------------------------

def test_verify_bundle(tmp_path):
    assert "no manifest.json" in handoff.verify_bundle(tmp_path)[0]
    (tmp_path / "spec.md").write_text("spec")
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {"spec.md": handoff._sha(tmp_path / "spec.md"),
                                                                  "gone.md": "x"}}))
    assert handoff.verify_bundle(tmp_path) == ["gone.md is missing from the handoff package"]
    (tmp_path / "spec.md").write_text("changed")
    assert any("spec.md was changed after the package was built" in p for p in handoff.verify_bundle(tmp_path))


# --- validator, on a real built package ---------------------------------------------------

def built_package(env, monkeypatch):
    setup_feature(env, monkeypatch)
    env("golden", "--file", "-", stdin=GOLDEN)
    env("eval", "--live")
    env("submit")
    for user in ("bob", "priya", "dana", "sam"):
        as_user(env, user, "approve")
    assert as_user(env, "alice", "handoff")[0] == 0
    return next(env.repo.glob("features/*/handoff/HND-001"))


def test_tampering_with_the_frozen_package_is_an_error(env, monkeypatch):
    folder = built_package(env, monkeypatch)
    assert validate_repo(env.repo).ok
    (folder / "spec.md").write_text((folder / "spec.md").read_text() + "\nSneaky change.\n")
    errors = [i.message for i in validate_repo(env.repo).errors]
    assert any("spec.md was changed after the package was built" in e for e in errors)
    (folder / "assets" / "ASSET-001.md").unlink()
    assert any("assets/ASSET-001.md is missing" in i.message for i in validate_repo(env.repo).errors)


def test_validator_applies_the_gate_to_a_current_package(env, monkeypatch):
    built_package(env, monkeypatch)
    path = next(env.repo.glob("features/*/requirements/REQ-001.md"))
    req = art.load(path)
    art.save(replace(req, status="in_review", approvals=tuple(a for a in req.approvals if a.by != "priya")))
    errors = [i.message for i in validate_repo(env.repo).errors]
    assert any(e.startswith("handoff gate: REQ-001 v1: still needs Tech approval") for e in errors)


def test_stale_plan_flags_show_in_validation_warnings(env, monkeypatch):
    built_package(env, monkeypatch)
    assert not [w for w in validate_repo(env.repo).warnings if decompose.is_flag(w.message)]


# --- git steps -------------------------------------------------------------------------------

@pytest.fixture
def scratch(tmp_path, monkeypatch):
    for k, v in {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com",
                 "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.com"}.items():
        monkeypatch.setenv(k, v)
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("a\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path, GitOps(tmp_path)


def test_squash_merge_tag_and_branch_checks_without_github(scratch):
    root, ops = scratch
    git(root, "switch", "-q", "-c", "feat/FEAT-001")
    (root / "features").mkdir()
    (root / "features" / "f.md").write_text("work\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "work")
    git(root, "switch", "-q", "main")
    assert not ops.branch_matches("feat/FEAT-001", "main", "features")
    sha = ops.squash_merge("feat/FEAT-001", "FEAT-001: Guest triage (HND-001)")
    assert sha == ops.head_sha() and log(root)[0] == "FEAT-001: Guest triage (HND-001)"
    assert ops.branch_matches("feat/FEAT-001", "main", "features")
    ops.create_tag("FEAT-001/handoff-v1", sha, "handed off")
    assert ops.tags("FEAT-001/handoff-v*") == ["FEAT-001/handoff-v1"]
    ops.delete_branch("feat/FEAT-001")
    assert not ops.branch_exists("feat/FEAT-001")


def test_merge_commit_reads_the_pr(scratch):
    root, _ = scratch

    def run(args, cwd):
        out = json.dumps({"mergeCommit": {"oid": "abc"}, "state": "MERGED"}) if args[1:3] == ["pr", "view"] else ""
        return subprocess.CompletedProcess(args, 0, out, "")
    assert GitOps(root, run).merge_commit(7) == "abc"


def test_whole_handoff_without_github(env, monkeypatch):
    setup_feature(env, monkeypatch)
    env("golden", "--file", "-", stdin=GOLDEN)
    env("eval", "--live")
    env("submit")
    for user in ("bob", "priya", "dana", "sam"):
        as_user(env, user, "approve")
    git(env.repo, "remote", "remove", "origin")
    code, out = as_user(env, "alice", "handoff")
    assert code == 0 and "This repository is not connected to GitHub, so the reviewers have to accept it" in out
    for user in ("priya", "sam"):
        code, out = as_user(env, user, "approve")
        assert code == 0 and "recorded here only" in out
    code, out = as_user(env, "alice", "handoff")
    assert code == 0, out
    assert out.startswith("Handed off: FEAT-001 is merged and tagged FEAT-001/handoff-v1.")
    assert git(env.repo, "tag", "--list").split() == ["FEAT-001/handoff-v1"]
    assert git(env.repo, "branch", "--show-current").strip() == "main"
    assert log(env.repo)[0] == "FEAT-001: Guest request triage (HND-001)"
