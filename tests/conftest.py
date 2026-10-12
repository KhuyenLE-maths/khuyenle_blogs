"""Shared test setup: an isolated project directory and a fixture-backed Hub client."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from msx import db
from msx.discover import discover
from msx.hf import FixtureHubClient
from msx.project import Project, load_project

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
NOW = datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)

TEST_CONFIG = """
[site]
name = "ModelScopeX Test"
base_url = "https://example.test/msx"

[discover]
authors = ["FixtureLab", "FixtureVision", "FixtureEmpty"]
categories = ["text-generation", "image-text-to-text"]
lookback_days = 30
max_models = 50
exclude_name_patterns = ["gguf", "awq", "gptq", "mlx", "bnb", "int4", "int8"]

[hardware.mac]
label = "Test Mac"
memory_gb = 16
usable_fraction = 0.7

[hardware.gpu]
label = "Test GPU"
memory_gb = 24
usable_fraction = 0.9

[publishing]
paused = false
"""


@pytest.fixture
def project(tmp_path: Path) -> Project:
    (tmp_path / "config.toml").write_text(TEST_CONFIG, encoding="utf-8")
    shutil.copytree(REPO / "migrations", tmp_path / "migrations")
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    return load_project(tmp_path)


@pytest.fixture
def conn(project: Project):
    connection = db.open_db(project)
    yield connection
    connection.close()


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    target = tmp_path / "hf-fixtures"
    shutil.copytree(FIXTURES, target)  # a copy, so tests may edit responses
    return target


@pytest.fixture
def client(fixture_dir: Path) -> FixtureHubClient:
    return FixtureHubClient(fixture_dir)


def no_sleep(_seconds: float) -> None:
    return None


def run_discover(project, conn, client, now=NOW, **kwargs):
    return discover(project, conn, client, now=now, sleep=no_sleep, request_delay=0, **kwargs)
