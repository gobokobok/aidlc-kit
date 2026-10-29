"""Render the viewer into a folder of static files."""

import shutil
from datetime import datetime
from pathlib import Path

import jinja2

from aidlc.site.model import Site, build_site

TEMPLATES = Path(__file__).parent / "templates"


def environment() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES), autoescape=True,
        undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True)


def render(site: Site) -> dict[str, str]:
    """Every page, keyed by its path inside the output folder."""
    env = environment()
    pages: dict[str, str] = {}

    def page(path: str, template: str, **ctx) -> None:
        depth = path.count("/")
        ctx.setdefault("wide", False)
        pages[path] = env.get_template(template).render(site=site, root="../" * depth, **ctx)

    page("index.html", "index.html", section="features")
    page("audit.html", "audit.html", section="audit")
    page("about.html", "about.html", section="about")
    for f in site.features:
        base = f"features/{f.id}"
        page(f"{base}/index.html", "feature.html", section="features", f=f)
        page(f"{base}/trace.html", "trace.html", section="features", f=f, wide=True)
        page(f"{base}/evals.html", "evals.html", section="features", f=f)
    return pages


def write(out: Path, pages: dict[str, str]) -> None:
    if out.exists():
        shutil.rmtree(out)
    for path, html in pages.items():
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
    shutil.copy(TEMPLATES / "style.css", out / "style.css")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def build(root: Path, out: Path, tags: list[str], now: datetime, commit: str | None = None,
          source_url: str | None = None, source_subdir: str = "") -> list[str]:
    """Build the site into `out`; returns the files written."""
    pages = render(build_site(root, tags, now, commit, source_url, source_subdir))
    write(out, pages)
    return sorted([*pages, "style.css"])
