"""End to end through the CLI with real Git, a local bare remote and a fake `gh`."""

import io
import json
import subprocess
from pathlib import Path

import pytest

from aidlc import artifacts as art
from aidlc.cli import main
from aidlc.gitops import GitOps, subprocess_runner

from conftest import CONFIG_YAML, T0

ANSWERS = ["--data-classes", "personal", "--autonomy", "suggest", "--audience", "customer_facing",
           "--regulated-decision", "no", "--rationale", "Guest messages may contain names."]


class FakeGh:
    """Real Git; GitHub calls answered in memory."""

    def __init__(self, user="alice"):
        self.user = user
        self.calls: list[list[str]] = []
        self.pr: dict | None = None

    def __call__(self, args, cwd):
        if args[0] != "gh":
            return subprocess_runner(args, cwd)
        self.calls.append(args)
        ok = lambda out="": subprocess.CompletedProcess(args, 0, out, "")  # noqa: E731
        if args[1:3] == ["api", "user"]:
            return ok(self.user + "\n")
        if args[1:3] == ["pr", "view"]:
            if self.pr is None:
                return subprocess.CompletedProcess(args, 1, "", "no pull requests found")
            return ok(json.dumps(self.pr))
        if args[1:3] == ["pr", "create"]:
            self.pr = {"number": 1, "url": "https://github.example/acme/repo/pull/1", "state": "OPEN"}
            return ok(self.pr["url"] + "\n")
        return ok()


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("AIDLC_USER", raising=False)
    for key, value in {"GIT_AUTHOR_NAME": "Alice", "GIT_AUTHOR_EMAIL": "alice@example.com",
                       "GIT_COMMITTER_NAME": "Alice", "GIT_COMMITTER_EMAIL": "alice@example.com"}.items():
        monkeypatch.setenv(key, value)
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    repo = tmp_path / "work"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "aidlc.yaml").write_text(CONFIG_YAML)
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "-u", "origin", "main")
    gh = FakeGh()

    def run(*argv: str, stdin: str = "") -> tuple[int, str]:
        out = io.StringIO()
        code = main(["--root", str(repo), *argv], ops_factory=lambda r: GitOps(r, gh),
                     now=T0, out=out, stdin=io.StringIO(stdin))
        return code, out.getvalue()

    run.repo, run.remote, run.gh = repo, remote, gh
    return run


def log(repo: Path) -> list[str]:
    return git(repo, "log", "--format=%s").splitlines()


def test_pm_journey_without_seeing_git(env):
    code, out = env("new-feature", "--title", "Guest request triage", *ANSWERS)
    assert code == 0, out
    assert out.startswith("Opened FEAT-001 Guest request triage. It is Tier 2 (Medium) because "
                          "it handles personal data and it is customer-facing, so sam (Risk) will "
                          "check the risk profile.")
    assert git(env.repo, "branch", "--show-current").strip() == "feat/FEAT-001"

    code, out = env("discover", "--title", "Guests wait too long", "--body-file", "-",
                    stdin="## Problem\nRequests sit in one inbox.\n")
    assert code == 0 and out.startswith('Saved DISC-001 "Guests wait too long" as a draft.')
    assert env("requirement", "--title", "Route maintenance requests")[0] == 0
    assert env("criteria", "--title", "Routing accuracy", "--threshold", "accuracy=0.9")[0] == 0
    assert env("asset", "--title", "Triage prompt")[0] == 0

    assert log(env.repo)[:5] == [
        "[FEAT-001][ASSET-001 v1] Add asset: Triage prompt",
        "[FEAT-001][AC-001 v1] Add criteria: Routing accuracy",
        "[FEAT-001][REQ-001 v1] Add requirement: Route maintenance requests",
        "[FEAT-001][DISC-001 v1] Add discovery: Guests wait too long",
        '[FEAT-001][RISK-001 v1] Open feature "Guest request triage" with risk profile (T2)',
    ]
    assert art.load(next(env.repo.glob("features/*/criteria/AC-001.md"))).extra["thresholds"] == {"accuracy": 0.9}

    code, out = env("submit")
    assert code == 0, out
    assert out.startswith("Sent to dana (PM peer), bob (Ops) and priya (Tech). "
                          "sam (Risk) is included because this feature is Tier 2. "
                          "Review request: https://github.example/acme/repo/pull/1")
    assert "commit" not in out and "origin" not in out  # no Git output leaks
    assert git(env.remote, "branch", "--list", "feat/FEAT-001").strip() == "feat/FEAT-001"
    create = next(c for c in env.gh.calls if c[1:3] == ["pr", "create"])
    body = create[create.index("--body") + 1]
    assert "Who sees or is affected by the result? **Customers or guests**" in body
    assert ["gh", "pr", "edit", "1", "--add-reviewer", "bob,dana,priya,sam"] in env.gh.calls

    code, out = env("reviewers")
    assert "… Risk, Tier 2 (Medium): sam" in out
    assert "Still waiting on: sam (Risk) for RISK-001, DISC-001, REQ-001, AC-001 and ASSET-001" in out

    code, out = env("submit")
    assert code == 0 and out.startswith("Sent to")  # resubmit updates the same PR
    assert any(c[1:3] == ["pr", "edit"] and "--body" in c for c in env.gh.calls)

    code, out = env("status")
    assert "Waiting for reviewers" in out


