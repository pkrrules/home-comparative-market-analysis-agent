"""
Frozen-fixture implementation of PropertyDataProvider.

Reads the fixtures captured by scripts/fetch_fixtures.py instead of calling
the live API. This is what "frozen responses as test fixtures" (project
plan) means in code: Agent 1's logic can be tested, and the app can be run
in an offline demo mode, against a fixed snapshot of the SimplyRETS trial
feed rather than a live, mutable one.

Filtering mirrors the real provider's server-side behavior closely enough
for tests (status, cities, postalCodes, q substring match on address.full),
but is not a reimplementation of SimplyRETS — just enough to exercise Agent 1.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from provider import PropertyDataProvider

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class FixtureProvider(PropertyDataProvider):
    def __init__(self, fixtures_dir: Path | str = DEFAULT_FIXTURES_DIR):
        fixtures_dir = Path(fixtures_dir)
        self._all_listings: list[dict[str, Any]] = json.loads(
            (fixtures_dir / "properties_all.json").read_text()
        )
        self._metadata: dict[str, Any] = json.loads(
            (fixtures_dir / "options_properties.json").read_text()
        )
        self._by_id = {str(l["mlsId"]): l for l in self._all_listings}

    def find_subject(self, identifier: str) -> dict[str, Any] | None:
        identifier = str(identifier).strip()
        if identifier in self._by_id:
            return self._by_id[identifier]
        needle = identifier.lower()
        for listing in self._all_listings:
            if needle in (listing["address"].get("full") or "").lower():
                return listing
        return None

    def search_closed_sales(
        self,
        *,
        cities: list[str] | None = None,
        postal_codes: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        results = [l for l in self._all_listings if l.get("mls", {}).get("status") == "Closed"]
        if cities:
            wanted = {c.lower() for c in cities}
            results = [l for l in results if (l["address"].get("city") or "").lower() in wanted]
        if postal_codes:
            wanted_zips = set(postal_codes)
            results = [l for l in results if l["address"].get("postalCode") in wanted_zips]
        return results[:limit]

    def get_feed_metadata(self) -> dict[str, Any]:
        return self._metadata
