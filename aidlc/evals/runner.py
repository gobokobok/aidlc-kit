"""Golden-set runner: render each case's prompt from its asset, ask the model
client, parse the structured answer, score it, and compare per-criterion
metrics with the criterion's thresholds (and the risk tier's minimums).

Metrics, computed over the cases linked to a criterion:
- `accuracy`: share of cases where every expected field matches
- `<field>_accuracy`: share of cases where that field matches
- `<field>_recall`, `<field>_precision`: for true/false fields, about `true`
- `unsafe`: failed cases tagged `safety`
- `invalid`: answers that were not a JSON object (or were refused)

A threshold `name: limit` means metric >= limit; `max_<metric>` means
metric <= limit; `min_<metric>` means metric >= limit.
"""

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import jinja2
import yaml

from aidlc import artifacts as art
from aidlc.artifacts import Artifact
from aidlc.config import Config, Tier
from aidlc.evals.model import Client, EvalError, Request

GOLDEN_FILE = "golden.yaml"
REPORT_JSON = "report.json"
REPORT_MD = "report.md"
CACHE_DIR = "cache"
SAFETY_TAG = "safety"
CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
DEFAULT_MAX_TOKENS = 16000
VOLATILE = ("generated_at", "mode")  # report fields that may differ between equal runs


# --- golden set ---------------------------------------------------------------

@dataclass(frozen=True)
class Case:
    id: str
    input: Any
    expected: dict[str, Any]
    criteria: tuple[str, ...]
    tags: tuple[str, ...] = ()
    asset: str | None = None


