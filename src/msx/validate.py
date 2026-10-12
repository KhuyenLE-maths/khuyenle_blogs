"""`msx approve`: validate an article and mark it approved."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from . import db
from .articles import ARTICLE_STATUSES, REQUIRED_FIELDS, Article, read_article, write_article
from .project import Project, iso, utc_now

PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME)\b|lorem ipsum", re.IGNORECASE)


def validate_article(project: Project, conn: sqlite3.Connection, article: Article) -> list[str]:
    """Return every problem found; an empty list means the article may be approved."""
    errors: list[str] = []
    meta = article.meta

    if project.config["publishing"].get("paused"):
        errors.append("publishing is paused (publishing.paused = true in config.toml)")

    missing = [key for key in REQUIRED_FIELDS if key != "sources" and not meta.get(key)]
    if missing:
        errors.append("frontmatter is missing: " + ", ".join(missing))

    if meta.get("status") and meta["status"] not in ARTICLE_STATUSES:
        errors.append(f"status must be one of {', '.join(ARTICLE_STATUSES)}")

    if meta.get("slug") and meta["slug"] != article.path.stem:
        errors.append(f"slug '{meta['slug']}' does not match file name '{article.path.stem}.md'")

    model_id = meta.get("model_id")
    if model_id and db.get_model(conn, str(model_id)) is None:
        errors.append(f"model_id '{model_id}' is not in the database")

    sources = meta.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources is empty: list at least one source URL")
    else:
        bad = [s for s in sources if not (isinstance(s, str) and s.startswith(("https://", "http://")))]
        if bad:
            errors.append("sources must be http(s) URLs: " + ", ".join(map(str, bad)))

    for number, line in enumerate(article.body.splitlines(), start=1):
        match = PLACEHOLDER.search(line)
        if match:
            errors.append(f"placeholder text '{match.group(0)}' on body line {number}")

    return errors


def approve(
    project: Project, conn: sqlite3.Connection, slug: str, *, now: datetime | None = None
) -> list[str]:
    path = project.articles_dir / f"{slug}.md"
    if not path.exists():
        return [f"no article at content/articles/{slug}.md"]
    article = read_article(path)
    errors = validate_article(project, conn, article)
    if errors:
        return errors
    article.meta["status"] = "approved"
    article.meta["updated"] = iso(now or utc_now())
    write_article(article)
    return []