def test_change_after_review_makes_new_version_and_stales_children(env):
    env("new-feature", "--title", "Triage", *ANSWERS)
    env("discover", "--title", "Why")
    env("requirement", "--title", "What")
    env("submit")
    code, out = env("change", "DISC-001", "--body-file", "-", "--summary", "Add interview notes",
                    stdin="## Problem\nNew evidence.\n")
    assert code == 0, out
    assert out.strip() == "DISC-001 is now v2 and needs review again. REQ-001 is now out of date; update with /change."
    assert log(env.repo)[0] == "[FEAT-001][DISC-001 v2] Add interview notes"
    code, out = env("submit")
    assert code == 1 and "REQ-001 is out of date" in out
    code, out = env("change", "REQ-001")
    assert out.startswith("REQ-001 is now v2")


def test_risk_revision_reports_new_requirements(env):
    env("new-feature", "--title", "Triage", *ANSWERS)
    code, out = env("risk", "--data-classes", "personal,payment")
    assert code == 0, out
    assert "The answers make it Tier 3 (High) because it handles payment data" in out
    assert "The tier rose from Tier 2 (Medium) to Tier 3 (High)" in out
    assert "A privacy assessment must be written and approved." in out
    assert log(env.repo)[0] == "[FEAT-001][RISK-001 v1] Revise risk profile: T2 -> T3"
    code, out = env("risk", "--tier", "T1")
    assert code == 1 and "not set it lower" in out
    code, out = env("risk")
    assert out.startswith("FEAT-001 is Tier 3 (High).")


def test_incomplete_questionnaire_says_what_is_missing(env):
    code, out = env("new-feature", "--title", "Triage", "--autonomy", "suggest")
    assert code == 1
    assert "answer --data-classes, --audience, --regulated-decision" in out
    assert git(env.repo, "branch", "--list", "feat/*").strip() == ""


def test_hand_edit_is_saved_as_new_version_before_next_command(env):
    env("new-feature", "--title", "Triage", *ANSWERS)
    env("discover", "--title", "Why")
    env("submit")
    path = next(env.repo.glob("features/*/discovery.md"))
    path.write_text(path.read_text().replace("## Problem", "## Problem (edited by hand)"))
    code, out = env("requirement", "--title", "What")
    assert code == 0
    assert out.startswith("You edited DISC-001 directly after it was reviewed, so it is now v2")
    assert art.load(path).version == 2
    assert "[FEAT-001] Save work in progress" in log(env.repo)


def test_conflict_stops_and_explains(env, tmp_path):
    env("new-feature", "--title", "Triage", *ANSWERS)
    env("discover", "--title", "Why")
    env("submit")  # pushes feat/FEAT-001 with upstream
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", "-b", "feat/FEAT-001", str(env.remote), str(other))
    theirs = next(other.glob("features/*/discovery.md"))
    theirs.write_text(theirs.read_text().replace("## Problem", "## Problem (theirs)"))
    git(other, "commit", "-qam", "their edit")
    git(other, "push", "-q")

    ours = next(env.repo.glob("features/*/discovery.md"))
    ours.write_text(ours.read_text().replace("## Problem", "## Problem (ours)"))
    code, out = env("requirement", "--title", "What")
    assert code == 1
    assert "Someone else changed the same part of" in out and "discovery.md" in out
    assert "## Problem (ours)" in ours.read_text()  # our work is intact
    assert git(env.repo, "status", "--porcelain").strip() == ""  # committed, not lost, no rebase left
