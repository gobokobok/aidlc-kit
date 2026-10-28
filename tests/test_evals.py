"""Eval runner, clients and providers: all with fake models, no API calls."""

import json
import sys
import types
from dataclasses import replace

import pytest

from aidlc import artifacts as art
from aidlc import workspace as ws
from aidlc.config import parse_config
from aidlc.evals import model, runner
from aidlc.evals.model import Cache, CacheMiss, EvalError, Request, Response
from aidlc.evals.runner import Case, CaseResult
from aidlc.validate import validate_repo

from conftest import CONFIG_YAML, T0, T1, config, make, make_risk

PROMPT_BODY = """
# Triage prompt

## System
```text
You sort hotel guest messages.
```

## Prompt
```text
Classify this guest message: {{ input }}
Answer as JSON with category and urgent.
```
"""


def cfg_with_eval(**settings):
    text = CONFIG_YAML + "eval:\n" + "".join(f"  {k}: {v}\n" for k, v in settings.items())
    cfg, issues = parse_config(text)
    assert not issues, issues
    return cfg


CFG = cfg_with_eval(provider="anthropic", model="claude-opus-5-5", api_key_env="ANTHROPIC_API_KEY")

GOLDEN = """
- id: G-001
  input: The shower in 412 is leaking onto the floor
  expected: {category: maintenance, urgent: true}
  criteria: [AC-001]
  tags: [safety]
- id: G-002
  input: Can I get two extra towels?
  expected: {category: housekeeping, urgent: false}
  criteria: [AC-001]
- id: G-003
  input: What time does breakfast start?
  expected: {category: food_and_beverage, urgent: false}
  criteria: [AC-001]
"""


def classify(prompt: str) -> str:
    """A deterministic stand-in for the model."""
    text = prompt.lower()
    if "leak" in text:
        return '{"category": "maintenance", "urgent": true}'
    if "towel" in text:
        return 'Sure! ```json\n{"category": "housekeeping", "urgent": false}\n```'
    if "breakfast" in text:
        return '{"category": "front_desk", "urgent": false}'  # wrong on purpose
    return "I am not sure."


def fake_client(answer=classify, served_by=None, fallback=False, stop=None):
    def complete(request: Request) -> Response:
        return Response(answer(request.prompt), stop, served_by, fallback)
    return complete


def feature_items(**asset_extra):
    return [
        make_risk(),
        make("REQ-001", "requirement"),
        make("AC-001", "criteria", parents=(("REQ-001", 1),), thresholds={"accuracy": 0.6, "max_unsafe": 0}),
        replace(make("ASSET-001", "asset", parents=(("AC-001", 1),), **asset_extra), body=PROMPT_BODY),
    ]


def run(items=None, golden=GOLDEN, client=None, tier=None, cfg=CFG):
    return runner.run("FEAT-001", items or feature_items(), golden, cfg, cfg.tier(tier) if tier else None,
                      client or fake_client(), "cached", T1)


# --- golden set -------------------------------------------------------------------

def test_parse_golden_valid():
    cases, problems = runner.parse_golden(GOLDEN, {"AC-001"}, {"ASSET-001"})
    assert problems == []
    assert [c.id for c in cases] == ["G-001", "G-002", "G-003"]
    assert cases[0] == Case("G-001", "The shower in 412 is leaking onto the floor",
                            {"category": "maintenance", "urgent": True}, ("AC-001",), ("safety",))


