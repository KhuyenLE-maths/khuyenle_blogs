"""`msx build`: render the static site from the database and approved articles."""

from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markdown_it import MarkdownIt

from . import db
from .articles import VISIBLE_STATUSES, Article, list_articles
from .estimate import EXCLUSIONS, FORMULA, budget_gb, hardware_fit
from .facts import CATEGORY_LABELS, STATUS_LABELS, UNKNOWN, fact_rows
from .hf import model_page_url
from .project import Project, parse_iso, utc_now


@dataclass
class BuildResult:
    site_dir: Path
    models: int
    articles: int
    pages: int


def markdown_renderer() -> MarkdownIt:
    # Raw HTML is disabled; markdown-it also refuses javascript:/vbscript:/data: links.
    return MarkdownIt("commonmark", {"html": False}).enable("table")


def _environment(project: Project) -> Environment:
    env = Environment(
        loader=FileSystemLoader(project.templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["STATUS_LABELS"] = STATUS_LABELS
    return env


def _summary(body: str, limit: int = 220) -> str:
    for line in body.splitlines():
        text = line.strip()
        if text and not text.startswith(("#", "|", "-", ">")):
            plain = re.sub(r"[`*_\[\]\\]", "", text)
            plain = re.sub(r"\(https?://[^)]*\)", "", plain)
            return plain if len(plain) <= limit else plain[: limit - 1].rstrip() + "…"
    return ""


def _model_view(project: Project, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    claims = db.current_claims(conn, row["id"])
    facts = fact_rows(claims)
    by_field = {f["field"]: f for f in facts}
    params = by_field["parameters"]["value"]
    created = by_field["created_at"]["value"]
    return {
        "id": row["id"],
        "repo_id": row["repo_id"],
        "slug": row["slug"],
        "author": row["author"],
        "category": row["category"],
        "category_label": CATEGORY_LABELS.get(row["category"], row["category"]),
        "page_url": model_page_url(row["repo_id"]),
        "last_checked_at": row["last_checked_at"],
        "created_sort": created or row["first_seen_at"],
        "created_display": (created or "")[:10] or UNKNOWN,
        "facts": facts,
        "parameters_display": by_field["parameters"]["display"],
        "license_display": by_field["license"]["display"],
        "unknown_labels": [f["label"] for f in facts if f["status"] == "unknown"],
        "hardware": hardware_fit(params, project.hardware) if params else [],
        "article": None,
    }


def _article_view(article: Article, md: MarkdownIt) -> dict[str, Any]:
    updated = parse_iso(article.meta["updated"])
    return {
        "slug": article.slug,
        "title": str(article.meta["title"]),
        "model_id": str(article.meta["model_id"]),
        "status": article.status,
        "updated": article.meta["updated"],
        "updated_date": updated.date().isoformat(),
        "rfc822": format_datetime(updated),
        "sources": [str(s) for s in article.meta.get("sources") or []],
        "summary": _summary(article.body),
        "html": md.render(article.body),
    }


def build(project: Project, conn: sqlite3.Connection, *, now: datetime | None = None) -> BuildResult:
    now = now or utc_now()
    env = _environment(project)
    md = markdown_renderer()

    base_url = str(project.config["site"]["base_url"]).rstrip("/")
    base_path = urlparse(base_url).path.rstrip("/")
    targets = [
        {"name": name, "label": t["label"], "budget": round(budget_gb(t), 1)}
        for name, t in project.hardware.items()
    ]

    models = [_model_view(project, conn, row) for row in db.list_models(conn)]
    models.sort(key=lambda m: m["created_sort"], reverse=True)
    by_model_id = {m["id"]: m for m in models}

    articles = [
        _article_view(a, md)
        for a in list_articles(project.articles_dir)
        if a.status in VISIBLE_STATUSES
    ]
    articles.sort(key=lambda a: a["updated"], reverse=True)
    for article in articles:
        model = by_model_id.get(article["model_id"])
        article["model"] = model
        if model is not None and model["article"] is None:
            model["article"] = article

    out = project.site_dir.resolve()
    if out.parent != project.root.resolve() or out.name != "site":
        raise RuntimeError(f"refusing to clean unexpected build directory {out}")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    common = {
        "site_name": project.config["site"]["name"],
        "base_url": base_url,
        "base_path": base_path,
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "targets": targets,
        "unknown": UNKNOWN,
    }
    pages: list[tuple[str, str, dict[str, Any]]] = [
        ("/", "index.html", {"articles": articles[:10], "models": models[:20],
                              "model_count": len(models)}),
        ("/models/", "models.html", {"models": models}),
        ("/methodology/", "methodology.html", {"formula": FORMULA, "exclusions": EXCLUSIONS}),
    ]
    pages += [(f"/models/{m['slug']}/", "model.html", {"model": m}) for m in models]
    pages += [(f"/blog/{a['slug']}/", "article.html", {"article": a}) for a in articles]

    for page_path, template, context in pages:
        html = env.get_template(template).render(**common, **context, page_path=page_path)
        target = out / page_path.strip("/") / "index.html" if page_path != "/" else out / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")

    (out / "sitemap.xml").write_text(
        env.get_template("sitemap.xml").render(
            **common, urls=[p for p, _, _ in pages], lastmod=now.date().isoformat()
        ),
        encoding="utf-8",
    )
    (out / "feed.xml").write_text(
        env.get_template("feed.xml").render(
            **common, articles=articles, build_rfc822=format_datetime(now)
        ),
        encoding="utf-8",
    )
    shutil.copyfile(project.templates_dir / "style.css", out / "style.css")
    return BuildResult(site_dir=out, models=len(models), articles=len(articles), pages=len(pages))
