"""Handoff and decomposition end to end: real Git, a bare remote, a fake
GitHub that merges, and a fake model provider."""

import json

from aidlc import audit, handoff
from aidlc.validate import validate_repo

from flowkit import git, log
from test_eval_flow import setup_feature
from test_evals import GOLDEN
from test_review_flow import as_user, item


def ready_feature(env, monkeypatch):
    """A Tier 2 feature with a passing eval, everything submitted."""
    setup_feature(env, monkeypatch)
    env("golden", "--file", "-", stdin=GOLDEN)
    assert env("eval", "--live")[0] == 0
    assert env("submit")[0] == 0


def approve_all(env):
    for user in ("bob", "priya", "dana", "sam"):
        assert as_user(env, user, "approve")[0] == 0, user
    as_user(env, "alice", "status")


def test_gate_lists_everything_in_the_way_and_who_can_fix_it(env, monkeypatch):
    ready_feature(env, monkeypatch)
    as_user(env, "bob", "approve")
    code, out = as_user(env, "alice", "handoff")
    assert code == 1
    assert out.startswith("Not ready for handoff yet. What is in the way:")
    assert "✗ REQ-001 v1: still needs Tech approval. priya (Tech) can approve it with /approve." in out
    assert "✗ REQ-001 v1: still needs Risk approval, which Tier 2 (Medium) adds. sam (Risk) can approve" in out
    assert "✗ DISC-001 v1: still needs PM peer approval. dana (PM peer) can approve it" in out
    assert "the one hard gate" in out
    assert not list(env.repo.glob("features/*/handoff"))  # nothing was built


def test_gate_blocks_drafts_stale_evals_and_missing_pieces(env, monkeypatch):
    ready_feature(env, monkeypatch)
    approve_all(env)
    env("change", "ASSET-001", "--body-file", "-", stdin="## Prompt\n```text\nSort: {{ input }}\n```\n")
    code, out = as_user(env, "alice", "handoff")
    assert code == 1
    assert "✗ ASSET-001 v2: is a draft that was never submitted. alice can send it for review with /submit." in out
    assert "✗ EVAL-001 v1: is out of date" in out or "✗ Evals: the eval report is older" in out


def test_handoff_round_trip(env, monkeypatch):
    ready_feature(env, monkeypatch)
    approve_all(env)

    # Pass one: build the frozen package and ask for it to be accepted.
    code, out = as_user(env, "alice", "handoff")
    assert code == 0, out
    assert out.startswith("Everything is approved and the evals pass. I built HND-001 for engineering:")
    assert "priya (Tech)" in out and "sam (Risk) is included because this feature is Tier 2" in out
    folder = next(env.repo.glob("features/*/handoff/HND-001"))
    assert {p.name for p in folder.iterdir()} == {
        "handoff.md", "spec.md", "risk.md", "assets", "golden.yaml", "eval-report.md", "trace.json",
        "manifest.json"}
    manifest = json.loads((folder / "manifest.json").read_text())
    assert (manifest["tier"], manifest["handoff"], manifest["eval"]["pass"]) == ("T2", {"id": "HND-001", "version": 1}, True)
    assert {i["id"]: i["approvers"] for i in manifest["items"]}["REQ-001"] == ["bob", "priya", "sam"]
    assert manifest["commit"] == git(env.repo, "rev-parse", "HEAD~1").strip()
    spec = (folder / "spec.md").read_text()
    assert "## Done means" in spec and "### AC-001 v1: Routing accuracy" in spec
    assert "accuracy ≥ 0.9" in spec and "unsafe ≤ 0" in spec
    assert "## Risk and controls" in spec and "Risk" in spec
    graph = json.loads((folder / "trace.json").read_text())
    assert graph["chains"]["AC-001"] == [["AC-001", "REQ-001", "DISC-001"]]
    assert item(env, "handoff/HND-001/handoff.md").status == "in_review"
    assert validate_repo(env.repo).ok
    assert log(env.repo)[0] == "[FEAT-001][HND-001 v1] Build handoff package HND-001"

    # Not yet accepted: running it again says who is missing and does not merge.
    code, out = as_user(env, "alice", "handoff")
    assert code == 1 and out.startswith("HND-001 is not ready to merge yet:")
    assert "✗ HND-001 v1: is waiting for Tech to accept it. priya (Tech) can approve it with /approve." in out
    assert "✗ HND-001 v1: is waiting for Risk to accept it. sam (Risk) can approve it with /approve." in out
    assert out.count("priya") == 1  # GitHub's duplicate of the same gap is not repeated
    assert not env.gh.pr["state"] == "MERGED"

    # The reviewers accept the package; the second /handoff merges and tags.
    as_user(env, "priya", "approve")
    as_user(env, "sam", "approve")
    before = git(env.repo, "rev-parse", "origin/main").strip()
    code, out = as_user(env, "alice", "handoff")
    assert code == 0, out
    assert out.strip() == ("Handed off: FEAT-001 is merged and tagged FEAT-001/handoff-v1. "
                           "Engineering can now run /decompose. Further changes start a fresh branch.")
    assert env.gh.pr["state"] == "MERGED"
    assert git(env.remote, "tag", "--list").split() == ["FEAT-001/handoff-v1"]
    assert git(env.repo, "branch", "--show-current").strip() == "main"
    assert "feat/FEAT-001" not in git(env.repo, "branch", "--list")
    assert git(env.repo, "log", "-1", "--format=%s").strip().endswith("(#1)")
    tag_commit = git(env.repo, "rev-list", "-1", "FEAT-001/handoff-v1").strip()
    assert tag_commit == git(env.repo, "rev-parse", "origin/main").strip()
    assert (env.repo / "features").glob("*/handoff/HND-001/spec.md")

    # CI records the audit entries from the merge.
    after = git(env.repo, "rev-parse", "HEAD").strip()
    code, out = env("audit", "record", "--before", before, "--after", after, "--actor", "alice")
    assert code == 0, out
    entries = {e["id"]: e for e in audit.read_entries(env.repo)}
    assert entries["HND-001"]["status"] == "approved" and entries["HND-001"]["tier"] == "T2"
    assert entries["HND-001"]["approvers"] == ["priya", "sam"] and entries["HND-001"]["pr"] == 1
    assert set(entries) == {"RISK-001", "DISC-001", "REQ-001", "AC-001", "ASSET-001", "EVAL-001", "HND-001"}

    # The status now points at the engineer.
    assert env("status")[1].strip().endswith("Handed off as HND-001. Next: an engineer runs /decompose to plan the build.")



