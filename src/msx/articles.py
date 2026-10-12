"""Read and write Markdown articles with YAML frontmatter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from .project import iso, parse_iso

REQUIRED_FIELDS = ("title", "slug", "model_id", "status", "created", "updated", "sources")
ARTICLE_STATUSES = ("draft", "approved", "published")
VISIBLE_STATUSES = ("approved", "published")


class ArticleError(Exception):
    pass


@dataclass
class Article:
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @property
    def slug(self) -> str:
        return str(self.meta.get("slug") or self.path.stem)

    @property
    def status(self) -> str:
        return str(self.meta.get("status", ""))


def _normalize(meta: dict[str, Any]) -> dict[str, Any]:
    """Turn YAML-parsed timestamps back into canonical ISO strings."""
    for key in ("created", "updated", "published_at"):
        value = meta.get(key)
        if isinstance(value, (datetime, date)):
            meta[key] = iso(parse_iso(value))
        elif isinstance(value, str) and value:
            try:
                meta[key] = iso(parse_iso(value))
            except ValueError:
                pass  # left as-is; validation reports it
    return meta


def parse_article(path: Path, text: str) -> Article:
    if not text.startswith("---\n"):
        raise ArticleError(f"{path.name}: missing YAML frontmatter (file must start with '---')")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ArticleError(f"{path.name}: frontmatter is not closed with '---'")
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        raise ArticleError(f"{path.name}: invalid YAML frontmatter: {exc}") from exc
    if not isinstance(meta, dict):
        raise ArticleError(f"{path.name}: frontmatter must be a mapping")
    return Article(path=path, meta=_normalize(meta), body=text[end + 5:])


def read_article(path: Path) -> Article:
    return parse_article(path, path.read_text(encoding="utf-8"))


def write_article(article: Article) -> None:
    header = yaml.safe_dump(article.meta, sort_keys=False, allow_unicode=True)
    article.path.parent.mkdir(parents=True, exist_ok=True)
    article.path.write_text(f"---\n{header}---\n{article.body}", encoding="utf-8")


def list_articles(directory: Path) -> list[Article]:
    if not directory.exists():
        return []
    return [read_article(p) for p in sorted(directory.glob("*.md"))]
