"""Assistant adapters: render the neutral command prompts and working rules
into the files each AI assistant reads, and set up a repository (`aidlc init`).

The neutral source (`commands/*.md`, `rules.md`) names no assistant or
vendor. Each adapter only decides file locations, frontmatter, how the PM's
input reaches the prompt, and where the always-on rules go.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import jinja2
import yaml

from aidlc import artifacts as art
from aidlc import blocks, ci, risk
from aidlc.config import parse_config

HERE = Path(__file__).parent
DEFAULT_CONFIG = HERE / "aidlc.yaml"

BLOCK_START, BLOCK_END = blocks.MD_MARKERS

TASK_PREFIX = "AIDLC: "
INPUT_PREFIX = "aidlc"

# What the PM typed after the command, for assistants with no placeholder.
TYPED_INPUT = "whatever the PM typed with the command (it may be empty)"


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    argument_hint: str
    template: str


@dataclass(frozen=True)
class Assistant:
    name: str
    summary: str


ASSISTANTS: dict[str, Assistant] = {a.name: a for a in (
    Assistant("claude", "Claude Code: /commands in .claude/commands, rules in CLAUDE.md"),
    Assistant("copilot", "GitHub Copilot in VS Code: /commands in .github/prompts, rules in "
                         ".github/copilot-instructions.md"),
    Assistant("cursor", "Cursor: /commands in .cursor/commands, rules in .cursor/rules/aidlc.mdc"),
    Assistant("agents", "Any assistant that reads AGENTS.md: rules and workflows in AGENTS.md"),
    Assistant("vscode", "No assistant: AIDLC tasks in .vscode/tasks.json (Terminal > Run Task)"),
)}


class SetupError(ValueError):
    """Setup cannot continue; the message says why."""


# --- neutral source ------------------------------------------------------

def load_commands() -> list[Command]:
    out = []
    for path in sorted((HERE / "commands").glob("*.md")):
        parts = art.split_frontmatter(path.read_text(encoding="utf-8"))
        if parts is None:
            raise SetupError(f"{path.name} has no frontmatter")
        meta = yaml.safe_load(parts[0]) or {}
        out.append(Command(path.stem, meta["description"], meta.get("argument_hint", ""),
                           parts[1].lstrip("\n")))
    return out


def rules_text() -> str:
    return (HERE / "rules.md").read_text(encoding="utf-8").strip() + "\n"


def render_body(cmd: Command, args: str, rules_ref: str) -> str:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True,
                             autoescape=False)
    return env.from_string(cmd.template).render(args=args, rules_ref=rules_ref)


def _frontmatter(fields: dict[str, str]) -> str:
    lines = [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fields.items() if v]
    return "---\n" + "\n".join(lines) + "\n---\n"


# --- shared files: replace only our block --------------------------------

def upsert_block(existing: str | None, content: str) -> str:
    """Insert or replace the AIDLC block, leaving everything else untouched."""
    return blocks.upsert(existing, content)


# --- adapters ------------------------------------------------------------

Reader = Callable[[str], str | None]


def _claude(read: Reader) -> dict[str, str]:
    files = {"CLAUDE.md": upsert_block(read("CLAUDE.md"), rules_text())}
    for c in load_commands():
        body = render_body(c, "$ARGUMENTS", "Follow the AIDLC working rules in CLAUDE.md.")
        files[f".claude/commands/{c.name}.md"] = _frontmatter(
            {"description": c.description, "argument-hint": c.argument_hint}) + body
    return files


def _copilot(read: Reader) -> dict[str, str]:
    path = ".github/copilot-instructions.md"
    files = {path: upsert_block(read(path), rules_text())}
    for c in load_commands():
        body = render_body(c, TYPED_INPUT, f"Follow the AIDLC working rules in {path}.")
        # `agent: agent` lets the prompt run terminal commands.
        files[f".github/prompts/{c.name}.prompt.md"] = _frontmatter(
            {"description": c.description, "argument-hint": c.argument_hint, "agent": "agent"}) + body
    return files


def _cursor(read: Reader) -> dict[str, str]:
    rules = "---\ndescription: AIDLC Kit working rules\nalwaysApply: true\n---\n" + rules_text()
    files = {".cursor/rules/aidlc.mdc": rules}
    for c in load_commands():
        body = render_body(c, TYPED_INPUT, "Follow the AIDLC working rules in .cursor/rules/aidlc.mdc.")
        files[f".cursor/commands/{c.name}.md"] = f"# /{c.name}: {c.description}\n\n{body}"
    return files


def _agents(read: Reader) -> dict[str, str]:
    sections = [rules_text(), "### AIDLC workflows",
                "Each workflow has a command name. When the PM uses the name or asks for the "
                "same thing in words, follow its steps."]
    for c in load_commands():
        body = render_body(c, "what the PM asked for", "Follow the working rules above.")
        sections.append(f"#### /{c.name}: {c.description}\n\n{body.strip()}")
    return {"AGENTS.md": upsert_block(read("AGENTS.md"), "\n\n".join(sections))}


def _vscode_tasks() -> tuple[list[dict], list[dict]]:
    """Tasks for working without an AI assistant. Drafts are written in an
    editor tab and saved with the matching task (`--body-file ${file}`)."""
    def task(label: str, args: list[str], detail: str) -> dict:
        return {"label": f"{TASK_PREFIX}{label}", "type": "process", "command": "aidlc",
                "args": args, "detail": detail, "problemMatcher": [],
                "presentation": {"reveal": "always", "panel": "dedicated", "clear": True}}

    def inp(name: str) -> str:
        return "${input:" + INPUT_PREFIX + name + "}"

    q = {x.key: x for x in risk.QUESTIONS}
    inputs = [
        {"id": f"{INPUT_PREFIX}Title", "type": "promptString", "description": "Short title"},
        {"id": f"{INPUT_PREFIX}Id", "type": "promptString", "description": "Item ID, e.g. REQ-002"},
        {"id": f"{INPUT_PREFIX}Threshold", "type": "promptString", "default": "accuracy=0.9",
         "description": "Threshold as name=value"},
        {"id": f"{INPUT_PREFIX}DataClasses", "type": "promptString", "default": "internal",
         "description": q["data_classes"].text + " Comma list of: " + ", ".join(risk.DATA_CLASSES)},
        {"id": f"{INPUT_PREFIX}Autonomy", "type": "pickString",
         "description": q["autonomy"].text, "options": list(risk.AUTONOMY)},
        {"id": f"{INPUT_PREFIX}Audience", "type": "pickString",
         "description": q["audience"].text, "options": list(risk.AUDIENCE)},
        {"id": f"{INPUT_PREFIX}Regulated", "type": "pickString",
         "description": q["regulated_decision"].text, "options": ["no", "yes"]},
        {"id": f"{INPUT_PREFIX}Rationale", "type": "promptString",
         "description": "One sentence on why these answers fit"},
        {"id": f"{INPUT_PREFIX}Reason", "type": "promptString",
         "description": "What must change, in a sentence the author can act on"},
    ]
    tasks = [
        task("/new-feature", ["new-feature", "--title", inp("Title"), "--data-classes", inp("DataClasses"),
                              "--autonomy", inp("Autonomy"), "--audience", inp("Audience"),
                              "--regulated-decision", inp("Regulated"), "--rationale", inp("Rationale")],
             "Open a feature and answer the risk questions"),
        task("/discover (save open file)", ["discover", "--title", inp("Title"), "--body-file", "${file}"],
             "Save the open file as the discovery brief"),
        task("/requirement (save open file)", ["requirement", "--title", inp("Title"), "--body-file", "${file}"],
             "Save the open file as a new requirement"),
        task("/criteria (save open file)", ["criteria", "--title", inp("Title"), "--threshold",
                                            inp("Threshold"), "--body-file", "${file}"],
             "Save the open file as new acceptance criteria"),
        task("/asset (save open file)", ["asset", "--title", inp("Title"), "--body-file", "${file}"],
             "Save the open file as the AI prompt and behaviour"),
        task("/privacy (save open file)", ["privacy", "--title", inp("Title"), "--body-file", "${file}"],
             "Save the open file as the privacy assessment"),
        task("/change (after editing an item)", ["change", inp("Id")],
             "Record your edits to an item; reviewed items get a new version"),
        task("/risk", ["risk"], "Show the risk profile and tier"),
        task("/eval (save open file as golden set)", ["golden", "--file", "${file}"],
             "Save the open file as the golden set (YAML list of test cases)"),
        task("/eval", ["eval"], "Run the golden set from saved answers"),
        task("/eval --live", ["eval", "--live"], "Ask the configured model (costs money) and run the golden set"),
        task("/submit", ["submit"], "Send drafts for review"),
        task("/approve (everything waiting for me)", ["approve"], "Approve every item waiting for your role"),
        task("/reject", ["reject", inp("Id"), "--reason", inp("Reason")], "Reject an item and say why"),
        task("/reviewers", ["reviewers"], "Who still has to approve what"),
        task("/status", ["status"], "Where the feature stands and what is next"),
    ]
    return tasks, inputs


def merge_tasks(existing: str | None) -> str:
    """Replace AIDLC tasks and inputs in tasks.json, keeping everything else."""
    data = {"version": "2.0.0", "tasks": [], "inputs": []}
    if existing and existing.strip():
        try:
            data = json.loads(existing)
        except json.JSONDecodeError as exc:
            raise SetupError(
                ".vscode/tasks.json contains comments or is not plain JSON, so I did not change "
                "it. Remove the comments, or add the AIDLC tasks by hand, and run init again.") from exc
    tasks, inputs = _vscode_tasks()
    data.setdefault("version", "2.0.0")
    data["tasks"] = [t for t in data.get("tasks", [])
                     if not str(t.get("label", "")).startswith(TASK_PREFIX)] + tasks
    data["inputs"] = [i for i in data.get("inputs", [])
                      if not str(i.get("id", "")).startswith(INPUT_PREFIX)] + inputs
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _vscode(read: Reader) -> dict[str, str]:
    return {".vscode/tasks.json": merge_tasks(read(".vscode/tasks.json"))}


ADAPTERS: dict[str, Callable[[Reader], dict[str, str]]] = {
    "claude": _claude, "copilot": _copilot, "cursor": _cursor, "agents": _agents, "vscode": _vscode,
}


def render(assistant: str, read: Reader) -> dict[str, str]:
    """Files for one assistant as {relative path: content}. Pure apart from
    `read`, which returns a file's current text (or None)."""
    if assistant not in ADAPTERS:
        raise SetupError(f"{assistant!r} is not supported. Choose from: {', '.join(ADAPTERS)}.")
    return ADAPTERS[assistant](read)


