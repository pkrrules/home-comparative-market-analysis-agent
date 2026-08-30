"""
Frozen-fixture implementation of PropertyDataProvider, backed by the
SimplyRETS fixtures from Phase 1/2 (fixtures/properties_all.json etc.).

Kept for reference alongside simplyrets_provider.py — see
docs/phase2b-repliers-migration.md for why the active provider moved to
Repliers. For current test/offline-demo use, see repliers_fixture_provider.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from provider import PropertyDataProvider

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class SimplyRETSFixtureProvider(PropertyDataProvider):
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
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
        property_type: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        # lat/lng/radius_km ignored — see provider.py / simplyrets_provider.py.
        results = [l for l in self._all_listings if l.get("mls", {}).get("status") == "Closed"]
        if cities:
            wanted = {c.lower() for c in cities}
            results = [l for l in results if (l["address"].get("city") or "").lower() in wanted]
        if postal_codes:
            wanted_zips = set(postal_codes)
            results = [l for l in results if l["address"].get("postalCode") in wanted_zips]
        if property_type:
            results = [l for l in results if l.get("property", {}).get("type") == property_type]
        return results[:limit]

    def get_feed_metadata(self) -> dict[str, Any]:
        return self._metadata
