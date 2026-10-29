"""The documentation: every link resolves, every command it shows exists."""

import re
from pathlib import Path

import pytest

from aidlc.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
DOCS = sorted([ROOT / "README.md", *(ROOT / "docs").glob("*.md")])
REQUIRED = ("overview", "quickstart", "testing-guide", "architecture", "workflow", "setup", "trade-offs",
            "limitations", "demo", "decisions", "example-tier3")


def commands() -> set[str]:
    parser = build_parser()
    return set(next(a for a in parser._actions if hasattr(a, "choices") and a.choices).choices)


@pytest.mark.parametrize("name", REQUIRED)
def test_required_docs_exist_and_are_linked_from_the_readme(name):
    assert (ROOT / "docs" / f"{name}.md").stat().st_size > 500
    assert f"docs/{name}.md" in (ROOT / "README.md").read_text()


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_relative_links_resolve(doc):
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", doc.read_text()):
        if re.match(r"[a-z]+:", target):
            continue
        assert (doc.parent / target).exists(), f"{doc.name} links to missing {target}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_commands_shown_in_docs_exist(doc):
    known = commands()
    for word in re.findall(r"(?<![\w./-])aidlc ([a-z][a-z-]+)", doc.read_text()):
        assert word in known, f"{doc.name} shows `aidlc {word}`, which is not a command"


def test_every_chat_command_is_documented_in_the_workflow():
    text = (ROOT / "docs" / "workflow.md").read_text() + (ROOT / "README.md").read_text()
    for name in ("new-feature", "discover", "requirement", "criteria", "asset", "eval", "submit", "approve",
                 "reject", "handoff", "decompose", "status", "change", "risk", "reviewers"):
        assert f"/{name}" in text, name


def test_the_demo_commands_are_real():
    text = (ROOT / "docs" / "demo.md").read_text()
    for flag in ("--data-classes", "--autonomy", "--audience", "--regulated-decision", "--rationale", "--title"):
        assert flag in text
    parser = build_parser()
    args = parser.parse_args(["new-feature", "--title", "x", "--data-classes", "personal", "--autonomy", "suggest",
                              "--audience", "customer_facing", "--regulated-decision", "no", "--rationale", "r"])
    assert args.title == "x"


def test_setup_shows_the_install_flag():
    assert "--install" in (ROOT / "docs" / "setup.md").read_text()
    args = build_parser().parse_args(["init", "--assistant", "claude", "--install", "pip install x"])
    assert args.install == "pip install x"