def golden_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_golden(text: str, criteria_ids: set[str] | None = None,
                 asset_ids: set[str] | None = None) -> tuple[list[Case], list[str]]:
    """Cases and plain-language problems. With ID sets given, links are checked."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError:
        return [], [f"{GOLDEN_FILE} is not valid YAML"]
    if not isinstance(raw, list) or not raw:
        return [], [f"{GOLDEN_FILE} must be a list of cases"]
    cases, problems, seen = [], [], set()
    for n, c in enumerate(raw, 1):
        where = f"case #{n}"
        if not isinstance(c, dict):
            problems.append(f"{where} must be a set of fields (id, input, expected, criteria, tags)")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not CASE_ID_RE.match(cid):
            problems.append(f"{where} needs an id like G-001")
            continue
        where = f"case {cid}"
        if cid in seen:
            problems.append(f"{where} is listed more than once")
        seen.add(cid)
        unknown = set(c) - {"id", "input", "expected", "criteria", "tags", "asset"}
        if unknown:
            problems.append(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
        if not isinstance(c.get("input"), (str, dict)) or c.get("input") in ("", {}):
            problems.append(f"{where} needs an input (text, or a set of named fields)")
        expected = c.get("expected")
        if not isinstance(expected, dict) or not expected:
            problems.append(f"{where} needs expected output fields, e.g. {{category: maintenance}}")
            expected = {}
        crit = c.get("criteria")
        if not isinstance(crit, list) or not crit or not all(isinstance(x, str) for x in crit):
            problems.append(f"{where} must link to at least one criterion, e.g. criteria: [AC-001]")
            crit = []
        elif criteria_ids is not None:
            for x in crit:
                if x not in criteria_ids:
                    problems.append(f"{where} links to {x}, which is not a criterion in this feature")
        tags = c.get("tags", []) or []
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            problems.append(f"{where}: tags must be a list of words")
            tags = []
        asset = c.get("asset")
        if asset is not None and asset_ids is not None and asset not in asset_ids:
            problems.append(f"{where} uses {asset}, which is not an asset in this feature")
        cases.append(Case(cid, c.get("input"), expected, tuple(crit), tuple(tags), asset))
    return cases, problems


# --- prompts --------------------------------------------------------------------

def _fenced_block(body: str, heading: str) -> str | None:
    m = re.search(rf"^##\s+{heading}\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    if not m:
        return None
    block = re.search(r"^```[^\n]*\n(.*?)^```", m.group(1), re.M | re.S)
    return block.group(1) if block else None


def prompt_of(asset: Artifact) -> tuple[str | None, str]:
    """(system prompt, prompt template) from the asset body: the first fenced
    block under `## Prompt`, and optionally under `## System`."""
    prompt = _fenced_block(asset.body, "Prompt")
    if not prompt or not prompt.strip() or prompt.strip() == "(the prompt goes here)":
        raise EvalError(f"{asset.id} has no prompt yet: put it in a ```text block under '## Prompt'.")
    return _fenced_block(asset.body, "System"), prompt


def render_prompt(template: str, case_input: Any) -> str:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False, keep_trailing_newline=True)
    try:
        return env.from_string(template).render(input=case_input)
    except jinja2.TemplateError as exc:
        raise EvalError(f"the prompt could not be filled in for this input ({exc})") from exc


def parse_output(text: str) -> dict[str, Any] | None:
    """The JSON object in a model answer (allowing surrounding prose or fences)."""
    text = text.strip()
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


# --- scoring --------------------------------------------------------------------

def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual or (isinstance(actual, str) and str(expected).lower() == actual.strip().lower())
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    return expected == actual


@dataclass
class CaseResult:
    case: Case
    actual: dict[str, Any] | None = None
    fields: dict[str, bool] = field(default_factory=dict)
    error: str | None = None
    served_by: str | None = None
    refused: bool = False
    fallback: bool = False

    @property
    def correct(self) -> bool:
        return self.error is None and self.actual is not None and all(self.fields.values())


def score(case: Case, actual: dict[str, Any] | None) -> dict[str, bool]:
    return {name: actual is not None and name in actual and _same(want, actual[name])
            for name, want in case.expected.items()}


def metrics(results: list[CaseResult]) -> dict[str, float | int]:
    done = [r for r in results if r.error is None]
    n = len(done)
    out: dict[str, float | int] = {
        "cases": n,
        "accuracy": round(sum(r.correct for r in done) / n, 4) if n else 0.0,
        "unsafe": sum(1 for r in done if SAFETY_TAG in r.case.tags and not r.correct),
        "invalid": sum(1 for r in done if r.actual is None),
    }
    names = sorted({k for r in done for k in r.case.expected})
    for name in names:
        with_field = [r for r in done if name in r.case.expected]
        out[f"{name}_accuracy"] = round(sum(r.fields.get(name, False) for r in with_field) / len(with_field), 4)
        if all(isinstance(r.case.expected[name], bool) for r in with_field):
            truth = [r.case.expected[name] for r in with_field]
            guess = [bool(r.actual and _same(True, r.actual.get(name))) for r in with_field]
            tp = sum(t and g for t, g in zip(truth, guess))
            out[f"{name}_recall"] = round(tp / sum(truth), 4) if any(truth) else 1.0
            out[f"{name}_precision"] = round(tp / sum(guess), 4) if any(guess) else (0.0 if any(truth) else 1.0)
    return out


def check_threshold(name: str, limit: float, m: dict[str, float | int]) -> dict[str, Any]:
    if name.startswith("max_"):
        metric, op = name[4:], "<="
    elif name.startswith("min_"):
        metric, op = name[4:], ">="
    else:
        metric, op = name, ">="
    if metric not in m:
        return {"threshold": name, "metric": metric, "op": op, "limit": limit, "value": None, "pass": False,
                "problem": f"there is no metric {metric}; available: {', '.join(sorted(m))}"}
    value = m[metric]
    passed = value <= limit if op == "<=" else value >= limit
    return {"threshold": name, "metric": metric, "op": op, "limit": limit, "value": value, "pass": passed}


def effective_thresholds(criterion: Artifact, config: Config, tier: Tier | None) -> tuple[dict[str, float], list[str]]:
    """The criterion's thresholds (or aidlc.yaml defaults), checked against
    the tier minimums. A minimum the criterion does not mention is added."""
    own = criterion.extra.get("thresholds")
    thresholds = dict(own) if isinstance(own, dict) and own else dict(config.thresholds)
    problems = []
    for name, floor in (tier.min_thresholds if tier else {}).items():
        if name not in thresholds:
            thresholds[name] = floor
        elif art.looser_than(name, thresholds[name], floor):
            word = "above" if name.startswith("max_") else "below"
            problems.append(f"{criterion.id} sets {name} {thresholds[name]}, {word} the {tier.display} "
                            f"minimum of {floor}; tighten it with /change {criterion.id}")
    return thresholds, problems


# --- running ----------------------------------------------------------------------

def _asset_for(case: Case, assets: dict[str, Artifact]) -> Artifact:
    if case.asset:
        return assets[case.asset]
    if len(assets) == 1:
        return next(iter(assets.values()))
    raise EvalError(f"the feature has several assets; say which one with `asset:` "
                    f"({', '.join(sorted(assets))})")


def build_request(case: Case, asset: Artifact, config: Config) -> Request:
    system, template = prompt_of(asset)
    model = asset.extra.get("model") or config.evals.get("model")
    if not model:
        raise EvalError(f"no model is set: add `model:` to {asset.id} or `eval.model` to aidlc.yaml")
    return Request(
        provider=str(config.evals.get("provider") or ""),
        model=str(model),
        system=system,
        prompt=render_prompt(template, case.input),
        max_tokens=int(asset.extra.get("max_tokens") or DEFAULT_MAX_TOKENS),
        effort=asset.extra.get("effort"),
        temperature=asset.extra.get("temperature"),
        asset=f"{asset.id}@{asset.version}",
    )


def run(
    feature_id: str,
    items: list[Artifact],
    golden_text: str,
    config: Config,
    tier: Tier | None,
    client: Client,
    mode: str,
    now: datetime,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run the golden set and return the report (a plain dict)."""
    criteria = {a.id: a for a in items if a.type == "criteria"}
    assets = {a.id: a for a in items if a.type == "asset"}
    cases, problems = parse_golden(golden_text, set(criteria), set(assets))
    errors = list(problems)
    if not assets:
        errors.append("the feature has no asset (prompt) to evaluate yet")

    results: list[CaseResult] = []
    used_assets: dict[str, Artifact] = {}
    for case in cases if assets and not problems else []:
        result = CaseResult(case)
        try:
            asset = _asset_for(case, assets)
            used_assets[asset.id] = asset
            response = client(build_request(case, asset, config))
            result.served_by = response.served_by
            result.fallback = response.fallback
            result.refused = response.stop_reason == "refusal"
            result.actual = None if result.refused else parse_output(response.text)
            result.fields = score(case, result.actual)
        except EvalError as exc:
            result.error = str(exc)
            errors.append(f"case {case.id}: {exc}")
        results.append(result)
        if progress:
            progress(case.id)

    report_criteria = []
    for cid, crit in sorted(criteria.items()):
        linked = [r for r in results if cid in r.case.criteria]
        thresholds, tier_problems = effective_thresholds(crit, config, tier)
        m = metrics(linked)
        checks = [check_threshold(name, limit, m) for name, limit in thresholds.items()]
        crit_problems = list(tier_problems) + [f"{cid}: {c['problem']}" for c in checks if "problem" in c]
        if not linked:
            crit_problems.append(f"{cid} has no golden cases")
        report_criteria.append({
            "id": cid, "version": crit.version, "title": crit.title, "thresholds": thresholds,
            "metrics": m, "checks": checks, "problems": crit_problems,
            "pass": not crit_problems and all(c["pass"] for c in checks),
        })

    expected_model = {a.id: (a.extra.get("model") or config.evals.get("model")) for a in assets.values()}
    failing = []
    for r in results:
        if not r.correct:
            failing.append({"id": r.case.id, "criteria": list(r.case.criteria), "tags": list(r.case.tags),
                            "input": r.case.input, "expected": r.case.expected, "actual": r.actual,
                            "error": r.error, "refused": r.refused})
    fallback_cases = sorted(r.case.id for r in results if r.fallback)
    return {
        "feature": feature_id,
        "generated_at": art.format_ts(now),
        "mode": mode,
        "provider": config.evals.get("provider"),
        "tier": tier.name if tier else None,
        "assets": [{"id": a.id, "version": a.version, "model": expected_model[a.id]}
                   for a in sorted(used_assets.values(), key=lambda a: a.id)],
        "golden": {"sha256": golden_sha(golden_text), "cases": len(cases)},
        "criteria": report_criteria,
        "errors": errors,
        "failing_cases": failing,
        "answered_by_fallback_model": fallback_cases,
        "pass": not errors and bool(report_criteria) and all(c["pass"] for c in report_criteria),
    }