# --- init ----------------------------------------------------------------

@dataclass(frozen=True)
class Written:
    path: str
    action: str  # "created" | "updated" | "unchanged"


def write_files(root: Path, planned: dict[str, str]) -> list[Written]:
    written = []
    for rel, content in planned.items():
        path = root / rel
        old = path.read_text(encoding="utf-8") if path.is_file() else None
        action = "created" if old is None else "unchanged" if old == content else "updated"
        if action != "unchanged":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        written.append(Written(rel, action))
    return written


def ci_files(root: Path, config_text: str, install: str = ci.DEFAULT_INSTALL) -> dict[str, str]:
    """CI workflows plus CODEOWNERS, with only the kit's block in CODEOWNERS."""
    config, issues = parse_config(config_text)
    if any(i.severity == "error" for i in issues):
        raise SetupError("aidlc.yaml has problems; run `aidlc validate` and fix them first.")
    out = ci.workflows(install)
    path = root / ci.CODEOWNERS_PATH
    existing = path.read_text(encoding="utf-8") if path.is_file() else None
    out[ci.CODEOWNERS_PATH] = blocks.upsert(existing, ci.codeowners(config), blocks.HASH_MARKERS)
    return out


def init(root: Path, assistants: list[str], install: str = ci.DEFAULT_INSTALL) -> list[Written]:
    """Set up a repository: config, features folder, CI, CODEOWNERS and
    assistant files."""
    if not assistants:
        options = "\n".join(f"  --assistant {a.name}: {a.summary}" for a in ASSISTANTS.values())
        raise SetupError("Choose at least one assistant (you can name several):\n" + options)

    def read(rel: str) -> str | None:
        path = root / rel
        return path.read_text(encoding="utf-8") if path.is_file() else None

    planned: dict[str, str] = {}
    if read("aidlc.yaml") is None:
        planned["aidlc.yaml"] = DEFAULT_CONFIG.read_text(encoding="utf-8")
    if not (root / "features").is_dir():
        planned["features/.gitkeep"] = ""
    planned.update(ci_files(root, planned.get("aidlc.yaml") or read("aidlc.yaml") or "", install))
    for name in dict.fromkeys(assistants):
        # Later assistants see earlier ones' output for shared files.
        for rel, content in render(name, lambda r: planned.get(r, read(r))).items():
            planned[rel] = content
    return write_files(root, planned)
