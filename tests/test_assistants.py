import io
import json
import re
import subprocess
from pathlib import Path

import pytest

from aidlc import assistants as asst
from aidlc.assistants import BLOCK_END, BLOCK_START, SetupError
from aidlc.cli import build_parser, main
from aidlc.config import parse_config

PACKAGE = Path(asst.__file__).resolve().parents[1]
VENDORS = re.compile(r"claude|anthropic|copilot|cursor|openai|gpt|gemini|codex", re.I)


def subcommands() -> set[str]:
    parser = build_parser()
    action = next(a for a in parser._actions if a.dest == "command")
    return set(action.choices)


def none(_: str) -> None:
    return None


# --- neutral source ------------------------------------------------------

def test_neutral_source_names_no_vendor():
    for path in [*(PACKAGE / "assistants" / "commands").glob("*.md"), PACKAGE / "assistants" / "rules.md"]:
        assert not VENDORS.search(path.read_text()), path.name


def test_shipped_code_only_names_vendors_in_adapters_and_providers():
    allowed = [PACKAGE / "assistants" / "__init__.py", PACKAGE / "evals" / "providers"]
    for path in PACKAGE.rglob("*"):
        if path.is_file() and path.suffix in (".py", ".md", ".yaml", ".yml") \
                and not any(path == a or a in path.parents for a in allowed):
            assert not VENDORS.search(path.read_text()), path


def test_every_cli_call_in_prompts_is_a_real_command():
    real = subcommands()
    texts = [c.template for c in asst.load_commands()] + [asst.rules_text()]
    called = {m for t in texts for m in re.findall(r"`aidlc ([a-z][a-z-]*)", t)}
    assert called and called <= real | {"<command>"}, called - real


def test_commands_cover_the_cli_workflow():
    names = {c.name for c in asst.load_commands()}
    assert names == {"new-feature", "discover", "requirement", "criteria", "asset", "privacy", "approve", "reject", "eval",
                     "change", "risk", "submit", "reviewers", "status"}
    assert all(c.description for c in asst.load_commands())


# --- adapters ------------------------------------------------------------

def test_claude():
    files = asst.render("claude", none)
    cmd = files[".claude/commands/discover.md"]
    assert cmd.startswith('---\ndescription: "Write the discovery brief')
    assert "Input from the PM: $ARGUMENTS" in cmd
    assert "Follow the AIDLC working rules in CLAUDE.md." in cmd
    assert files["CLAUDE.md"].startswith(BLOCK_START)


def test_copilot():
    files = asst.render("copilot", none)
    prompt = files[".github/prompts/new-feature.prompt.md"]
    assert 'agent: "agent"' in prompt and 'argument-hint: "<feature name>"' in prompt
    assert "$ARGUMENTS" not in prompt and "{{" not in prompt
    assert ".github/copilot-instructions.md" in files


def test_cursor():
    files = asst.render("cursor", none)
    assert files[".cursor/rules/aidlc.mdc"].startswith("---\ndescription: AIDLC Kit working rules\nalwaysApply: true\n---\n")
    assert files[".cursor/commands/submit.md"].startswith("# /submit: Send the feature's drafts for review")


def test_agents_holds_every_workflow_in_one_block():
    text = asst.render("agents", none)["AGENTS.md"]
    assert text.count(BLOCK_START) == 1
    for c in asst.load_commands():
        assert f"#### /{c.name}: " in text


def test_vscode_tasks_call_real_commands():
    data = json.loads(asst.render("vscode", none)[".vscode/tasks.json"])
    real = subcommands()
    assert all(t["label"].startswith("AIDLC: ") for t in data["tasks"])
    assert all(t["args"][0] in real for t in data["tasks"])
    ids = {i["id"] for i in data["inputs"]}
    used = {m for t in data["tasks"] for a in t["args"] for m in re.findall(r"\$\{input:(\w+)\}", a)}
    assert used <= ids


def test_unknown_assistant():
    with pytest.raises(SetupError, match="not supported"):
        asst.render("emacs", none)


# --- shared files --------------------------------------------------------

def test_upsert_block_keeps_company_content_and_is_idempotent():
    mine = "# Our rules\n\nBe kind.\n"
    once = asst.upsert_block(mine, "v1")
    assert once.startswith(mine.rstrip("\n") + "\n\n" + BLOCK_START)
    twice = asst.upsert_block(once, "v1")
    assert twice == once
    after = once + "\n## More of ours\n"
    updated = asst.upsert_block(after, "v2")
    assert "v1" not in updated and "v2" in updated
    assert updated.startswith("# Our rules") and updated.endswith("## More of ours\n")
    assert updated.count(BLOCK_START) == updated.count(BLOCK_END) == 1


def test_merge_tasks_keeps_other_tasks():
    theirs = json.dumps({"version": "2.0.0", "tasks": [{"label": "build", "type": "shell", "command": "make"},
                                                      {"label": "AIDLC: old", "command": "x"}],
                         "inputs": [{"id": "theirs", "type": "promptString"}]})
    merged = json.loads(asst.merge_tasks(theirs))
    labels = [t["label"] for t in merged["tasks"]]
    assert labels[0] == "build" and "AIDLC: old" not in labels
    assert merged["inputs"][0]["id"] == "theirs"
    assert asst.merge_tasks(asst.merge_tasks(theirs)) == asst.merge_tasks(theirs)


def test_merge_tasks_refuses_jsonc():
    with pytest.raises(SetupError, match="comments"):
        asst.merge_tasks('{\n  // build\n  "version": "2.0.0"\n}')


# --- init ----------------------------------------------------------------

def test_init_requires_an_assistant(tmp_path):
    with pytest.raises(SetupError, match="--assistant copilot"):
        asst.init(tmp_path, [])


def test_init_sets_up_and_reruns_cleanly(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Ours\n")
    written = asst.init(tmp_path, ["agents", "copilot"])
    assert {w.path: w.action for w in written}["AGENTS.md"] == "updated"
    assert (tmp_path / "features" / ".gitkeep").exists()
    cfg, issues = parse_config((tmp_path / "aidlc.yaml").read_text())
    assert issues == [] and "sam" in cfg.people
    assert all(w.action == "unchanged" for w in asst.init(tmp_path, ["agents", "copilot"]))
    assert (tmp_path / "AGENTS.md").read_text().startswith("# Ours\n")


def test_init_never_overwrites_config(tmp_path):
    (tmp_path / "aidlc.yaml").write_text("display_name: Ours\n")
    asst.init(tmp_path, ["vscode"])
    assert (tmp_path / "aidlc.yaml").read_text() == "display_name: Ours\n"


def test_cli_init_commits_only_its_files(tmp_path, monkeypatch):
    for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(k, "Setup")
    for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, "setup@example.com")
    git = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True,  # noqa: E731
                                    check=True).stdout
    git("init", "-q", "-b", "main")
    (tmp_path / "README.md").write_text("hi\n")
    git("add", ".")
    git("commit", "-qm", "init")
    (tmp_path / "notes.txt").write_text("unrelated work in progress\n")
    out = io.StringIO()
    assert main(["--root", str(tmp_path), "init", "--assistant", "copilot", "--assistant", "vscode"],
                out=out) == 0
    assert "Set up AIDLC Kit for copilot and vscode and saved them." in out.getvalue()
    assert git("log", "-1", "--format=%s").strip() == "[AIDLC] Set up AIDLC Kit for copilot and vscode"
    assert git("status", "--porcelain").strip() == "?? notes.txt"
    out = io.StringIO()
    main(["--root", str(tmp_path), "init", "--assistant", "copilot"], out=out)
    assert "already up to date" in out.getvalue()
