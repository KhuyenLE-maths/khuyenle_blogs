"""Weight-memory estimates. Every result here is an estimate, never a measurement."""

from __future__ import annotations

from typing import Any

PRECISIONS = (("16-bit", 16), ("8-bit", 8), ("4-bit", 4))

FORMULA = (
    "weights (GB) = parameters × bits ÷ 8 ÷ 10^9; "
    "a target is marked 'likely fits' when weights ≤ memory_gb × usable_fraction"
)

EXCLUSIONS = "KV cache, activations, and runtime overhead are excluded."


def weight_gb(parameters: int, bits: int) -> float:
    return parameters * bits / 8 / 1e9


def budget_gb(target: dict[str, Any]) -> float:
    return float(target["memory_gb"]) * float(target["usable_fraction"])


def hardware_fit(parameters: int, targets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per precision with weight size and a fits flag per hardware target."""
    rows = []
    for label, bits in PRECISIONS:
        size = weight_gb(parameters, bits)
        rows.append({
            "precision": label,
            "bits": bits,
            "weights_gb": round(size, 2),
            "fits": {name: size <= budget_gb(target) for name, target in targets.items()},
        })
    return rows