@pytest.mark.parametrize(("text", "fragment"), [
    ("not: a list", "must be a list"),
    ("- id: G-1\n  input: x\n  expected: {a: 1}\n  criteria: [AC-001]\n- id: G-1\n  input: y\n"
     "  expected: {a: 1}\n  criteria: [AC-001]", "more than once"),
    ("- id: G-1\n  expected: {a: 1}\n  criteria: [AC-001]", "needs an input"),
    ("- id: G-1\n  input: x\n  criteria: [AC-001]", "needs expected"),
    ("- id: G-1\n  input: x\n  expected: {a: 1}", "at least one criterion"),
    ("- id: G-1\n  input: x\n  expected: {a: 1}\n  criteria: [AC-009]", "AC-009, which is not a criterion"),
    ("- id: G-1\n  input: x\n  expected: {a: 1}\n  criteria: [AC-001]\n  weight: 2", "unknown field"),
    ("- id: G-1\n  input: x\n  expected: {a: 1}\n  criteria: [AC-001]\n  asset: ASSET-9", "not an asset"),
])
def test_parse_golden_problems(text, fragment):
    _, problems = runner.parse_golden(text, {"AC-001"}, {"ASSET-001"})
    assert any(fragment in p for p in problems), problems


# --- prompts and parsing -------------------------------------------------------------

def test_prompt_of_reads_fenced_blocks():
    asset = feature_items()[3]
    system, prompt = runner.prompt_of(asset)
    assert system == "You sort hotel guest messages.\n"
    assert prompt.startswith("Classify this guest message: {{ input }}")


def test_prompt_of_requires_a_prompt():
    asset = replace(make("ASSET-001", "asset"), body=ws.template_body("asset"))
    with pytest.raises(EvalError, match="has no prompt yet"):
        runner.prompt_of(asset)


def test_render_prompt():
    assert runner.render_prompt("Msg: {{ input }}", "hi") == "Msg: hi"
    assert runner.render_prompt("{{ input.room }}: {{ input.text }}", {"room": 4, "text": "x"}) == "4: x"
    with pytest.raises(EvalError, match="could not be filled in"):
        runner.render_prompt("{{ input.missing }}", {"room": 4})


@pytest.mark.parametrize(("text", "parsed"), [
    ('{"a": 1}', {"a": 1}),
    ('Here you go:\n```json\n{"a": 1}\n```', {"a": 1}),
    ("[1, 2]", None),
    ("no json here", None),
])
def test_parse_output(text, parsed):
    assert runner.parse_output(text) == parsed


# --- scoring ---------------------------------------------------------------------

def result(expected, actual, tags=()):
    case = Case("G", "x", expected, ("AC-001",), tuple(tags))
    return CaseResult(case, actual, runner.score(case, actual))


def test_metrics():
    results = [
        result({"category": "maintenance", "urgent": True}, {"category": "Maintenance", "urgent": True}, ["safety"]),
        result({"category": "maintenance", "urgent": True}, {"category": "maintenance", "urgent": False}, ["safety"]),
        result({"category": "housekeeping", "urgent": False}, {"category": "housekeeping", "urgent": "false"}),
        result({"category": "other", "urgent": False}, None),
    ]
    m = runner.metrics(results)
    assert m["cases"] == 4
    assert m["accuracy"] == 0.5
    assert m["category_accuracy"] == 0.75
    assert m["urgent_recall"] == 0.5        # one of two urgent cases caught
    assert m["urgent_precision"] == 1.0     # the one flagged urgent was urgent
    assert m["unsafe"] == 1                 # one failed safety case
    assert m["invalid"] == 1


@pytest.mark.parametrize(("name", "limit", "value_pass"), [
    ("accuracy", 0.5, (0.5, True)),
    ("accuracy", 0.6, (0.5, False)),
    ("max_unsafe", 0, (1, False)),
    ("max_invalid", 1, (1, True)),
    ("min_accuracy", 0.4, (0.5, True)),
])
def test_check_threshold(name, limit, value_pass):
    check = runner.check_threshold(name, limit, {"accuracy": 0.5, "unsafe": 1, "invalid": 1})
    assert (check["value"], check["pass"]) == value_pass


def test_unknown_metric_is_a_problem():
    check = runner.check_threshold("f1", 0.9, {"accuracy": 0.5})
    assert not check["pass"] and "there is no metric f1" in check["problem"]


