"""All Git and GitHub CLI (`gh`) calls live here and only here.

Errors are raised as GitError with a plain-language message for the PM; the
raw command output is kept on `.detail` for `--verbose`. Never force-pushes.
"""

import json
import os
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

MAIN_BRANCH = "main"
FEATURE_BRANCH_PREFIX = "feat/"
DECOMPOSE_BRANCH_PREFIX = "decompose/"
REMOTE = "origin"

Runner = Callable[[list[str], Path], subprocess.CompletedProcess]


class GitError(RuntimeError):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


class ConflictError(GitError):
    """Someone else changed the same lines; nothing was changed locally."""


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    state: str


@dataclass(frozen=True)
class Review:
    """One GitHub pull request review. GitHub authenticates `login`, so
    this, unlike a name written in a file, cannot be forged."""
    login: str
    state: str          # APPROVED | CHANGES_REQUESTED | COMMENTED | DISMISSED
    commit_id: str
    submitted_at: str
    body: str = ""


def _json_stream(text: str) -> list:
    """Parse concatenated JSON values (gh --paginate output)."""
    decoder, pos, out = json.JSONDecoder(), 0, []
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break
        value, pos = decoder.raw_decode(text, pos)
        out.append(value)
    return out


def subprocess_runner(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def feature_branch(feature_id: str) -> str:
    return f"{FEATURE_BRANCH_PREFIX}{feature_id}"


def decompose_branch(feature_id: str) -> str:
    return f"{DECOMPOSE_BRANCH_PREFIX}{feature_id}"


def feature_of_branch(branch: str) -> str | None:
    """FEAT-001 from feat/FEAT-001 or decompose/FEAT-001."""
    for prefix in (FEATURE_BRANCH_PREFIX, DECOMPOSE_BRANCH_PREFIX):
        if branch.startswith(prefix):
            return branch.removeprefix(prefix)
    return None


def commit_message(feature_id: str, summary: str, artifact_id: str | None = None,
                   version: int | None = None) -> str:
    """`[FEAT-001][REQ-003 v2] summary`, or `[FEAT-001] summary`."""
    tag = f"[{artifact_id} v{version}]" if artifact_id else ""
    return f"[{feature_id}]{tag} {summary}"


class GitOps:
    def __init__(self, root: Path, run: Runner = subprocess_runner):
        self.root = root
        self._run = run

    # --- plumbing --------------------------------------------------------

    def _call(self, args: list[str], what: str, check: bool = True) -> subprocess.CompletedProcess:
        try:
            result = self._run(args, self.root)
        except FileNotFoundError as exc:
            tool = args[0]
            hint = " Install the GitHub CLI and run `gh auth login` once." if tool == "gh" else ""
            raise GitError(f"Could not {what}: `{tool}` is not installed.{hint}") from exc
        if check and result.returncode != 0:
            raise GitError(f"Could not {what}.", (result.stdout or "") + (result.stderr or ""))
        return result

    def _git(self, *args: str, what: str = "run a Git step", check: bool = True) -> str:
        return self._call(["git", *args], what, check).stdout.strip()

    def _gh(self, *args: str, what: str = "talk to GitHub") -> str:
        return self._call(["gh", *args], what).stdout.strip()

    # --- questions -------------------------------------------------------

    def is_repo(self) -> bool:
        return self._call(["git", "rev-parse", "--is-inside-work-tree"], "", check=False).returncode == 0

    def current_branch(self) -> str:
        return self._git("branch", "--show-current", what="find the current branch")

    def branch_exists(self, name: str) -> bool:
        return self._call(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
                          "", check=False).returncode == 0

    def has_remote(self) -> bool:
        return REMOTE in self._git("remote", what="list remotes").split()

    def has_upstream(self) -> bool:
        return self._call(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], "",
                          check=False).returncode == 0

    def changed_paths(self) -> list[str]:
        """Modified, added, deleted and untracked paths relative to the root."""
        out = self._call(["git", "status", "--porcelain", "-z", "--untracked-files=all"],
                         "check for unsaved work").stdout
        paths = []
        entries = iter(out.split("\0"))
        for entry in entries:
            if not entry:
                continue
            status, path = entry[:2], entry[3:]
            if "R" in status or "C" in status:
                next(entries, None)  # skip the rename source
            paths.append(path)
        return paths

    def file_at_head(self, path: str) -> str | None:
        return self.file_at("HEAD", path)

    def file_at(self, ref: str, path: str) -> str | None:
        """A file's text at a commit, or None if it did not exist there."""
        result = self._call(["git", "show", f"{ref}:{path}"], "", check=False)
        return result.stdout if result.returncode == 0 else None

    def ref_exists(self, ref: str) -> bool:
        return self._call(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                          "", check=False).returncode == 0

    def changed_between(self, base: str, head: str = "HEAD", merge_base: bool = False) -> list[str]:
        """Paths that differ between two commits (`base...head` with merge_base)."""
        sep = "..." if merge_base else ".."
        out = self._git("diff", "--name-only", "--no-renames", f"{base}{sep}{head}",
                        what="compare versions")
        return [line for line in out.splitlines() if line]

    def commit_subject(self, ref: str = "HEAD") -> str:
        return self._git("log", "-1", "--format=%s", ref, what="read a commit")

    def tracked_files(self, ref: str, prefix: str) -> list[str]:
        out = self._git("ls-tree", "-r", "--name-only", ref, "--", prefix, what="list files")
        return [line for line in out.splitlines() if line]

    def feature_branches(self) -> list[str]:
        """Feature branches known locally or on the remote."""
        names = set(self._git("branch", "--list", f"{FEATURE_BRANCH_PREFIX}*",
                              "--format=%(refname:short)", what="list branches").split())
        if self.has_remote():
            out = self._call(["git", "ls-remote", "--heads", REMOTE, f"{FEATURE_BRANCH_PREFIX}*"],
                             "", check=False).stdout
            for line in out.splitlines():
                names.add(line.split("refs/heads/", 1)[-1])
        return sorted(n for n in names if n)

    def github_user(self) -> str:
        """The current person's GitHub username: $AIDLC_USER, else `gh`."""
        if os.environ.get("AIDLC_USER"):
            return os.environ["AIDLC_USER"]
        try:
            return self._gh("api", "user", "--jq", ".login", what="find your GitHub username")
        except GitError as exc:
            raise GitError(
                "I could not tell who you are on GitHub. Run `gh auth login` once "
                "(or set AIDLC_USER) and try again.", exc.detail) from exc

    def head_sha(self) -> str:
        return self._git("rev-parse", "HEAD", what="read the current commit")

    # --- actions ---------------------------------------------------------

    def commit(self, paths: Iterable[Path | str], message: str) -> bool:
        """Stage `paths` and commit. Returns False when nothing changed."""
        rel = [str(Path(p).resolve().relative_to(self.root.resolve())) if Path(p).is_absolute() else str(p)
               for p in paths]
        if not rel:
            return False
        self._git("add", "--all", "--", *rel, what="stage your changes")
        if self._call(["git", "diff", "--cached", "--quiet"], "", check=False).returncode == 0:
            return False
        self._git("commit", "--quiet", "-m", message, what="save your changes")
        return True

    def commit_all(self, message: str) -> bool:
        return self.commit(["."], message)

    def switch(self, branch: str) -> None:
        self._git("switch", "--quiet", branch, what=f"open {branch}")

    def create_branch(self, branch: str, base: str = MAIN_BRANCH) -> None:
        self._git("switch", "--quiet", "-c", branch, base, what=f"create {branch}")

    def pull_rebase(self) -> None:
        """Bring in teammates' changes. On conflict, undo and explain."""
        if not self.has_upstream():
            return
        result = self._call(["git", "pull", "--rebase", "--quiet"], "", check=False)
        if result.returncode == 0:
            return
        conflicted = self._git("diff", "--name-only", "--diff-filter=U", check=False).split()
        self._call(["git", "rebase", "--abort"], "", check=False)
        if conflicted:
            raise ConflictError(
                "Someone else changed the same part of "
                f"{', '.join(conflicted)} while you were working. I stopped and left your "
                "work exactly as it was. Ask an engineer to help combine the two versions.",
                result.stderr)
        raise GitError("I could not fetch the latest changes from GitHub. Check your "
                       "connection and try again.", result.stderr)

    def push(self) -> None:
        branch = self.current_branch()
        self._git("push", "--quiet", "-u", REMOTE, branch, what="send your work to GitHub")

    def push_head_to(self, branch: str) -> None:
        """Push HEAD to a branch (CI runs on a detached HEAD). If someone
        pushed in between, rebase once and retry. Never forces."""
        if self._call(["git", "push", "--quiet", REMOTE, f"HEAD:{branch}"], "", check=False).returncode == 0:
            return
        self._git("fetch", "--quiet", REMOTE, branch, what="fetch the latest changes")
        if self._call(["git", "rebase", "--quiet", f"{REMOTE}/{branch}"], "", check=False).returncode != 0:
            self._call(["git", "rebase", "--abort"], "", check=False)
            raise ConflictError(f"Could not add to {branch}: it changed in a conflicting way.")
        self._git("push", "--quiet", REMOTE, f"HEAD:{branch}", what=f"push to {branch}")

    def pr_for_branch(self, branch: str) -> PullRequest | None:
        result = self._call(["gh", "pr", "view", branch, "--json", "number,url,state"], "", check=False)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return PullRequest(data["number"], data["url"], data["state"])

    def create_pr(self, title: str, body: str, base: str = MAIN_BRANCH) -> PullRequest:
        branch = self.current_branch()
        self._gh("pr", "create", "--base", base, "--head", branch, "--title", title,
                 "--body", body, what="open a review request on GitHub")
        pr = self.pr_for_branch(branch)
        if pr is None:
            raise GitError("GitHub did not confirm the review request. Try /submit again.")
        return pr

    def update_pr(self, number: int, title: str, body: str) -> None:
        self._gh("pr", "edit", str(number), "--title", title, "--body", body,
                 what="update the review request on GitHub")

    def pr_reviews(self, number: int) -> list[Review]:
        out = self._gh("api", f"repos/{{owner}}/{{repo}}/pulls/{number}/reviews", "--paginate",
                       what="read the reviews on GitHub")
        reviews = []
        for page in _json_stream(out):
            for r in page if isinstance(page, list) else [page]:
                reviews.append(Review(
                    login=(r.get("user") or {}).get("login", ""), state=r.get("state", ""),
                    commit_id=r.get("commit_id", ""), submitted_at=r.get("submitted_at") or "",
                    body=r.get("body") or ""))
        return reviews

    def review_pr(self, number: int, approve: bool, body: str) -> None:
        flag = "--approve" if approve else "--request-changes"
        self._gh("pr", "review", str(number), flag, "--body", body,
                 what="record your review on GitHub")

    def merge_pr(self, number: int) -> None:
        """Squash-merge. GitHub refuses until required checks and reviews pass."""
        self._gh("pr", "merge", str(number), "--squash", what="merge the pull request on GitHub")

    def merge_commit(self, number: int) -> str | None:
        result = self._call(["gh", "pr", "view", str(number), "--json", "mergeCommit,state"], "", check=False)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return (data.get("mergeCommit") or {}).get("oid")

    def squash_merge(self, branch: str, message: str, base: str = MAIN_BRANCH) -> str:
        """Without GitHub: squash `branch` into `base` locally. Returns the commit."""
        self.switch(base)
        self._git("merge", "--squash", branch, what=f"combine {branch} into {base}")
        self._git("commit", "--quiet", "-m", message, what="save the combined work")
        return self.head_sha()

    def tags(self, pattern: str) -> list[str]:
        """Tag names matching a glob, local or on the remote."""
        names = set(self._git("tag", "--list", pattern, what="list tags").split())
        if self.has_remote():
            out = self._call(["git", "ls-remote", "--tags", REMOTE, pattern], "", check=False).stdout
            for line in out.splitlines():
                ref = line.split("refs/tags/", 1)[-1]
                names.add(ref.removesuffix("^{}"))
        return sorted(n for n in names if n)

    def create_tag(self, name: str, ref: str, message: str) -> None:
        self._git("tag", "-a", name, ref, "-m", message, what=f"tag {name}")

    def push_tag(self, name: str) -> None:
        self._git("push", "--quiet", REMOTE, f"refs/tags/{name}", what=f"send tag {name} to GitHub")

    def branch_matches(self, branch: str, base: str, path: str) -> bool:
        """Whether `path` is identical on both branches (nothing would be lost)."""
        return self._call(["git", "diff", "--quiet", base, branch, "--", path], "", check=False).returncode == 0

    def delete_branch(self, branch: str) -> None:
        self._git("branch", "-D", branch, what=f"tidy up {branch}")

    def request_reviewers(self, number: int, users: Iterable[str]) -> None:
        users = sorted(set(users))
        if users:
            self._gh("pr", "edit", str(number), "--add-reviewer", ",".join(users),
                     what="ask reviewers on GitHub")
