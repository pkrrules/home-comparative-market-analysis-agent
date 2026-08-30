"""
Thin Repliers API client.

Mirrors simplyrets_client.py in spirit: minimal, tailored to this project's
needs, not a general SDK. Auth is a header (`REPLIERS-API-KEY`), not Basic
auth, and Repliers' `/listings` search takes very different parameters from
SimplyRETS — the two providers are genuinely different shapes, which is
exactly why the mapping/provider layers exist.

Docs: https://docs.repliers.io
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

DEFAULT_BASE_URL = "https://api.repliers.io"
DEFAULT_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.5


class RepliersError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class RepliersClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key or os.environ.get("REPLIERS_API_KEY")
        if not self.api_key:
            raise RepliersError("REPLIERS_API_KEY is not set (env or .env)")
        self.base_url = (base_url or os.environ.get("REPLIERS_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers["REPLIERS-API-KEY"] = self.api_key
        self._session.headers["Accept"] = "application/json"

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._session.request(method, url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue

            if resp.status_code == 429:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt * 2)
                continue
            if resp.status_code >= 500:
                last_exc = RepliersError(f"{method} {path} -> {resp.status_code}", resp.status_code, resp.text)
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            if resp.status_code >= 400:
                raise RepliersError(
                    f"{method} {path} -> {resp.status_code}: {resp.text[:500]}", resp.status_code, resp.text
                )
            return resp

        raise RepliersError(f"{method} {path} failed after {MAX_RETRIES} attempts: {last_exc}")

    def search_listings(self, **params: Any) -> dict[str, Any]:
        """GET /listings — returns the full envelope ({count, page, numPages,
        listings: [...], ...}), not just the array, since pagination metadata
        matters here (unlike SimplyRETS' flat-array response)."""
        resp = self._request("GET", "/listings", params=params)
        return resp.json()

    def get_listing(self, mls_number: str) -> dict[str, Any]:
        resp = self._request("GET", f"/listings/{mls_number}")
        return resp.json()