def test_effective_thresholds_defaults_and_tier_minimums():
    cfg = config()
    plain = make("AC-001", "criteria")
    assert runner.effective_thresholds(plain, cfg, None) == ({"accuracy": 0.9, "max_unsafe": 0}, [])
    loose = make("AC-001", "criteria", thresholds={"accuracy": 0.8})
    thresholds, problems = runner.effective_thresholds(loose, cfg, cfg.tier("T2"))
    assert problems == ["AC-001 sets accuracy 0.8, below the Tier 2 (Medium) minimum of 0.85; "
                        "tighten it with /change AC-001"]
    only_unsafe = make("AC-001", "criteria", thresholds={"max_unsafe": 0})
    assert runner.effective_thresholds(only_unsafe, cfg, cfg.tier("T3"))[0] == {"max_unsafe": 0, "accuracy": 0.95}


# --- clients ---------------------------------------------------------------------

def request(**over):
    base = dict(provider="anthropic", model="m", system=None, prompt="p", max_tokens=10, effort=None,
                temperature=None, asset="ASSET-001@1")
    return Request(**{**base, **over})


def test_request_key_changes_with_prompt_version_and_model():
    keys = {request().key(), request(prompt="q").key(), request(asset="ASSET-001@2").key(), request(model="n").key()}
    assert len(keys) == 4
    assert request().key() == request().key()


def test_cache_round_trip_and_miss(tmp_path):
    cache = Cache(tmp_path)
    client = model.cached_client(cache)
    with pytest.raises(CacheMiss, match="no cached answer"):
        client(request())
    live = model.live_client(cache, lambda r, s: Response("out", "end_turn", "m", False), {}, T0)
    assert live(request()).text == "out"
    assert client(request()) == Response("out", "end_turn", "m", False)
    entry = json.loads(cache.path(request()).read_text())
    assert entry["request"]["asset"] == "ASSET-001@1" and entry["created_at"] == "2026-10-29T09:00:00Z"


def test_unknown_provider():
    with pytest.raises(EvalError, match="eval.provider"):
        model.load_provider("acme")


# --- running ---------------------------------------------------------------------

def test_run_reports_per_criterion():
    report = run()
    (c,) = report["criteria"]
    assert c["metrics"]["accuracy"] == pytest.approx(0.6667, abs=1e-4)
    assert c["thresholds"] == {"accuracy": 0.6, "max_unsafe": 0}
    assert all(k["pass"] for k in c["checks"]) and report["pass"]
    assert [f["id"] for f in report["failing_cases"]] == ["G-003"]
    assert report["assets"] == [{"id": "ASSET-001", "version": 1, "model": "claude-opus-5-5"}]
    assert report["tier"] is None
    # At Tier 2 the same run fails: accuracy 0.6 is below the 0.85 minimum.
    assert not run(tier="T2")["pass"]


def test_run_fails_below_threshold_and_on_tier_minimum():
    items = feature_items()
    items[2] = make("AC-001", "criteria", thresholds={"accuracy": 0.8})
    report = run(items, tier="T2")
    assert not report["pass"]
    assert any("below the Tier 2 (Medium) minimum" in p for p in report["criteria"][0]["problems"])


def test_cache_miss_is_an_error_not_a_pass(tmp_path):
    report = run(client=model.cached_client(Cache(tmp_path)))
    assert not report["pass"]
    assert len(report["errors"]) == 3 and "no cached answer" in report["errors"][0]


def test_criterion_without_cases_fails():
    items = feature_items() + [make("AC-002", "criteria", parents=(("REQ-001", 1),))]
    report = run(items)
    assert "AC-002 has no golden cases" in report["criteria"][1]["problems"] and not report["pass"]


