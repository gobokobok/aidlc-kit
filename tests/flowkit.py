"""Shared helpers for end-to-end tests: real Git, a local bare remote and
a fake `gh` that answers GitHub calls in memory."""

import io
import json
import subprocess
from pathlib import Path

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
        self.reviews: list[dict] = []
        self.refuse_merge = False

    def merge(self, cwd: Path) -> subprocess.CompletedProcess:
        """Squash-merge the PR branch into main on the remote, like GitHub does,
        refusing while a required check would fail."""
        if self.refuse_merge:
            return subprocess.CompletedProcess([], 1, "", "Pull request is not mergeable: required status check failed")
        remote = subprocess_runner(["git", "remote", "get-url", "origin"], cwd).stdout.strip()
        clone = cwd.parent / "merge-clone"
        subprocess_runner(["rm", "-rf", str(clone)], cwd)
        for step in (["git", "clone", "-q", remote, str(clone)],
                     ["git", "merge", "--squash", f"origin/{self.pr['branch']}"],
                     ["git", "commit", "-q", "-m", f"{self.pr['title']} (#{self.pr['number']})"],
                     ["git", "push", "-q", "origin", "main"]):
            result = subprocess_runner(step, cwd if step[1] == "clone" else clone)
            if result.returncode != 0:
                return result
        sha = subprocess_runner(["git", "rev-parse", "HEAD"], clone).stdout.strip()
        self.pr = {**self.pr, "state": "MERGED", "mergeCommit": {"oid": sha}}
        return subprocess.CompletedProcess([], 0, "", "")

    def add_review(self, login: str, state: str, cwd: Path, body: str = "") -> None:
        """A review as GitHub records it: by an authenticated login, at a commit."""
        head = subprocess_runner(["git", "rev-parse", "HEAD"], cwd).stdout.strip()
        self.reviews.append({"user": {"login": login}, "state": state, "commit_id": head,
                             "submitted_at": f"2026-10-29T12:{len(self.reviews):02d}:00Z", "body": body})

    def __call__(self, args, cwd):
        if args[0] != "gh":
            return subprocess_runner(args, cwd)
        self.calls.append(args)
        ok = lambda out="": subprocess.CompletedProcess(args, 0, out, "")  # noqa: E731
        if args[1:3] == ["api", "user"]:
            return ok(self.user + "\n")
        if args[1:3] == ["pr", "merge"]:
            return self.merge(cwd)
        if args[1:3] == ["pr", "view"]:
            if self.pr is None:
                return subprocess.CompletedProcess(args, 1, "", "no pull requests found")
            return ok(json.dumps(self.pr))
        if args[1] == "api" and args[2].endswith("/reviews"):
            return ok(json.dumps(self.reviews))
        if args[1:3] == ["pr", "review"]:
            self.add_review(self.user, "APPROVED" if "--approve" in args else "CHANGES_REQUESTED", cwd,
                            args[args.index("--body") + 1])
            return ok()
        if args[1:3] == ["pr", "create"]:
            number = self.pr["number"] + 1 if self.pr else 1
            self.reviews = []
            self.pr = {"number": number, "url": f"https://github.example/acme/repo/pull/{number}",
                       "state": "OPEN", "branch": args[args.index("--head") + 1],
                       "title": args[args.index("--title") + 1]}
            return ok(self.pr["url"] + "\n")
        return ok()


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def make_env(tmp_path, monkeypatch):
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