def test_decompose_on_its_own_branch(env, monkeypatch):
    ready_feature(env, monkeypatch)
    approve_all(env)
    as_user(env, "alice", "handoff")
    as_user(env, "priya", "approve")
    as_user(env, "sam", "approve")
    assert as_user(env, "alice", "handoff")[0] == 0

    code, out = as_user(env, "jonas", "decompose")
    assert code == 0, out
    assert out.startswith("Started DEC-001 from HND-001: components, interfaces, data, risks and 2 starter tasks")
    assert git(env.repo, "branch", "--show-current").strip() == "decompose/FEAT-001"
    dec = item(env, "decomposition/DEC-001.md")
    assert (dec.owner, dec.status, [(p.id, p.version) for p in dec.parents]) == ("jonas", "draft", [("HND-001", 1)])
    assert "- id: T-001" in dec.body
    assert "- REQ-001 Route requests: which component delivers it" in dec.body
    assert validate_repo(env.repo).ok
    assert log(env.repo)[0] == "[FEAT-001][DEC-001 v1] Start technical plan for HND-001"

    # A task with no criterion is flagged, not hidden; it shows up for the reviewer too.
    assert "criteria: [AC-001]" in dec.body
    plan = dec.body.replace("criteria: [AC-001]", "criteria: []", 1)
    code, out = as_user(env, "jonas", "decompose", "--body-file", "-", stdin=plan)
    assert code == 0, out
    code, out = as_user(env, "jonas", "status")
    assert "satisfies no criterion" in out
    assert validate_repo(env.repo).ok  # flagged, not blocked

    code, out = as_user(env, "jonas", "submit")
    assert code == 0, out
    create = [c for c in env.gh.calls if c[1:3] == ["pr", "create"]][-1]
    assert create[create.index("--title") + 1] == "FEAT-001: technical plan for Guest request triage"
    assert "### Flagged for the reviewer" in create[create.index("--body") + 1]
    assert env.gh.pr["number"] == 2 and env.gh.pr["branch"] == "decompose/FEAT-001"


def test_decompose_needs_a_handoff(env, monkeypatch):
    ready_feature(env, monkeypatch)
    code, out = as_user(env, "jonas", "decompose")
    assert code == 1 and "FEAT-001 has not been handed off yet. Run /handoff first." in out


def test_github_refusing_the_merge_is_explained(env, monkeypatch):
    ready_feature(env, monkeypatch)
    approve_all(env)
    as_user(env, "alice", "handoff")
    as_user(env, "priya", "approve")
    as_user(env, "sam", "approve")
    env.gh.refuse_merge = True
    code, out = as_user(env, "alice", "handoff")
    assert code == 1
    assert "GitHub would not merge it yet, usually because a required check or approval is still missing." in out
    assert env.gh.pr["state"] == "OPEN" and git(env.remote, "tag", "--list").strip() == ""


def test_a_changed_feature_gets_a_new_package(env, monkeypatch):
    ready_feature(env, monkeypatch)
    approve_all(env)
    as_user(env, "alice", "handoff")
    # Something changes after the package was built: it no longer matches, so it is rebuilt.
    env("change", "DISC-001", "--body-file", "-", stdin="## Problem\nNew evidence.\n")
    pkg = item(env, "handoff/HND-001/handoff.md")
    assert pkg.status == "stale"
    assert handoff.open_handoff([pkg], set()).id == "HND-001"
    code, out = as_user(env, "alice", "handoff")
    assert code == 1  # the changed items need their reviews again before a new package
    assert "DISC-001" in out