# --- reports ----------------------------------------------------------------------

def stable(report: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in report.items() if k not in VOLATILE}


def report_md(report: dict[str, Any]) -> str:
    verdict = "PASS" if report["pass"] else "FAIL"
    lines = [f"**Eval: {verdict}** ({report['golden']['cases']} cases, {report['mode']} answers"
             + (f", tier {report['tier']}" if report.get("tier") else "") + ")", ""]
    for c in report["criteria"]:
        lines.append(f"- {'✓' if c['pass'] else '✗'} **{c['id']} v{c['version']}** {c['title']}")
        for check in c["checks"]:
            value = "n/a" if check["value"] is None else check["value"]
            lines.append(f"  - {check['metric']} {value} (needs {check['op']} {check['limit']})"
                         f"{'' if check['pass'] else ' ✗'}")
        for p in c["problems"]:
            lines.append(f"  - ✗ {p}")
    if report["errors"]:
        lines += ["", "Errors:"] + [f"- {e}" for e in report["errors"]]
    if report["failing_cases"]:
        lines += ["", "Failing cases:"]
        for f in report["failing_cases"]:
            got = "refused" if f["refused"] else (f["error"] or json.dumps(f["actual"], ensure_ascii=False))
            lines.append(f"- {f['id']}: expected {json.dumps(f['expected'], ensure_ascii=False)}, got {got}")
    if report.get("answered_by_fallback_model"):
        lines += ["", "Answered by a fallback model after a refusal (results may not reflect the configured "
                      "model): " + ", ".join(report["answered_by_fallback_model"])]
    return "\n".join(lines) + "\n"


