"""`msx draft`: write a deterministic, fact-only article draft for one model."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import db
from .articles import Article, read_article, write_article
from .estimate import EXCLUSIONS, FORMULA, budget_gb, hardware_fit
from .facts import CATEGORY_LABELS, UNKNOWN, fact_rows, format_value, md_escape
from .hf import model_page_url
from .project import Project, iso, utc_now


class DraftError(Exception):
    pass


@dataclass
class DraftResult:
    path: Path
    created: bool
    changes: list[dict[str, Any]] = field(default_factory=list)


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def render_body(project: Project, model: sqlite3.Row, claims: dict[str, dict[str, Any]]) -> str:
    rows = fact_rows(claims)
    by_field = {row["field"]: row for row in rows}
    category = CATEGORY_LABELS.get(model["category"], model["category"])

    intro = [
        f"`{model['repo_id']}` is a Hugging Face repository from {md_escape(model['author'])}, "
        f"discovered in the {md_escape(category)} category.",
    ]
    created = by_field["created_at"]
    if created["value"] is not None:
        intro.append(f"It was created on {md_escape(str(created['value'])[:10])}.")
    license_row = by_field["license"]
    if license_row["value"] is not None:
        intro.append(f"Its declared license is {md_escape(license_row['display'])}.")
    else:
        intro.append(f"Its license is {UNKNOWN.lower()}.")
    intro.append(
        "Every fact below comes from the publisher's own metadata on the Hub "
        "and is marked with its verification status."
    )

    facts = _table(
        ["Field", "Value", "Status", "Source"],
        [
            [
                row["label"],
                md_escape(row["display"]),
                row["status_label"],
                f"[{row['source_name']}]({row['source_url']})" if row["source_url"] else "",
            ]
            for row in rows
        ],
    )

    params = by_field["parameters"]
    targets = project.hardware
    if params["value"] is not None and targets:
        header = ["Precision", "Weights (GB)"] + [
            f"{md_escape(t['label'])} (budget {budget_gb(t):.1f} GB)" for t in targets.values()
        ]
        fit_rows = [
            [r["precision"], f"{r['weights_gb']:.2f}"]
            + ["likely fits" if r["fits"][name] else "does not fit" for name in targets]
            for r in hardware_fit(params["value"], targets)
        ]
        hardware = "\n\n".join([
            f"Parameters: {format_value('parameters', params['value'])}, "
            f"{params['status_label']}.",
            _table(header, fit_rows),
            f"Status: estimated. Formula: {FORMULA}. {EXCLUSIONS}",
        ])
    else:
        hardware = f"Cannot be estimated: the parameter count is {UNKNOWN}."

    unknown = [row["label"] for row in rows if row["status"] == "unknown"]
    not_verified = (
        "\n".join(f"- {label}" for label in unknown) if unknown else "- Nothing: every field has a value."
    )

    return "\n".join([
        "",
        " ".join(intro),
        "",
        "## Facts",
        "",
        facts,
        "",
        "## Hardware fit (estimate)",
        "",
        hardware,
        "",
        "## Not yet verified",
        "",
        not_verified,
        "",
    ])


def draft(
    project: Project, conn: sqlite3.Connection, model_ref: str, *, now: datetime | None = None
) -> DraftResult:
    model = db.get_model(conn, model_ref)
    if model is None:
        raise DraftError(f"Unknown model {model_ref!r}. Run 'msx discover' first, or check the id.")
    path = project.articles_dir / f"{model['slug']}.md"
    if path.exists():
        existing = read_article(path)
        since = str(existing.meta.get("updated") or existing.meta.get("created") or "")
        changes = db.material_changes_since(conn, model["id"], since) if since else []
        return DraftResult(path=path, created=False, changes=changes)

    claims = db.current_claims(conn, model["id"])
    sources = [model_page_url(model["repo_id"])]
    sources += sorted({c["source_url"] for c in claims.values() if c["source_url"]} - set(sources))
    stamp = iso(now or utc_now())
    article = Article(
        path=path,
        meta={
            "title": model["repo_id"],
            "slug": model["slug"],
            "model_id": model["id"],
            "status": "draft",
            "created": stamp,
            "updated": stamp,
            "sources": sources,
        },
        body=render_body(project, model, claims),
    )
    write_article(article)
    return DraftResult(path=path, created=True)
