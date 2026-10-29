"""Review end to end: real Git, a bare remote and a fake `gh` that records
reviews the way GitHub does (by login, at a commit)."""

import json

from aidlc import artifacts as art
from aidlc import audit

from flowkit import ANSWERS, git, log


def submit_feature(env):
    env("new-feature", "--title", "Guest request triage", *ANSWERS)
    env("discover", "--title", "Guests wait too long")
    env("requirement", "--title", "Route maintenance requests")
    env("criteria", "--title", "Routing accuracy", "--threshold", "accuracy=0.9")
    env("asset", "--title", "Triage prompt")
    assert env("submit")[0] == 0


def as_user(env, user, *argv, **kw):
    env.gh.user = user
    return env(*argv, **kw)


def item(env, pattern):
    return art.load(next(env.repo.glob(f"features/*/{pattern}")))


def test_full_review_round(env):
    submit_feature(env)

    # bob approves in his IDE: recorded in the files and mirrored on GitHub.
    code, out = as_user(env, "bob", "approve")
    assert code == 0, out
    assert out.startswith("Approved REQ-001 v1 as Ops; AC-001 v1 as Ops. It is on the GitHub review request too.")
    assert "REQ-001 still needs Tech (priya) and Risk (sam)." in out
    assert "Skipped" not in out  # items that are not bob's to review are not listed
    assert log(env.repo)[0] == "[FEAT-001] Approved by bob: REQ-001 v1, AC-001 v1"
    assert any(c[1:4] == ["pr", "review", "1"] and "--approve" in c for c in env.gh.calls)

    # priya approves on the GitHub screen; alice's next /status records it.
    env.gh.add_review("priya", "APPROVED", env.repo)
    code, out = as_user(env, "alice", "status")
    assert "Recorded approvals given on GitHub: priya for REQ-001, AC-001 and ASSET-001." in out
    assert [ap.by for ap in item(env, "requirements/REQ-001.md").approvals] == ["bob", "priya"]

    # Not yet complete: approvals_complete fails and says who is missing.
    code, out = env("approvals-check", "--pr", "1", "--base", "origin/main")
    assert code == 1 and "still needs Risk approval (Tier 2 (Medium)): sam." in out

    as_user(env, "sam", "approve")
    as_user(env, "dana", "approve")
    assert item(env, "risk.md").extra["approved_tier"] == "T2"
    assert {item(env, p).status for p in ("risk.md", "discovery.md", "requirements/REQ-001.md",
                                          "criteria/AC-001.md", "assets/ASSET-001.md")} == {"approved"}
    code, out = env("approvals-check", "--pr", "1", "--base", "origin/main")
    assert code == 0, out
    assert "all 5 submitted item(s) have every required approval" in out

    # Squash-merge to main, then the audit job records what changed.
    before = git(env.repo, "rev-parse", "origin/main").strip()
    git(env.repo, "switch", "-q", "main")
    git(env.repo, "merge", "-q", "--squash", "feat/FEAT-001")
    git(env.repo, "commit", "-q", "-m", "FEAT-001: Guest request triage (#1)")
    after = git(env.repo, "rev-parse", "HEAD").strip()
    code, out = env("audit", "record", "--before", before, "--after", after, "--actor", "alice")
    assert code == 0 and out.strip() == "Recorded 5 change(s) in the audit log."
    entries = audit.read_entries(env.repo)
    req = next(e for e in entries if e["id"] == "REQ-001")
    assert (req["tier"], req["pr"], req["actor"]) == ("T2", 1, "alice")
    assert req["approvers"] == ["bob", "priya", "sam"]
    assert req["roles_satisfied"] == ["ops_reviewer", "tech_reviewer", "risk_reviewer"]

    git(env.repo, "add", audit.LOG)
    git(env.repo, "commit", "-q", "-m", "audit")
    assert env("audit", "check", "--base", after)[0] == 0
    log_path = env.repo / audit.LOG
    lines = log_path.read_text().splitlines()
    tampered = json.loads(lines[0]) | {"approvers": ["someone-else"]}
    log_path.write_text("\n".join([json.dumps(tampered), *lines[1:]]) + "\n")
    code, out = env("audit", "check", "--base", "HEAD")
    assert code == 1 and "line 1 was changed or removed" in out