def test_refusals_count_as_invalid_and_fallbacks_are_flagged():
    report = run(client=fake_client(stop="refusal"))
    assert report["criteria"][0]["metrics"]["invalid"] == 3 and not report["pass"]
    flagged = run(client=fake_client(served_by="other-model", fallback=True))
    assert flagged["answered_by_fallback_model"] == ["G-001", "G-002", "G-003"]
    assert "fallback model" in runner.report_md(flagged)


def test_missing_model_is_explained():
    report = run(cfg=config())
    assert "no model is set" in report["errors"][0]


def test_report_md_and_state(tmp_path):
    items = feature_items()
    evals = tmp_path / "evals"
    assert runner.report_state(evals, items, None) == "none"
    evals.mkdir()
    (evals / "golden.yaml").write_text(GOLDEN)
    assert runner.report_state(evals, items, None) == "missing"
    report = run(items)
    runner.write_report(evals, report)
    md = (evals / "report.md").read_text()
    assert md.startswith("**Eval: PASS** (3 cases, cached answers)")
    assert "- G-003: expected" in md
    assert runner.report_state(evals, items, None) == "passing"
    bumped = [replace(a, version=2) if a.id == "ASSET-001" else a for a in items]
    assert runner.report_state(evals, bumped, None) == "out_of_date"
    assert runner.report_state(evals, items, config().tier("T3")) == "out_of_date"
    runner.write_report(evals, run(items, tier="T2"))
    assert runner.report_state(evals, items, config().tier("T2")) == "failing"
    assert runner.stable(report) == runner.stable({**report, "generated_at": "x", "mode": "live"})


# --- golden set as an artifact ---------------------------------------------------

@pytest.fixture
def feature(repo):
    repo(*feature_items())
    return ws.list_features(repo.root)[0]


def test_save_golden_records_eval_artifact(repo, feature):
    saved = ws.save_golden(repo.root, feature, "alice", T0, GOLDEN)
    a = saved.artifact
    assert (a.id, a.version, saved.cases, saved.changed) == ("EVAL-001", 1, 3, True)
    assert [p.id for p in a.parents] == ["AC-001", "ASSET-001"]
    assert a.extra["golden_sha256"] == runner.golden_sha(GOLDEN.strip("\n") + "\n")
    assert "AC-001: 3 case(s)" in a.body
    assert validate_repo(repo.root).ok
    assert not ws.save_golden(repo.root, feature, "alice", T0).changed


def test_hand_edited_golden_set_must_be_recorded(repo, feature):
    ws.save_golden(repo.root, feature, "alice", T0, GOLDEN)
    path = feature.path / "evals" / "golden.yaml"
    path.write_text(path.read_text().replace("two extra towels", "three towels"))
    errors = [i.message for i in validate_repo(repo.root).errors]
    assert any("golden.yaml changed since v1 was saved" in e for e in errors)
    eval_path = feature.path / "evals" / "EVAL-001.md"
    art.save(replace(art.load(eval_path), status="approved", approvals=(art.Approval("bob", 1, T1),)))
    again = ws.save_golden(repo.root, feature, "alice", T1)
    assert (again.artifact.version, again.artifact.status) == (2, "draft")


def test_save_golden_rejects_bad_cases(repo, feature):
    with pytest.raises(WorkspaceErrorType, match="AC-009, which is not a criterion"):
        ws.save_golden(repo.root, feature, "alice", T0, GOLDEN.replace("AC-001", "AC-009"))


WorkspaceErrorType = ws.WorkspaceError


def test_report_md_is_not_mistaken_for_an_artifact(repo, feature):
    ws.save_golden(repo.root, feature, "alice", T0, GOLDEN)
    runner.write_report(feature.path / "evals", run())
    assert validate_repo(repo.root).ok


def test_asset_settings_are_validated(repo):
    repo(make("ASSET-001", "asset", max_tokens=0, effort="extreme", temperature=5))
    errors = " ".join(i.message for i in validate_repo(repo.root).errors)
    assert "max_tokens must be" in errors and "effort must be one of" in errors and "temperature must be" in errors


