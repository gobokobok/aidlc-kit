#!/usr/bin/env python3
"""Rebuild the FEAT-001 worked example by driving the real CLI.

Maintainer tool; it does not ship with the package. It plays every role in a
scratch repository (real Git, a local bare remote, an in-memory stand-in for
GitHub), taking the people from this repository's `aidlc.yaml`, then copies
`features/` and `audit/log.jsonl` here.

The saved model answers come from a scripted stand-in (keyword rules written
below), not a real model: it is labelled as such in the cache entries and in
`aidlc.yaml`. To record real answers instead, set `eval:` in aidlc.yaml and run
`aidlc eval --live` on the feature.

    python tools/build_example.py
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from aidlc import artifacts as art  # noqa: E402
from aidlc.cli import main  # noqa: E402
from aidlc.config import load_config  # noqa: E402
from aidlc.evals import model  # noqa: E402
from aidlc.evals.model import Response  # noqa: E402
from aidlc.gitops import GitOps  # noqa: E402
from flowkit import FakeGh, git  # noqa: E402

MODEL = "example-scripted-v1"
START = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)
ANSWERS = ["--data-classes", "personal", "--autonomy", "suggest", "--audience", "customer_facing",
           "--regulated-decision", "no", "--rationale",
           "Guest messages can contain names and room numbers. The AI only suggests; staff confirm."]

# Keyword rules, in order. The first match wins; no match means "other".
RULES = [
    (("gas", "smoke", "leak", "flood", "fire"), "maintenance", True),
    (("latch", "can't lock", "cannot lock"), "maintenance", True),
    (("doctor", "ambulance", "dizzy", "chest pain"), "front_desk", True),
    (("allerg",), "food_and_beverage", True),
    (("locked out",), "front_desk", True),
    (("towel", "sheets", "make up", "housekeeping", "clean"), "housekeeping", False),
    (("breakfast", "room service", "dinner", "restaurant"), "food_and_beverage", False),
    (("air condition", "not cooling", "remote", "broken", "not working"), "maintenance", False),
    (("wifi", "checkout", "check-out", "loud", "noise"), "front_desk", False),
]


def scripted(request, settings):
    message = request.prompt.split("Guest message:\n", 1)[1].lower()
    category, urgent = "other", False
    for words, queue, flag in RULES:
        if any(w in message for w in words):
            category, urgent = queue, flag
            break
    text = json.dumps({"category": category, "urgent": urgent})
    if category == "housekeeping" and "towel" in message:
        text = f"```json\n{text}\n```"  # models often fence JSON; the runner copes
    return Response(text, "end_turn", MODEL)


class Studio:
    """A scratch repository where each call runs as one person."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.clock = START
        self.remote = tmp / "remote.git"
        git(tmp, "init", "-q", "--bare", "-b", "main", str(remote := self.remote))
        self.repo = tmp / "work"
        self.repo.mkdir()
        self.gh = FakeGh()
        self.as_("kit")
        git(self.repo, "init", "-q", "-b", "main")
        shutil.copy(ROOT / "aidlc.yaml", self.repo / "aidlc.yaml")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "Set up the kit")
        git(self.repo, "remote", "add", "origin", str(remote))
        git(self.repo, "push", "-q", "-u", "origin", "main")

    def as_(self, user: str) -> None:
        self.gh.user = user
        stamp = self.clock.strftime("%Y-%m-%dT%H:%M:%SZ")
        for key, value in {"GIT_AUTHOR_NAME": user, "GIT_COMMITTER_NAME": user,
                           "GIT_AUTHOR_EMAIL": f"{user}@example.com", "GIT_COMMITTER_EMAIL": f"{user}@example.com",
                           "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}.items():
            os.environ[key] = value
        os.environ.pop("AIDLC_USER", None)

    def __call__(self, user: str, *argv: str, stdin: str = "", ok: bool = True) -> str:
        self.clock += timedelta(minutes=7)
        self.as_(user)
        out = io.StringIO()
        code = main(["--root", str(self.repo), *argv], ops_factory=lambda r: GitOps(r, self.gh),
                    now=self.clock, out=out, stdin=io.StringIO(stdin))
        if ok and code != 0:
            raise SystemExit(f"`aidlc {' '.join(argv)}` as {user} failed:\n{out.getvalue()}")
        print(f"  {user}: aidlc {argv[0]} → {out.getvalue().strip().splitlines()[0][:100] if out.getvalue().strip() else ''}")
        return out.getvalue()

    def read(self, name: str) -> str:
        return (HERE / "example" / name).read_text(encoding="utf-8")


def roles(config) -> dict[str, list[str]]:
    held: dict[str, list[str]] = {}
    for person, their in config.people.items():
        for role in their:
            held.setdefault(role, []).append(person)
    return held


def build(tmp: Path) -> Path:
    model.load_provider = lambda name: scripted
    config, _ = load_config(ROOT)
    held = roles(config)
    author, peer = held["pm"][0], held["pm"][1]
    ops, tech, risk, engineer = (held[r][0] for r in ("ops_reviewer", "tech_reviewer", "risk_reviewer", "engineer"))
    s = Studio(tmp)

    print("The PM writes the feature")
    s(author, "new-feature", "--title", "Guest request triage", *ANSWERS)
    s(author, "discover", "--title", "Guests wait too long for a reply to simple requests",
      "--body-file", "-", stdin=s.read("discovery.md"))
    for n, title in enumerate(("Sort every guest message into one team queue", "Flag urgent messages",
                               "Suggest only: a person confirms every message"), 1):
        s(author, "requirement", "--title", title, "--body-file", "-", stdin=s.read(f"req-{n}.md"))
    s(author, "criteria", "--title", "Messages land in the right queue", "--parent", "REQ-001", "--parent", "REQ-003",
      "--threshold", "accuracy=0.9", "--threshold", "max_invalid=0", "--threshold", "max_unsafe=0",
      "--body-file", "-", stdin=s.read("ac-1.md"))
    s(author, "criteria", "--title", "Urgent messages are not missed", "--parent", "REQ-002",
      "--threshold", "urgent_recall=0.95", "--threshold", "urgent_precision=0.8", "--threshold", "max_unsafe=0",
      "--body-file", "-", stdin=s.read("ac-2.md"))
    s(author, "asset", "--title", "Guest message triage prompt", "--parent", "AC-001", "--parent", "AC-002",
      "--set-model", MODEL, "--human-review-step",
      "Front-desk staff see the suggested queue and urgent flag next to the guest message and confirm or "
      "change them before it is passed on.", "--body-file", "-", stdin=s.read("asset.md"))

    print("Golden set and eval")
    s(author, "golden", "--file", "-", stdin=s.read("golden.yaml"))
    s(author, "eval", "--live")

    print("Review")
    s(author, "submit")
    for user in (ops, tech, peer, risk):
        s(user, "approve")
    s(author, "status")

    print("Handoff")
    s(author, "handoff")
    s(tech, "approve")
    s(risk, "approve")
    before = git(s.repo, "rev-parse", "origin/main").strip()
    s(author, "handoff")
    s(author, "audit", "record", "--before", before, "--after", git(s.repo, "rev-parse", "HEAD").strip(),
      "--actor", author, "--pr", "1")

    print("Decomposition")
    before = git(s.repo, "rev-parse", "origin/main").strip()
    s(engineer, "decompose", "--body-file", "-", stdin=s.read("decomposition.md"))
    s(engineer, "submit")
    for user in (tech, risk):
        s(user, "approve")
    s(engineer, "status")
    s.as_(engineer)
    merged = s.gh.merge(s.repo)
    assert merged.returncode == 0, merged.stderr
    git(s.repo, "checkout", "-q", "main")
    git(s.repo, "pull", "-q", "--rebase")
    s(engineer, "audit", "record", "--before", before, "--after", git(s.repo, "rev-parse", "HEAD").strip(),
      "--actor", engineer, "--pr", "2")
    return s.repo


def main_script() -> None:
    with tempfile.TemporaryDirectory() as d:
        repo = build(Path(d))
        for old in (ROOT / "features").glob("FEAT-*"):
            shutil.rmtree(old)
        shutil.copytree(repo / "features", ROOT / "features", dirs_exist_ok=True)
        (ROOT / "audit").mkdir(exist_ok=True)
        shutil.copy(repo / "audit" / "log.jsonl", ROOT / "audit" / "log.jsonl")
    print("Done. Check it with: aidlc validate && aidlc eval --check --all")


if __name__ == "__main__":
    main_script()
