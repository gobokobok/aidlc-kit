"""The read-only viewer: what it shows, that it escapes content, and that
every page is plain static HTML."""

import io
import re
from dataclasses import replace
from pathlib import Path

import pytest

from aidlc.cli import main
from aidlc.site import build as site_build
from aidlc.site.graph import layout
from aidlc.site.model import build_site

from conftest import T1, approved_chain

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "guest-request-triage"


def pages(root: Path, tags=(), url=None) -> dict[str, str]:
    return site_build.render(build_site(root, list(tags), T1, "abcdef1234567", url))


def test_pages_exist_for_each_feature(repo):
    root = repo(*approved_chain())
    assert set(pages(root)) == {
        "index.html", "audit.html", "about.html", "features/FEAT-001/index.html", "features/FEAT-001/trace.html",
        "features/FEAT-001/evals.html"}


def test_overview_shows_tier_stage_and_blockers_for_an_unfinished_feature(repo):
    root = repo(*approved_chain())
    index = pages(root)["index.html"]
    assert "Tier 2 (Medium)" in index and "Guest request" not in index
    assert "FEAT-001" in index and "in the way of handoff" in index
    detail = pages(root)["features/FEAT-001/index.html"]
    assert "Blocking handoff" in detail
    assert "there is no asset yet" in detail          # the real gate's wording
    assert "Handed off" not in detail


def test_handed_off_feature_has_no_blockers(repo):
    root = repo(*approved_chain())
    detail = pages(root, tags=["FEAT-001/handoff-v1"])["features/FEAT-001/index.html"]
    assert "Nothing: this feature was handed off." in detail
    assert "Handed off as HND-001" in detail


def test_reviewer_markers_show_who_approved_and_who_is_pending(repo):
    items = approved_chain()
    req = replace(items[2], approvals=tuple(a for a in items[2].approvals if a.by != "priya"))
    root = repo(items[0], items[1], req, items[3])
    html = pages(root)["features/FEAT-001/index.html"]
    block = html[html.index('id="REQ-001"'):html.index('id="AC-001"')]
    assert "✓" in block and "Ops (bob)" in block and "Risk (sam)" in block
    assert re.search(r'class="wait">.*?….*?Tech \(priya\)', block, re.S)   # pending is marked, not hidden
    assert "added by" not in block and "· T2" in block                    # the tier's role says so


def test_content_is_escaped(repo):
    items = approved_chain()
    items[1] = replace(items[1], title='<script>alert("x")</script> Guests')
    root = repo(*items)
    for html in pages(root).values():
        assert "<script>alert" not in html
    assert "&lt;script&gt;" in pages(root)["features/FEAT-001/index.html"]


def test_pages_are_static_and_work_at_phone_width(repo):
    root = repo(*approved_chain())
    for path, html in pages(root).items():
        assert "<script" not in html, path
        assert 'name="viewport"' in html and 'name="color-scheme"' in html
        assert 'href="/' not in html and 'src="/' not in html, f"{path} links from the site root"
    css = (ROOT / "aidlc/site/templates/style.css").read_text()
    assert "prefers-color-scheme: dark" in css and "max-width:640px" in css
    depth = pages(root)["features/FEAT-001/trace.html"]
    assert 'href="../../style.css"' in depth


def test_source_links_only_when_an_address_is_given(repo):
    root = repo(*approved_chain())
    plain = pages(root)["features/FEAT-001/index.html"]
    assert "/blob/main/" not in plain
    linked = pages(root, url="https://github.com/acme/kit")["features/FEAT-001/index.html"]
    assert 'href="https://github.com/acme/kit/blob/main/features/FEAT-001-guest-triage/requirements/REQ-001.md"' in linked


def test_trace_graph_layout_follows_parent_links():
    items = approved_chain()
    graph = layout(items[1:], [])
    ids = [n["id"] for n in graph["nodes"]]
    assert ids == ["DISC-001", "REQ-001", "AC-001"]
    x = {n["id"]: n["x"] for n in graph["nodes"]}
    assert x["DISC-001"] < x["REQ-001"] < x["AC-001"]                 # discovery on the left
    assert {(e["from"], e["to"]) for e in graph["edges"]} == {("REQ-001", "DISC-001"), ("AC-001", "REQ-001")}


