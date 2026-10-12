"""Hugging Face Hub access (live or fixture-backed) and deterministic claim extraction.

Responses from the Hub are untrusted data: we only read typed fields from them and
never interpret their text as instructions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar

API_BASE = "https://huggingface.co/api"
WEB_BASE = "https://huggingface.co"

T = TypeVar("T")


class HubError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class HubClient(Protocol):
    def list_models(self, author: str, pipeline_tag: str, limit: int) -> list[dict[str, Any]]: ...

    def model_info(self, repo_id: str) -> dict[str, Any]: ...


def model_api_url(repo_id: str) -> str:
    return f"{API_BASE}/models/{repo_id}"


def model_page_url(repo_id: str) -> str:
    return f"{WEB_BASE}/{repo_id}"


class LiveHubClient:
    """Calls the public Hub REST API through huggingface_hub's configured HTTP session.

    huggingface_hub supplies the user agent and, when HF_TOKEN is set, the auth header.
    The token is never logged or printed.
    """

    def __init__(self, timeout: float = 30.0):
        from huggingface_hub import get_session
        from huggingface_hub.utils import build_hf_headers

        self._session = get_session()
        self._headers = build_hf_headers()
        self._timeout = timeout

    def _get(self, url: str, params: dict[str, str] | None = None) -> Any:
        try:
            response = self._session.get(
                url, params=params, headers=self._headers, timeout=self._timeout
            )
        except Exception as exc:  # network errors from the HTTP client
            raise HubError(f"request failed for {url}: {exc.__class__.__name__}") from exc
        if response.status_code != 200:
            raise HubError(f"HTTP {response.status_code} for {url}", response.status_code)
        return response.json()

    def list_models(self, author: str, pipeline_tag: str, limit: int) -> list[dict[str, Any]]:
        params = {
            "author": author,
            "pipeline_tag": pipeline_tag,
            "sort": "createdAt",
            "direction": "-1",
            "limit": str(limit),
        }
        data = self._get(f"{API_BASE}/models", params)
        if not isinstance(data, list):
            raise HubError(f"unexpected list response for {author}/{pipeline_tag}")
        return data

    def model_info(self, repo_id: str) -> dict[str, Any]:
        data = self._get(model_api_url(repo_id))
        if not isinstance(data, dict):
            raise HubError(f"unexpected model response for {repo_id}")
        return data


class FixtureHubClient:
    """Serves saved API responses from a directory, for tests and offline demos.

    Layout: list/<author>__<pipeline_tag>.json and models/<org>__<name>.json
    """

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def list_models(self, author: str, pipeline_tag: str, limit: int) -> list[dict[str, Any]]:
        path = self.directory / "list" / f"{author}__{pipeline_tag}.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))[:limit]

    def model_info(self, repo_id: str) -> dict[str, Any]:
        path = self.directory / "models" / f"{repo_id.replace('/', '__')}.json"
        if not path.exists():
            raise HubError(f"HTTP 404 for {model_api_url(repo_id)}", 404)
        return json.loads(path.read_text(encoding="utf-8"))


def with_retry(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call fn, retrying up to `retries` times with exponential backoff.

    Client errors other than 429 (rate limited) are not retried.
    """
    for attempt in range(retries + 1):
        try:
            return fn()
        except HubError as exc:
            retryable = exc.status is None or exc.status == 429 or exc.status >= 500
            if not retryable or attempt == retries:
                raise
            sleep(base_delay * 2**attempt)
    raise AssertionError("unreachable")


# --- claim extraction ---------------------------------------------------------

CLAIM_FIELDS = (
    "pipeline_tag",
    "license",
    "created_at",
    "last_modified",
    "commit_sha",
    "gated",
    "parameters",
    "base_model",
    "languages",
    "library",
)


def _as_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list):
        return None
    cleaned = [str(item) for item in items if isinstance(item, (str, int, float)) and str(item)]
    return cleaned or None


def _license(info: dict[str, Any]) -> Any:
    card = info.get("cardData") or {}
    if card.get("license"):
        return card["license"]
    for tag in info.get("tags") or []:
        if isinstance(tag, str) and tag.startswith("license:"):
            return tag.split(":", 1)[1]
    return None


def _parameters(info: dict[str, Any]) -> int | None:
    safetensors = info.get("safetensors")
    if not isinstance(safetensors, dict):
        return None
    total = safetensors.get("total")
    if isinstance(total, int) and not isinstance(total, bool) and total > 0:
        return total
    per_dtype = safetensors.get("parameters")
    if isinstance(per_dtype, dict):
        counts = [v for v in per_dtype.values() if isinstance(v, int) and not isinstance(v, bool)]
        if counts and sum(counts) > 0:
            return sum(counts)
    return None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def extract_claims(info: dict[str, Any]) -> list[tuple[str, Any, str]]:
    """Map a model-info response to (field, value, status) triples.

    Present values are 'publisher_declared' (stated by the repo owner on the Hub);
    missing values are 'unknown' with value None. Nothing is guessed.
    """
    card = info.get("cardData") or {}
    gated = info.get("gated")
    values: dict[str, Any] = {
        "pipeline_tag": _str_or_none(info.get("pipeline_tag")),
        "license": _license(info),
        "created_at": _str_or_none(info.get("createdAt")),
        "last_modified": _str_or_none(info.get("lastModified")),
        "commit_sha": _str_or_none(info.get("sha")),
        "gated": gated if isinstance(gated, (bool, str)) else None,
        "parameters": _parameters(info),
        "base_model": _as_str_list(card.get("base_model")),
        "languages": _as_str_list(card.get("language")),
        "library": _str_or_none(info.get("library_name")),
    }
    return [
        (field, values[field], "unknown" if values[field] is None else "publisher_declared")
        for field in CLAIM_FIELDS
    ]
