from __future__ import annotations

import pytest

from msx.estimate import hardware_fit, weight_gb

TARGETS = {
    "mac": {"label": "Mac", "memory_gb": 16, "usable_fraction": 0.7},  # budget 11.2 GB
    "gpu": {"label": "GPU", "memory_gb": 24, "usable_fraction": 0.9},  # budget 21.6 GB
}


def test_weight_estimate_arithmetic():
    assert weight_gb(8_000_000_000, 16) == pytest.approx(16.0)
    assert weight_gb(8_000_000_000, 8) == pytest.approx(8.0)
    assert weight_gb(8_000_000_000, 4) == pytest.approx(4.0)

    rows = {r["precision"]: r for r in hardware_fit(8_000_000_000, TARGETS)}
    assert rows["16-bit"]["fits"] == {"mac": False, "gpu": True}
    assert rows["8-bit"]["fits"] == {"mac": True, "gpu": True}
    assert rows["4-bit"]["weights_gb"] == 4.0
