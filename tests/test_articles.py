from __future__ import annotations

from dataclasses import replace

from conftest import NOW, run_discover
from msx.articles import read_article, write_article
from msx.draft import draft
from msx.validate import approve

LM_REPO = "FixtureLab/Fixture-LM-8B"
LM_SLUG = "fixturelab-fixture-lm-8b"


def test_draft_is_fact_only_and_complete(project, conn, client):
    run_discover(project, conn, client)
    result = draft(project, conn, LM_REPO, now=NOW)
    article = read_article(result.path)

    assert result.created
    assert article.meta["status"] == "draft"
    assert article.meta["sources"][0] == "https://huggingface.co/FixtureLab/Fixture-LM-8B"
    assert "8,030,261,248" in article.body
    assert "apache-2.0" in article.body
    assert "https://huggingface.co/api/models/FixtureLab/Fixture-LM-8B" in article.body
    assert "## Hardware fit (estimate)" in article.body


def test_draft_never_overwrites_an_existing_article(project, conn, client):
    run_discover(project, conn, client)
    first = draft(project, conn, LM_REPO, now=NOW)
    first.path.write_text(first.path.read_text() + "\nHand-written note.\n")

    second = draft(project, conn, LM_REPO, now=NOW)

    assert second.created is False
    assert "Hand-written note." in first.path.read_text()


def test_approve_refuses_placeholders_empty_sources_and_paused_publishing(project, conn, client):
    run_discover(project, conn, client)
    path = draft(project, conn, LM_REPO, now=NOW).path

    article = read_article(path)
    article.body += "\nTODO: add a verdict.\n"
    article.meta["sources"] = []
    write_article(article)
    errors = approve(project, conn, LM_SLUG, now=NOW)
    assert any("placeholder" in e for e in errors)
    assert any("sources is empty" in e for e in errors)  # every failure is reported
    assert read_article(path).meta["status"] == "draft"

    path.unlink()
    draft(project, conn, LM_REPO, now=NOW)
    paused = replace(project, config={**project.config, "publishing": {"paused": True}})
    errors = approve(paused, conn, LM_SLUG, now=NOW)
    assert errors == ["publishing is paused (publishing.paused = true in config.toml)"]
    assert read_article(path).meta["status"] == "draft"

    assert approve(project, conn, LM_SLUG, now=NOW) == []
    assert read_article(path).meta["status"] == "approved"