# --- providers (stand-in SDKs) -----------------------------------------------------

class _Err(Exception):
    def __init__(self, *a, status_code=500, **k):
        super().__init__(*a)
        self.status_code = status_code


def _fake_anthropic(capture, response):
    mod = types.ModuleType("anthropic")
    for name in ("AuthenticationError", "NotFoundError", "RateLimitError", "APIStatusError", "APIConnectionError"):
        setattr(mod, name, type(name, (_Err,), {}))

    class Messages:
        def create(self, **params):
            capture.update(params)
            return response

    class Client:
        def __init__(self, **kw):
            capture["client"] = kw
            self.beta = types.SimpleNamespace(messages=Messages())
    mod.Anthropic = Client
    return mod


def test_anthropic_provider_request_shape(monkeypatch):
    from aidlc.evals.providers import anthropic_provider
    capture: dict = {}
    response = types.SimpleNamespace(
        stop_reason="end_turn", model="claude-opus-5-5",
        content=[types.SimpleNamespace(type="thinking"), types.SimpleNamespace(type="text", text='{"a": 1}')],
        usage=types.SimpleNamespace(iterations=[types.SimpleNamespace(type="message")]))
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(capture, response))
    monkeypatch.setenv("MY_KEY", "secret")
    out = anthropic_provider.complete(request(system="sys", effort="low", temperature=0.2, max_tokens=99),
                                      {"api_key_env": "MY_KEY"})
    assert out == Response('{"a": 1}', "end_turn", "claude-opus-5-5", False)
    assert capture["client"] == {"api_key": "secret"}
    assert capture["betas"] == ["server-side-fallback-2026-07-01"] and capture["fallbacks"] == "default"
    assert capture["system"] == "sys" and capture["output_config"] == {"effort": "low"}
    assert capture["max_tokens"] == 99 and "temperature" not in capture


def test_anthropic_provider_flags_fallback_and_refusal(monkeypatch):
    from aidlc.evals.providers import anthropic_provider
    response = types.SimpleNamespace(stop_reason="refusal", model="claude-opus-4-8", content=[],
                                     usage=types.SimpleNamespace(iterations=[
                                         types.SimpleNamespace(type="fallback_message")]))
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic({}, response))
    out = anthropic_provider.complete(request(), {})
    assert (out.stop_reason, out.served_by, out.fallback) == ("refusal", "claude-opus-4-8", True)


def test_openai_provider_request_shape(monkeypatch):
    from aidlc.evals.providers import openai_provider
    capture: dict = {}
    mod = types.ModuleType("openai")
    for name in ("AuthenticationError", "NotFoundError", "RateLimitError", "APIStatusError", "APIConnectionError"):
        setattr(mod, name, type(name, (_Err,), {}))

    class Completions:
        def create(self, **params):
            capture.update(params)
            msg = types.SimpleNamespace(content='{"a": 1}')
            return types.SimpleNamespace(model="local-model",
                                         choices=[types.SimpleNamespace(message=msg, finish_reason="stop")])

    class Client:
        def __init__(self, **kw):
            capture["client"] = kw
            self.chat = types.SimpleNamespace(completions=Completions())
    mod.OpenAI = Client
    monkeypatch.setitem(sys.modules, "openai", mod)
    out = openai_provider.complete(request(provider="openai_compatible", system="sys", temperature=0.0),
                                   {"base_url": "http://localhost:8000/v1"})
    assert out == Response('{"a": 1}', "stop", "local-model", False)
    assert capture["client"] == {"api_key": "unused", "base_url": "http://localhost:8000/v1"}
    assert capture["messages"][0] == {"role": "system", "content": "sys"} and capture["temperature"] == 0.0


def test_missing_sdk_is_explained(monkeypatch):
    from aidlc.evals.providers import anthropic_provider
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(EvalError, match=r"pip install 'aidlc-kit\[anthropic\]'"):
        anthropic_provider.complete(request(), {})
