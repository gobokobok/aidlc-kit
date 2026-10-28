from pathlib import Path

import pytest

from aidlc.config import load_config, parse_config

from conftest import CONFIG_YAML

ROOT = Path(__file__).resolve().parents[1]


def test_repo_config_is_valid():
    cfg, issues = load_config(ROOT)
    assert issues == []
    assert cfg.tier("T2").extra_reviewers == ("risk_reviewer",)


def test_parsed_config():
    cfg, issues = parse_config(CONFIG_YAML)
    assert issues == []
    assert cfg.people["alice"] == ("pm",)
    assert cfg.review_routing["discovery"] == ("pm_peer",)
    assert list(cfg.risk_tiers) == ["T1", "T2", "T3"]
    t3 = cfg.tier("T3")
    assert (t3.display, t3.required_artifacts, t3.human_in_loop) == (
        "Tier 3 (High)", ("privacy_assessment",), True)
    assert t3.min_thresholds == {"accuracy": 0.95}


def test_missing_config_gives_defaults(tmp_path):
    cfg, issues = load_config(tmp_path)
    assert issues == []
    assert cfg.display_name == "AIDLC Kit"
    assert list(cfg.risk_tiers) == ["T1", "T2", "T3"]


def messages(text):
    return [(i.severity, i.message) for i in parse_config(text)[1]]


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("people: {'not ok!': [pm]}", "not a GitHub username"),
        ("people: {alice: pm}", "list of role names"),
        ("people: {alice: [pm_peer]}", "cannot be assigned"),
        ("review_routing: {story: [pm]}", "not an artifact type"),
        ("review_routing: {discovery: []}", "non-empty list"),
        ("risk_tiers: {T1: {label: Low}}", "must define T2"),
        ("risk_tiers: {T1: {label: Low}, T2: {label: M}, T3: {label: H}, High: {label: X}}", "named like T1"),
        ("risk_tiers: {T1: {label: Low, colour: red}, T2: {label: M}, T3: {label: H}}", "unknown setting"),
        ("risk_tiers: {T1: {label: Low, required_artifacts: [memo]}, T2: {label: M}, T3: {label: H}}",
         "required_artifacts"),
        ("risk_tiers: {T1: {label: Low, min_thresholds: {accuracy: 3}}, T2: {label: M}, T3: {label: H}}",
         "between 0 and 1"),
        ("thresholds: {accuracy: 2}", "between 0 and 1"),
    ],
)
def test_config_errors(text, fragment):
    msgs = messages(text)
    assert any(sev == "error" and fragment in m for sev, m in msgs), msgs


def test_role_nobody_holds_warns():
    msgs = messages("people: {alice: [pm], bob: [pm]}\nreview_routing: {asset: [tech_reviewer]}")
    assert msgs == [("warning", "asset artifacts need role tech_reviewer, but nobody in `people` has it")]


def test_pm_peer_needs_two_pms():
    msgs = messages("people: {alice: [pm]}\nreview_routing: {discovery: [pm_peer]}")
    assert len(msgs) == 1 and "fewer than two people have role pm" in msgs[0][1]