def test_forged_approval_fails_the_check(env):
    submit_feature(env)
    path = next(env.repo.glob("features/*/requirements/REQ-001.md"))
    req = art.load(path)
    forged = [art.Approval(p, 1, req.updated_at) for p in ("bob", "priya", "sam")]
    art.save(art.Artifact(**{**req.__dict__, "approvals": tuple(forged), "status": "approved"}))
    git(env.repo, "commit", "-qam", "sneaky")
    code, out = env("approvals-check", "--pr", "1", "--base", "origin/main")
    assert code == 1
    assert "records an approval by bob, but bob has not approved this pull request on GitHub" in out


def test_reject_reaches_the_author(env):
    submit_feature(env)
    code, out = as_user(env, "bob", "reject", "REQ-001", "--reason", "Say which queue.")
    assert code == 0
    assert out.startswith("Rejected REQ-001 v1 with your reason; alice will see it in /status.")
    assert any(c[1:3] == ["pr", "review"] and "--request-changes" in c for c in env.gh.calls)
    code, out = as_user(env, "alice", "status")
    assert "bob said: Say which queue." in out
    assert "Address the review comments on REQ-001 with /change" in out
    assert "bob asked for changes on GitHub: Changes requested on REQ-001 v1: Say which queue." in out


def test_owner_cannot_approve_own_work(env):
    submit_feature(env)
    code, out = env("approve", "REQ-001")
    assert code == 1
    assert "Skipped REQ-001: you wrote it, so someone else has to review it." in out


def reviewer_clone(env, tmp_path):
    """A second person's checkout: a fresh clone of the remote, sitting on main."""
    import io

    from aidlc.cli import main
    from aidlc.gitops import GitOps
    from conftest import T1

    clone = tmp_path / "reviewer"
    git(tmp_path, "clone", "-q", str(env.remote), str(clone))

    def run(user, *argv):
        env.gh.user = user
        out = io.StringIO()
        code = main(["--root", str(clone), *argv], ops_factory=lambda r: GitOps(r, env.gh), now=T1,
                    out=out, stdin=io.StringIO(""))
        return code, out.getvalue()

    run.clone = clone
    return run


def test_reviewer_on_a_fresh_clone_can_approve_without_git(env, tmp_path):
    submit_feature(env)
    reviewer = reviewer_clone(env, tmp_path)
    assert git(reviewer.clone, "branch", "--show-current").strip() == "main"
    assert not list(reviewer.clone.glob("features/*"))            # the feature is not on main yet

    code, out = reviewer("bob", "approve")                         # no feature named: one is open
    assert code == 0, out
    assert out.startswith("Approved REQ-001 v1 as Ops; AC-001 v1 as Ops.")
    assert git(reviewer.clone, "branch", "--show-current").strip() == "feat/FEAT-001"
    assert any(c[1:4] == ["pr", "review", "1"] and "--approve" in c for c in env.gh.calls)
    # The approval was pushed to the feature branch for the PM to pick up.
    assert "Approved by bob" in git(env.remote, "log", "feat/FEAT-001", "-1", "--format=%s")


def test_naming_a_feature_brings_in_its_branch(env, tmp_path):
    submit_feature(env)
    reviewer = reviewer_clone(env, tmp_path)
    code, out = reviewer("priya", "reviewers", "--feature", "FEAT-001")
    assert code == 0, out
    assert "FEAT-001 Guest request triage" in out and "REQ-001" in out


def test_unknown_feature_is_explained(env, tmp_path):
    submit_feature(env)
    reviewer = reviewer_clone(env, tmp_path)
    code, out = reviewer("bob", "approve", "--feature", "FEAT-009")
    assert code == 1 and "There is no feature FEAT-009 here." in out


def test_several_open_features_must_be_named(env, tmp_path):
    submit_feature(env)
    env("new-feature", "--title", "Second one", "--data-classes", "internal", "--autonomy", "suggest",
        "--audience", "internal", "--regulated-decision", "no")
    git(env.repo, "push", "-q", "-u", "origin", "feat/FEAT-002")
    reviewer = reviewer_clone(env, tmp_path)
    code, out = reviewer("bob", "approve")
    assert code == 1 and "Several features are open: FEAT-001, FEAT-002. Name the one you mean with --feature." in out
