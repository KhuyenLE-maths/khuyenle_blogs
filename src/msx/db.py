"""SQLite access: migrations, models, sources, append-only claims, and runs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .project import ProjectError, slugify

MATERIAL_FIELDS = ("license", "parameters", "gated")
CLAIM_STATUSES = ("publisher_declared", "independently_measured", "estimated", "unknown")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection, migrations_dir: Path) -> int:
    """Apply numbered migrations newer than PRAGMA user_version, each in one transaction."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    files = sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise ProjectError(f"No migrations found in {migrations_dir}")
    for path in files:
        number = int(path.name[:3])
        if number <= current:
            continue
        script = path.read_text(encoding="utf-8")
        conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
        current = number
    return current


def open_db(project: Any) -> sqlite3.Connection:
    conn = connect(project.db_path)
    migrate(conn, project.migrations_dir)
    return conn


def encode(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


# --- models -----------------------------------------------------------------


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug, n = base, 2
    while conn.execute("SELECT 1 FROM models WHERE slug = ?", (slug,)).fetchone():
        slug, n = f"{base}-{n}", n + 1
    return slug


def upsert_model(
    conn: sqlite3.Connection,
    *,
    repo_id: str,
    author: str,
    category: str,
    now: str,
    downloads: int | None,
    likes: int | None,
) -> bool:
    """Insert a new model or refresh its counters. Returns True when the model is new."""
    model_id = repo_id.lower()
    if conn.execute("SELECT 1 FROM models WHERE id = ?", (model_id,)).fetchone():
        conn.execute(
            "UPDATE models SET last_checked_at = ?, downloads = ?, likes = ? WHERE id = ?",
            (now, downloads, likes, model_id),
        )
        return False
    conn.execute(
        "INSERT INTO models (id, repo_id, slug, author, category, first_seen_at,"
        " last_checked_at, downloads, likes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (model_id, repo_id, _unique_slug(conn, slugify(repo_id)), author, category,
         now, now, downloads, likes),
    )
    return True


def get_model(conn: sqlite3.Connection, ref: str) -> sqlite3.Row | None:
    """Find a model by repo id (any casing) or by slug."""
    return conn.execute(
        "SELECT * FROM models WHERE id = ? OR slug = ?", (ref.lower(), ref.lower())
    ).fetchone()


def list_models(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM models ORDER BY first_seen_at DESC, id").fetchall()


# --- sources and claims -----------------------------------------------------


def source_id_for(conn: sqlite3.Connection, url: str, kind: str, now: str) -> int:
    conn.execute(
        "INSERT INTO sources (url, kind, retrieved_at) VALUES (?, ?, ?)"
        " ON CONFLICT(url) DO UPDATE SET retrieved_at = excluded.retrieved_at",
        (url, kind, now),
    )
    return conn.execute("SELECT id FROM sources WHERE url = ?", (url,)).fetchone()[0]


def latest_claim(conn: sqlite3.Connection, model_id: str, field: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM claims WHERE model_id = ? AND field = ? ORDER BY id DESC LIMIT 1",
        (model_id, field),
    ).fetchone()


def add_claim(
    conn: sqlite3.Connection,
    *,
    model_id: str,
    field: str,
    value: Any,
    status: str,
    source_id: int,
    now: str,
) -> bool:
    """Append a claim unless it repeats the current one. Returns True when a row was added."""
    if status not in CLAIM_STATUSES:
        raise ValueError(f"invalid claim status {status!r}")
    if status == "unknown":
        value = None
    encoded = encode(value)
    current = latest_claim(conn, model_id, field)
    if current is not None and current["value"] == encoded and current["status"] == status:
        return False
    conn.execute(
        "INSERT INTO claims (model_id, field, value, source_id, status, observed_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (model_id, field, encoded, source_id, status, now),
    )
    return True


def current_claims(conn: sqlite3.Connection, model_id: str) -> dict[str, dict[str, Any]]:
    """Latest claim per field, with its source."""
    rows = conn.execute(
        "SELECT c.field, c.value, c.status, c.observed_at, s.url AS source_url,"
        " s.kind AS source_kind FROM claims c JOIN sources s ON s.id = c.source_id"
        " WHERE c.id IN (SELECT MAX(id) FROM claims WHERE model_id = ? GROUP BY field)",
        (model_id,),
    ).fetchall()
    return {
        row["field"]: {
            "value": json.loads(row["value"]),
            "status": row["status"],
            "observed_at": row["observed_at"],
            "source_url": row["source_url"],
            "source_kind": row["source_kind"],
        }
        for row in rows
    }


def claim_history(conn: sqlite3.Connection, model_id: str, field: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM claims WHERE model_id = ? AND field = ? ORDER BY id",
        (model_id, field),
    ).fetchall()


def material_changes_since(
    conn: sqlite3.Connection, model_id: str, since: str
) -> list[dict[str, Any]]:
    """Material-field claims observed after `since` that replaced an earlier value."""
    placeholders = ",".join("?" for _ in MATERIAL_FIELDS)
    rows = conn.execute(
        f"SELECT * FROM claims WHERE model_id = ? AND field IN ({placeholders})"
        " AND observed_at > ? ORDER BY id",
        (model_id, *MATERIAL_FIELDS, since),
    ).fetchall()
    changes = []
    for row in rows:
        previous = conn.execute(
            "SELECT value FROM claims WHERE model_id = ? AND field = ? AND id < ?"
            " ORDER BY id DESC LIMIT 1",
            (model_id, row["field"], row["id"]),
        ).fetchone()
        if previous is None:  # first observation of a field is not a change
            continue
        changes.append({
            "field": row["field"],
            "old": json.loads(previous["value"]),
            "new": json.loads(row["value"]),
            "observed_at": row["observed_at"],
        })
    return changes


# --- runs -------------------------------------------------------------------


def start_run(conn: sqlite3.Connection, command: str, args: dict[str, Any], now: str) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO runs (command, args, started_at) VALUES (?, ?, ?)",
            (command, encode(args), now),
        )
    return cursor.lastrowid


def finish_run(
    conn: sqlite3.Connection, run_id: int, *, ok: bool, message: dict[str, Any], now: str
) -> None:
    with conn:
        conn.execute(
            "UPDATE runs SET finished_at = ?, ok = ?, message = ? WHERE id = ?",
            (now, int(ok), encode(message), run_id),
        )


def recent_runs(conn: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
