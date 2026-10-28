import subprocess
from pathlib import Path

import pytest

from aidlc.gitops import ConflictError, GitError, GitOps, commit_message


class FakeRun:
    """Answers commands by prefix; records every call."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls: list[list[str]] = []

    def __call__(self, args, cwd):
        self.calls.append(args)
        for prefix, (code, out) in self.answers.items():
            if tuple(args[: len(prefix)]) == prefix:
                return subprocess.CompletedProcess(args, code, out, "boom" if code else "")
        return subprocess.CompletedProcess(args, 0, "", "")


def test_commit_message_format():
    assert commit_message("FEAT-001", "Add requirement", "REQ-003", 2) == "[FEAT-001][REQ-003 v2] Add requirement"
    assert commit_message("FEAT-001", "Submit for review") == "[FEAT-001] Submit for review"


def test_commit_skips_when_nothing_staged():
    run = FakeRun({("git", "diff", "--cached", "--quiet"): (0, "")})
    assert GitOps(Path("/repo"), run).commit(["features"], "msg") is False
    assert ["git", "commit", "--quiet", "-m", "msg"] not in run.calls


def test_commit_when_something_staged():
    run = FakeRun({("git", "diff", "--cached", "--quiet"): (1, "")})
    assert GitOps(Path("/repo"), run).commit(["features"], "msg") is True
    assert ["git", "commit", "--quiet", "-m", "msg"] in run.calls


def test_pull_conflict_aborts_and_explains():
    run = FakeRun({
        ("git", "pull"): (1, ""),
        ("git", "diff", "--name-only"): (0, "features/FEAT-001-x/discovery.md\n"),
    })
    with pytest.raises(ConflictError, match="Someone else changed the same part of features/FEAT-001-x/discovery.md"):
        GitOps(Path("/repo"), run).pull_rebase()
    assert ["git", "rebase", "--abort"] in run.calls


def test_pull_skipped_without_upstream():
    run = FakeRun({("git", "rev-parse", "--abbrev-ref"): (128, "")})
    GitOps(Path("/repo"), run).pull_rebase()
    assert not any(c[:2] == ["git", "pull"] for c in run.calls)


def test_push_never_forces():
    run = FakeRun({("git", "branch", "--show-current"): (0, "feat/FEAT-001\n")})
    GitOps(Path("/repo"), run).push()
    push = next(c for c in run.calls if c[:2] == ["git", "push"])
    assert push == ["git", "push", "--quiet", "-u", "origin", "feat/FEAT-001"]
    assert not any("--force" in a or a == "-f" for c in run.calls for a in c)


def test_failures_are_plain_language():
    run = FakeRun({("git", "branch", "--show-current"): (0, "feat/FEAT-001\n"), ("git", "push"): (1, "")})
    with pytest.raises(GitError) as exc:
        GitOps(Path("/repo"), run).push()
    assert str(exc.value) == "Could not send your work to GitHub."
    assert exc.value.detail == "boom"


def test_missing_gh_is_explained():
    def run(args, cwd):
        raise FileNotFoundError(args[0])
    with pytest.raises(GitError, match="gh auth login"):
        GitOps(Path("/repo"), run).request_reviewers(1, ["bob"])


def test_github_user_prefers_env(monkeypatch):
    monkeypatch.setenv("AIDLC_USER", "alice")
    run = FakeRun()
    assert GitOps(Path("/repo"), run).github_user() == "alice"
    assert run.calls == []


def test_github_user_failure_says_how_to_fix(monkeypatch):
    monkeypatch.delenv("AIDLC_USER", raising=False)
    run = FakeRun({("gh", "api"): (1, "")})
    with pytest.raises(GitError, match="gh auth login"):
        GitOps(Path("/repo"), run).github_user()


def test_changed_paths_parses_porcelain():
    out = " M features/a.md\0?? features/new.md\0R  features/b.md\0features/old.md\0"
    run = FakeRun({("git", "status"): (0, out)})
    assert GitOps(Path("/repo"), run).changed_paths() == [
        "features/a.md", "features/new.md", "features/b.md"]


def test_request_reviewers_dedupes():
    run = FakeRun()
    GitOps(Path("/repo"), run).request_reviewers(7, ["sam", "bob", "sam"])
    assert run.calls == [["gh", "pr", "edit", "7", "--add-reviewer", "bob,sam"]]