def write_report(evals_dir: Path, report: dict[str, Any]) -> list[Path]:
    evals_dir.mkdir(parents=True, exist_ok=True)
    j, m = evals_dir / REPORT_JSON, evals_dir / REPORT_MD
    j.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    m.write_text(report_md(report), encoding="utf-8")
    return [j, m]


def read_report(evals_dir: Path) -> dict[str, Any] | None:
    path = evals_dir / REPORT_JSON
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def report_state(evals_dir: Path, items: list[Artifact], tier: Tier | None) -> str:
    """'none' (no golden set), 'missing', 'out_of_date', 'failing' or 'passing'.
    A report is current only for the asset and criteria versions, golden set
    and tier it was run with."""
    golden = evals_dir / GOLDEN_FILE
    if not golden.is_file():
        return "none"
    report = read_report(evals_dir)
    if report is None:
        return "missing"
    assets = {a.id: a.version for a in items if a.type == "asset"}
    criteria = {a.id: a.version for a in items if a.type == "criteria"}
    if (report.get("golden", {}).get("sha256") != golden_sha(golden.read_text(encoding="utf-8"))
            or not report.get("assets")
            or any(assets.get(a["id"]) != a["version"] for a in report["assets"])
            or {c["id"]: c["version"] for c in report.get("criteria", [])} != criteria
            or report.get("tier") != (tier.name if tier else None)):
        return "out_of_date"
    return "passing" if report.get("pass") else "failing"
