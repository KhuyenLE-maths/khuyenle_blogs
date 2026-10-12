"""Project root discovery, configuration loading, and small shared helpers."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

CONFIG_NAME = "config.toml"


class ProjectError(Exception):
    """Raised when the project layout or configuration is invalid."""


@dataclass(frozen=True)
class Project:
    root: Path
    config: dict[str, Any]

    @property
    def db_path(self) -> Path:
        return self.root / "data" / "msx.sqlite"

    @property
    def migrations_dir(self) -> Path:
        return self.root / "migrations"

    @property
    def templates_dir(self) -> Path:
        return self.root / "templates"

    @property
    def articles_dir(self) -> Path:
        return self.root / "content" / "articles"

    @property
    def site_dir(self) -> Path:
        return self.root / "site"

    @property
    def hardware(self) -> dict[str, dict[str, Any]]:
        return self.config.get("hardware", {})


def find_root(start: Path | None = None) -> Path:
    """Return the nearest directory at or above `start` that contains config.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_NAME).is_file():
            return candidate
    raise ProjectError(f"No {CONFIG_NAME} found in {current} or any parent directory.")


def load_project(start: Path | None = None) -> Project:
    root = find_root(start)
    try:
        with open(root / CONFIG_NAME, "rb") as fh:
            config = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ProjectError(f"{CONFIG_NAME} is not valid TOML: {exc}") from exc
    validate_config(config)
    return Project(root=root, config=config)


_REQUIRED_KEYS = {
    "site": ("name", "base_url"),
    "discover": ("authors", "categories", "lookback_days", "max_models", "exclude_name_patterns"),
    "publishing": ("paused",),
}


def validate_config(config: dict[str, Any]) -> None:
    problems: list[str] = []
    for section, keys in _REQUIRED_KEYS.items():
        values = config.get(section)
        if not isinstance(values, dict):
            problems.append(f"missing section [{section}]")
            continue
        problems.extend(f"missing {section}.{key}" for key in keys if key not in values)
    for name, target in (config.get("hardware") or {}).items():
        for key in ("label", "memory_gb", "usable_fraction"):
            if key not in target:
                problems.append(f"missing hardware.{name}.{key}")
    if problems:
        raise ProjectError(f"{CONFIG_NAME}: " + "; ".join(problems))


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(moment: datetime) -> str:
    """Canonical timestamp format used everywhere: 2026-10-12T08:50:00+00:00."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | datetime | date) -> datetime:
    """Parse ISO 8601 strings (including HF's '...000Z') and YAML-parsed datetimes."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime(value.year, value.month, value.day)
    else:
        moment = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        raise ProjectError(f"Cannot build a slug from {text!r}")
    return slug
