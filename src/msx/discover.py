"""`msx discover`: list recent models from the Hub and record their facts as claims."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from . import db
from .hf import HubClient, extract_claims, model_api_url, with_retry
from .project import Project, iso, parse_iso, utc_now


def discover(
    project: Project,
    conn: sqlite3.Connection,
    client: HubClient,
    *,
    now: datetime | None = None,
    authors: list[str] | None = None,
    max_models: int | None = None,
    lookback_days: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    request_delay: float = 0.2,
) -> dict[str, Any]:
    cfg = project.config["discover"]
    now = now or utc_now()
    stamp = iso(now)
    authors = authors or list(cfg["authors"])
    max_models = max_models or int(cfg["max_models"])
    lookback_days = lookback_days or int(cfg["lookback_days"])
    cutoff = now - timedelta(days=lookback_days)
    patterns = [p.lower() for p in cfg["exclude_name_patterns"]]

    run_id = db.start_run(
        conn,
        "discover",
        {"authors": authors, "max_models": max_models, "lookback_days": lookback_days},
        stamp,
    )
    summary: dict[str, Any] = {
        "checked": 0,
        "new_models": 0,
        "new_claims": 0,
        "skipped": 0,
        "errors": [],
        "authors_with_no_models": [],
    }

    candidates: dict[str, dict[str, Any]] = {}
    for author in authors:
        returned = 0
        for tag in cfg["categories"]:
            try:
                items = with_retry(
                    lambda: client.list_models(author, tag, min(max_models, 100)), sleep=sleep
                )
            except Exception as exc:
                summary["errors"].append(f"list {author}/{tag}: {exc}")
                continue
            returned += len(items)
            for item in items:
                repo_id = item.get("id") or item.get("modelId")
                created = item.get("createdAt")
                if not isinstance(repo_id, str) or "/" not in repo_id or not created:
                    summary["skipped"] += 1
                    continue
                if any(p in repo_id.lower() for p in patterns):
                    summary["skipped"] += 1
                    continue
                try:
                    created_at = parse_iso(created)
                except ValueError:
                    summary["skipped"] += 1
                    continue
                if created_at < cutoff:
                    continue
                candidates.setdefault(
                    repo_id.lower(),
                    {"repo_id": repo_id, "author": author, "category": tag, "created": created_at},
                )
        if returned == 0:
            summary["authors_with_no_models"].append(author)

    selected = sorted(candidates.values(), key=lambda c: c["created"], reverse=True)[:max_models]
    for index, cand in enumerate(selected):
        if index and request_delay:
            sleep(request_delay)
        repo_id = cand["repo_id"]
        try:
            info = with_retry(lambda: client.model_info(repo_id), sleep=sleep)
        except Exception as exc:
            summary["errors"].append(f"model {repo_id}: {exc}")
            continue
        with conn:  # one transaction per model
            is_new = db.upsert_model(
                conn,
                repo_id=repo_id,
                author=cand["author"],
                category=cand["category"],
                now=stamp,
                downloads=info.get("downloads") if isinstance(info.get("downloads"), int) else None,
                likes=info.get("likes") if isinstance(info.get("likes"), int) else None,
            )
            source_id = db.source_id_for(conn, model_api_url(repo_id), "hf_api", stamp)
            for field, value, status in extract_claims(info):
                if db.add_claim(
                    conn,
                    model_id=repo_id.lower(),
                    field=field,
                    value=value,
                    status=status,
                    source_id=source_id,
                    now=stamp,
                ):
                    summary["new_claims"] += 1
        summary["checked"] += 1
        summary["new_models"] += int(is_new)

    db.finish_run(conn, run_id, ok=not summary["errors"], message=summary, now=iso(utc_now()))
    summary["run_id"] = run_id
    return summary
