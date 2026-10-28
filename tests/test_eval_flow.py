"""/eval end to end: real Git, a fake model provider, no API calls."""

import json

from aidlc.evals import model
from aidlc.evals.model import Response

from flowkit import ANSWERS, git, log
from test_evals import GOLDEN, PROMPT_BODY

ANSWER = {"leak": ("maintenance", True), "towel": ("housekeeping", False), "breakfast": ("food_and_beverage", False)}


def provider(request, settings):
    calls.append(request)
    for word, (category, urgent) in ANSWER.items():
        if word in request.prompt.lower():
            return Response(json.dumps({"category": category, "urgent": urgent}), "end_turn", request.model)
    return Response("unsure", "end_turn", request.model)


calls: list = []


def setup_feature(env, monkeypatch):
    calls.clear()
    monkeypatch.setattr(model, "load_provider", lambda name: provider)
    with open(env.repo / "aidlc.yaml", "a") as f:
        f.write("eval:\n  provider: anthropic\n  model: claude-opus-5-5\n  api_key_env: ANTHROPIC_API_KEY\n")
    git(env.repo, "commit", "-qam", "eval settings")
    git(env.repo, "push", "-q")
    env("new-feature", "--title", "Guest request triage", *ANSWERS)
    env("discover", "--title", "Guests wait too long")
    env("requirement", "--title", "Route requests")
    env("criteria", "--title", "Routing accuracy", "--threshold", "accuracy=0.9", "--threshold", "max_unsafe=0")
    code, out = env("asset", "--title", "Triage prompt", "--body-file", "-", stdin=PROMPT_BODY)
    assert code == 0 and "Next: run /eval" in out


def test_eval_journey(env, monkeypatch):
    setup_feature(env, monkeypatch)
    assert env("status")[1].strip().endswith("Run /eval to build the golden set and test the prompt against the criteria.")

    code, out = env("golden", "--file", "-", stdin=GOLDEN)
    assert out.strip() == "Saved the golden set: 3 cases, recorded as EVAL-001 v1. Next: run /eval."
    assert log(env.repo)[0] == "[FEAT-001][EVAL-001 v1] Save golden set (3 cases)"

    code, out = env("eval")
    assert code == 1
    assert "3 case(s) have no saved answer for this exact prompt yet; a live run (/eval --live)" in out
    assert calls == []  # cached mode never calls the model

    code, out = env("eval", "--live")
    assert code == 0, out
    assert "Evals pass: AC-001 accuracy 1.0 (needs ≥ 0.9), unsafe 0 (needs ≤ 0)." in out
    assert len(calls) == 3 and calls[0].model == "claude-opus-5-5" and calls[0].asset == "ASSET-001@1"
    assert log(env.repo)[0] == "[FEAT-001] Eval run (live): pass"
    assert len(list(env.repo.glob("features/*/evals/cache/*.json"))) == 3

    code, out = env("eval", "--check", "--all")
    assert code == 0 and "eval: 1 feature(s) checked, all passing." in out
    assert len(calls) == 3  # the check uses saved answers only

    assert "Evals: passing" in env("status")[1]
    code, out = env("submit")
    create = next(c for c in env.gh.calls if c[1:3] == ["pr", "create"])
    assert "**Eval: PASS** (3 cases, live answers, tier T2)" in create[create.index("--body") + 1]

    # Changing the prompt makes the saved answers and the report out of date.
    asset = next(env.repo.glob("features/*/assets/ASSET-001.md"))
    env("change", "ASSET-001", "--body-file", "-", stdin=PROMPT_BODY.replace("Classify", "Sort"))
    code, out = env("eval", "--check", "--all")
    assert code == 1 and "report.json does not match a fresh run" in out
    assert "the prompt, criteria or golden set changed" in env("status")[1]
    assert asset.is_file()
    code, out = env("eval", "--live")
    assert code == 0 and log(env.repo)[0] == "[FEAT-001][EVAL-001 v2] Eval run (live): pass"
    assert len(calls) == 6 and calls[-1].asset == "ASSET-001@2"
    assert env("eval", "--check", "--all")[0] == 0


def test_tier_minimum_fails_the_eval(env, monkeypatch):
    setup_feature(env, monkeypatch)
    env("change", "AC-001", "--threshold", "accuracy=0.8")
    env("golden", "--file", "-", stdin=GOLDEN)
    code, out = env("eval", "--live")
    assert code == 1
    assert "AC-001 sets accuracy 0.8, below the Tier 2 (Medium) minimum of 0.85" in out
