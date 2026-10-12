"""Command-line interface: msx discover | status | draft | approve | build | preview."""

from __future__ import annotations

import argparse
import functools
import json
import sqlite3
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import db
from .articles import ARTICLE_STATUSES, ArticleError, list_articles
from .build import build
from .discover import discover
from .draft import DraftError, draft
from .facts import FIELD_LABELS
from .hf import FixtureHubClient, LiveHubClient
from .project import Project, ProjectError, load_project
from .validate import approve


def _fmt_change(change: dict[str, Any]) -> str:
    label = FIELD_LABELS.get(change["field"], change["field"])
    return f"  {label}: {change['old']!r} -> {change['new']!r} (observed {change['observed_at']})"


def cmd_discover(project: Project, conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    client = FixtureHubClient(args.fixtures) if args.fixtures else LiveHubClient()
    summary = discover(
        project,
        conn,
        client,
        authors=args.author,
        max_models=args.max_models,
        lookback_days=args.lookback_days,
    )
    print(f"Run #{summary['run_id']}: checked {summary['checked']} models, "
          f"{summary['new_models']} new, {summary['new_claims']} new claims, "
          f"{summary['skipped']} skipped.")
    if summary["authors_with_no_models"]:
        print("Authors that returned zero models (check the name in config.toml): "
              + ", ".join(summary["authors_with_no_models"]))
    for error in summary["errors"]:
        print(f"error: {error}", file=sys.stderr)
    return 0 if not summary["errors"] else 1


def cmd_status(project: Project, conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    articles = list_articles(project.articles_dir)
    counts = {status: 0 for status in ARTICLE_STATUSES}
    for article in articles:
        counts[article.status] = counts.get(article.status, 0) + 1
    models = db.list_models(conn)
    covered = {str(a.meta.get("model_id")) for a in articles}

    print(f"Models: {len(models)}")
    print("Articles: " + ", ".join(f"{k} {v}" for k, v in counts.items()))

    without = [m["repo_id"] for m in models if m["id"] not in covered]
    print(f"\nModels without an article ({len(without)}):")
    for repo_id in without[:30]:
        print(f"  {repo_id}")
    if len(without) > 30:
        print(f"  and {len(without) - 30} more")

    print("\nArticles needing an update (material change after 'updated'):")
    flagged = 0
    for article in articles:
        since = str(article.meta.get("updated") or "")
        model_id = str(article.meta.get("model_id") or "")
        changes = db.material_changes_since(conn, model_id, since) if since and model_id else []
        if changes:
            flagged += 1
            print(f"  {article.slug} [{article.status}]")
            for change in changes:
                print(_fmt_change(change))
    if not flagged:
        print("  none")

    print("\nLast runs:")
    runs = db.recent_runs(conn)
    if not runs:
        print("  none")
    for run in runs:
        message = json.loads(run["message"]) if run["message"] else {}
        state = "ok" if run["ok"] else ("running" if run["ok"] is None else "with errors")
        print(f"  #{run['id']} {run['command']} {run['started_at']} {state}: "
              f"checked {message.get('checked', '-')}, new claims {message.get('new_claims', '-')}, "
              f"errors {len(message.get('errors', []))}")
    return 0


def cmd_draft(project: Project, conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    result = draft(project, conn, args.model)
    rel = result.path.relative_to(project.root)
    if result.created:
        print(f"Draft written: {rel}")
        return 0
    print(f"{rel} already exists; not overwritten.")
    if result.changes:
        print("Material facts changed since its 'updated' date:")
        for change in result.changes:
            print(_fmt_change(change))
    else:
        print("No material facts changed since its 'updated' date.")
    return 0


def cmd_approve(project: Project, conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    errors = approve(project, conn, args.slug)
    if errors:
        print(f"Not approved: {args.slug}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Approved: {args.slug}")
    return 0


def cmd_build(project: Project, conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    result = build(project, conn)
    print(f"Built {result.pages} pages ({result.models} models, {result.articles} articles) "
          f"into {result.site_dir.relative_to(project.root)}/")
    return 0


def cmd_preview(project: Project, conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    site = project.site_dir
    if not (site / "index.html").exists():
        print("site/ is empty: run 'msx build' first.", file=sys.stderr)
        return 1
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site))
    with ThreadingHTTPServer((args.host, args.port), handler) as server:
        print(f"Serving site/ at http://{args.host}:{args.port}/  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


COMMANDS = {
    "discover": cmd_discover,
    "status": cmd_status,
    "draft": cmd_draft,
    "approve": cmd_approve,
    "build": cmd_build,
    "preview": cmd_preview,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="msx", description="ModelScopeX: evidence-backed tracker for open-weight model releases."
    )
    parser.add_argument("--root", type=Path, default=None,
                        help="project directory (default: nearest folder with config.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("discover", help="list recent models on the Hub and store their facts")
    p.add_argument("--author", action="append", help="limit to this author (repeatable)")
    p.add_argument("--max-models", type=int, help="override discover.max_models")
    p.add_argument("--lookback-days", type=int, help="override discover.lookback_days")
    p.add_argument("--fixtures", type=Path,
                   help="read saved API responses from this directory instead of the network")

    sub.add_parser("status", help="show article states, coverage, update flags, and recent runs")

    p = sub.add_parser("draft", help="write a fact-only draft for one model")
    p.add_argument("model", help="model repo id (e.g. Qwen/Qwen3-8B) or slug")

    p = sub.add_parser("approve", help="validate an article and mark it approved")
    p.add_argument("slug")

    sub.add_parser("build", help="render approved and published articles into site/")

    p = sub.add_parser("preview", help="serve site/ locally")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        project = load_project(args.root)
        conn = db.open_db(project)
        try:
            return COMMANDS[args.command](project, conn, args)
        finally:
            conn.close()
    except (ProjectError, ArticleError, DraftError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
