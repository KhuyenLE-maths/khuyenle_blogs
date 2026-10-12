"""Live smoke test against the Hugging Face API. Skipped by default; run: pytest -m network"""

from __future__ import annotations

import pytest

from msx.discover import discover
from msx.hf import LiveHubClient


@pytest.mark.network
def test_live_discover_one_author(project, conn):
    summary = discover(
        project,
        conn,
        LiveHubClient(),
        authors=["Qwen"],
        max_models=3,
        lookback_days=365,
        request_delay=0.5,
    )
    assert summary["errors"] == []
    assert summary["checked"] >= 1
    assert summary["new_claims"] > 0
