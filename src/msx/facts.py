"""Labels and display formatting for claims, shared by drafts and the site."""

from __future__ import annotations

from typing import Any

from .hf import CLAIM_FIELDS

UNKNOWN = "Unknown / Not verified"

FIELD_LABELS = {
    "pipeline_tag": "Pipeline tag",
    "license": "License",
    "created_at": "Created",
    "last_modified": "Last modified",
    "commit_sha": "Latest commit",
    "gated": "Gated access",
    "parameters": "Parameters",
    "base_model": "Base model",
    "languages": "Languages",
    "library": "Library",
}

CATEGORY_LABELS = {
    "text-generation": "LLM",
    "image-text-to-text": "VLM",
}

STATUS_LABELS = {
    "publisher_declared": "publisher-declared",
    "independently_measured": "independently measured",
    "estimated": "estimated",
    "unknown": "unknown",
}

SOURCE_NAMES = {
    "hf_api": "Hugging Face API",
    "hf_model_card": "Model card",
    "github": "GitHub",
    "paper": "Paper",
    "vendor_blog": "Vendor blog",
    "own_eval": "ModelScopeX evaluation",
}


def human_count(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    return f"{n:,}"


def format_value(field: str, value: Any) -> str:
    if value is None:
        return UNKNOWN
    if field == "parameters" and isinstance(value, int):
        return f"{value:,} ({human_count(value)})"
    if field == "gated":
        if value is False:
            return "no"
        if value is True:
            return "yes"
        return f"yes ({value} approval)"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def fact_rows(claims: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows in a fixed field order; fields never observed show as unknown."""
    rows = []
    for field in CLAIM_FIELDS:
        claim = claims.get(field)
        status = claim["status"] if claim else "unknown"
        value = claim["value"] if claim else None
        rows.append({
            "field": field,
            "label": FIELD_LABELS[field],
            "value": value,
            "display": format_value(field, value),
            "status": status,
            "status_label": STATUS_LABELS[status],
            "source_url": claim["source_url"] if claim else None,
            "source_name": SOURCE_NAMES.get(claim["source_kind"], "Source") if claim else None,
            "observed_at": claim["observed_at"] if claim else None,
        })
    return rows


def md_escape(text: str) -> str:
    """Escape Markdown-significant characters in untrusted values placed into Markdown."""
    out = text.replace("\\", "\\\\").replace("\n", " ").replace("\r", " ")
    for ch in "`*_[]<>|#!":
        out = out.replace(ch, "\\" + ch)
    return out
