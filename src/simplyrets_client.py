"""
Thin SimplyRETS API client.

Deliberately minimal and tailored to this project's audit/search needs —
not a generic real-estate SDK. Wraps auth, base URL, retries, and the
handful of endpoints Phase 1 (and later the Property/Data Agent) needs.

Docs: https://docs.simplyrets.com
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no external dependency). Silently no-ops if
    the file is absent; never overrides an already-set env var."""
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

DEFAULT_BASE_URL = "https://api.simplyrets.com"
DEFAULT_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.5


class SimplyRETSError(RuntimeError):
    """Raised for non-2xx responses or transport failures after retries."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class SimplyRETSClient:
    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        base_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.username = username or os.environ.get("SIMPLYRETS_USERNAME", "simplyrets")
        self.password = password or os.environ.get("SIMPLYRETS_PASSWORD", "simplyrets")
        self.base_url = (base_url or os.environ.get("SIMPLYRETS_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.auth = (self.username, self.password)

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

            if resp.status_code >= 500:
                last_exc = SimplyRETSError(
                    f"{method} {path} -> {resp.status_code}", resp.status_code, resp.text
                )
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue

            if resp.status_code >= 400:
                raise SimplyRETSError(
                    f"{method} {path} -> {resp.status_code}: {resp.text[:500]}",
                    resp.status_code,
                    resp.text,
                )

            return resp

        raise SimplyRETSError(f"{method} {path} failed after {MAX_RETRIES} attempts: {last_exc}")

    def options_properties(self) -> dict[str, Any]:
        """OPTIONS /properties — feed metadata: statuses, cities, counties,
        neighborhoods, property types, last-update info."""
        resp = self._request("OPTIONS", "/properties")
        return resp.json()

    def search_properties(self, **params: Any) -> list[dict[str, Any]]:
        """GET /properties with arbitrary query params (status, cities, type,
        limit, offset, q, minprice, maxprice, lastId, sort, ...)."""
        resp = self._request("GET", "/properties", params=params)
        return resp.json()

    def get_property(self, mls_id: str) -> dict[str, Any]:
        """GET /properties/{mlsId} — single listing detail."""
        resp = self._request("GET", f"/properties/{mls_id}")
        return resp.json()

    def response_headers(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, str]:
        """Expose raw headers (e.g. pagination/rate-limit headers) for audit purposes."""
        resp = self._request(method, path, params=params)
        return dict(resp.headers)
