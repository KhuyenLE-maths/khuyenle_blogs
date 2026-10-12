from __future__ import annotations

import xml.etree.ElementTree as ET

from conftest import NOW, run_discover
from msx.articles import read_article, write_article
from msx.build import build
from msx.draft import draft
from msx.validate import approve

LM_REPO, LM_SLUG = "FixtureLab/Fixture-LM-8B", "fixturelab-fixture-lm-8b"
VL_REPO, VL_SLUG = "FixtureVision/Fixture-VL-3B", "fixturevision-fixture-vl-3b"


def test_build_excludes_drafts(project, conn, client):
    run_discover(project, conn, client)
    draft(project, conn, LM_REPO, now=NOW)
    draft(project, conn, VL_REPO, now=NOW)
    assert approve(project, conn, LM_SLUG, now=NOW) == []

    build(project, conn, now=NOW)
    site = project.site_dir

    assert (site / "blog" / LM_SLUG / "index.html").exists()
    assert not (site / "blog" / VL_SLUG).exists()
    assert f"/blog/{VL_SLUG}/" not in (site / "feed.xml").read_text()
    assert f"/blog/{VL_SLUG}/" not in (site / "sitemap.xml").read_text()
    assert (site / "models" / VL_SLUG / "index.html").exists()  # model pages list every model


def test_markdown_scripts_and_javascript_links_are_not_active(project, conn, client):
    run_discover(project, conn, client)
    path = draft(project, conn, LM_REPO, now=NOW).path
    article = read_article(path)
    article.body += "\n<script>alert(1)</script>\n\n[click me](javascript:alert(1))\n"
    write_article(article)
    assert approve(project, conn, LM_SLUG, now=NOW) == []

    build(project, conn, now=NOW)
    html = (project.site_dir / "blog" / LM_SLUG / "index.html").read_text()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert 'href="javascript:' not in html


def test_end_to_end_fixture_to_site(project, conn, client):
    summary = run_discover(project, conn, client)
    assert summary["errors"] == []
    assert draft(project, conn, LM_REPO, now=NOW).created
    assert approve(project, conn, LM_SLUG, now=NOW) == []
    result = build(project, conn, now=NOW)
    site = project.site_dir

    assert result.models == 2 and result.articles == 1

    model_html = (site / "models" / LM_SLUG / "index.html").read_text()
    assert "8,030,261,248" in model_html
    assert "apache-2.0" in model_html
    assert "publisher-declared" in model_html
    assert 'href="https://huggingface.co/api/models/FixtureLab/Fixture-LM-8B"' in model_html
    assert "likely fits" in model_html

    vl_html = (site / "models" / VL_SLUG / "index.html").read_text()
    assert "Unknown / Not verified" in vl_html
    assert "Cannot be estimated" in vl_html

    article_html = (site / "blog" / LM_SLUG / "index.html").read_text()
    assert "https://huggingface.co/FixtureLab/Fixture-LM-8B" in article_html
    assert "<table>" in article_html
    assert f'rel="canonical" href="https://example.test/msx/blog/{LM_SLUG}/"' in article_html
    assert 'href="/msx/style.css"' in article_html  # base path from site.base_url

    feed = ET.parse(site / "feed.xml").getroot()
    assert [i.findtext("title") for i in feed.iter("item")] == [LM_REPO]
    sitemap = ET.parse(site / "sitemap.xml").getroot()
    assert len(list(sitemap)) == result.pages