def test_trace_page_has_the_graph_and_text_chains(repo):
    root = repo(*approved_chain())
    html = pages(root)["features/FEAT-001/trace.html"]
    assert "<svg" in html and "AC-001 builds on REQ-001" in html
    chain = re.search(r'class="card chain">(.*?)</div>', html, re.S).group(1)
    assert re.sub(r"<[^>]+>", " ", chain).split() == ["AC-001", "→", "REQ-001", "→", "DISC-001"]


def test_audit_page_lists_entries_with_links(repo):
    from aidlc import audit
    root = repo(*approved_chain())
    audit.append(root, [{"at": "2026-10-29T10:00:00Z", "feature": "FEAT-001", "id": "REQ-001", "version": 1,
                         "status": "approved", "actor": "alice", "approvers": ["bob", "priya", "sam"],
                         "tier": "T2", "roles_satisfied": ["ops_reviewer", "tech_reviewer", "risk_reviewer"],
                         "commit": "abc1234def", "pr": 7}])
    html = pages(root, url="https://github.com/acme/kit")["audit.html"]
    assert "REQ-001 v1" in html and "approved by bob, priya, sam" in html
    assert 'href="https://github.com/acme/kit/pull/7"' in html and "abc1234" in html


def test_eval_page_without_a_report_says_what_to_do(repo):
    root = repo(*approved_chain())
    assert "Run /eval" in pages(root)["features/FEAT-001/evals.html"]


def test_empty_repository_builds(tmp_path):
    (tmp_path / "aidlc.yaml").write_text("display_name: Empty\n")
    html = pages(tmp_path)
    assert set(html) == {"index.html", "audit.html", "about.html"} and "No features yet" in html["index.html"]


def test_cli_builds_the_site_into_a_folder(repo, tmp_path):
    root = repo(*approved_chain())
    out = io.StringIO()
    assert main(["--root", str(root), "site", "build", "--out", "viewer"], now=T1, out=out) == 0
    assert out.getvalue().startswith("Built the viewer site: 7 files in viewer.")
    assert (root / "viewer" / "index.html").is_file() and (root / "viewer" / "style.css").is_file()
    assert (root / "viewer" / ".nojekyll").is_file()


# --- the worked example ------------------------------------------------------

@pytest.fixture(scope="module")
def example_pages():
    return pages(EXAMPLE, tags=["FEAT-001/handoff-v1"], url="https://github.com/gobokobok/aidlc-kit")


def test_example_appears_on_the_site(example_pages):
    index = example_pages["index.html"]
    assert "Guest request triage" in index and "Tier 2 (Medium)" in index and "handed off" in index
    detail = example_pages["features/FEAT-001/index.html"]
    assert "Handed off as HND-001" in detail and "Risk (alexdanm-oss)" in detail
    evals = example_pages["features/FEAT-001/evals.html"]
    assert "20 cases" in evals and "urgent recall" in evals
    assert "AC-001 builds on REQ-001" in example_pages["features/FEAT-001/trace.html"]
    assert "T-005 builds on AC-002" in example_pages["features/FEAT-001/trace.html"]
    assert "approved by alexdanm-oss" in example_pages["audit.html"]


def test_about_page_is_generic_and_links_only_what_it_knows(repo):
    root = repo(*approved_chain())
    plain = pages(root)["about.html"]
    assert "About this site" in plain and "FEAT-001" in plain and "The repository" not in plain
    linked = pages(root, url="https://github.com/acme/kit")["about.html"]
    assert 'href="https://github.com/acme/kit"' in linked
    assert "gobokobok" not in linked and "/pull/" not in linked        # no kit-specific text in the shipped page
    assert 'aria-current="page">About' in linked


def test_links_point_into_a_subfolder_and_tags_can_come_from_a_file(repo, tmp_path):
    root = repo(*approved_chain())
    site = build_site(root, ["FEAT-001/handoff-v1"], T1, None, "https://github.com/acme/kit", "examples/demo/")
    html = site_build.render(site)["features/FEAT-001/index.html"]
    assert "blob/main/examples/demo/features/FEAT-001-guest-triage/requirements/REQ-001.md" in html
    tags = tmp_path / "tags.txt"
    tags.write_text("FEAT-001/handoff-v1\n\n")
    out = io.StringIO()
    code = main(["--root", str(root), "site", "build", "--out", "viewer", "--tags-file", str(tags),
                 "--source-subdir", "examples/demo"], now=T1, out=out)
    assert code == 0
    assert "Handed off as HND-001" in (root / "viewer/features/FEAT-001/index.html").read_text()
