"""
Frozen-fixture implementation of PropertyDataProvider, backed by the
Repliers migration-audit fixtures (fixtures/repliers_*.json).

Since Repliers' population is far larger than what's frozen (see
docs/phase1-repliers-audit.md §1), this only ever sees the sample —
useful for tests and an offline demo mode, not a substitute for the live
feed's full breadth.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from provider import PropertyDataProvider

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class RepliersFixtureProvider(PropertyDataProvider):
    def __init__(self, fixtures_dir: Path | str = DEFAULT_FIXTURES_DIR):
        fixtures_dir = Path(fixtures_dir)
        broad = json.loads((fixtures_dir / "repliers_closed_sales_sample.json").read_text())
        city = json.loads((fixtures_dir / "repliers_city_sample.json").read_text())
        # De-duplicate by mlsNumber: the two frozen samples can overlap on
        # top-of-index records for the anchor city (same finding as the
        # audit script — see scripts/audit_repliers.py).
        by_id = {l["mlsNumber"]: l for l in broad + city}
        self._all_listings: list[dict[str, Any]] = list(by_id.values())
        self._by_id = by_id
        self._metadata: dict[str, Any] = json.loads((fixtures_dir / "repliers_overview.json").read_text())

    def find_subject(self, identifier: str) -> dict[str, Any] | None:
        return self._by_id.get(str(identifier).strip())

    def search_closed_sales(
        self,
        *,
        cities: list[str] | None = None,
        postal_codes: list[str] | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
        property_type: str | None = "Residential",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        results = self._all_listings
        if cities:
            wanted = {c.lower() for c in cities}
            results = [l for l in results if (l["address"].get("city") or "").lower() in wanted]
        if postal_codes:
            wanted_zips = set(postal_codes)
            results = [l for l in results if l["address"].get("zip") in wanted_zips]
        if property_type:
            results = [l for l in results if l.get("details", {}).get("propertyType") == property_type]
        if lat is not None and lng is not None and radius_km is not None:
            # Frozen fixtures are too small a sample to trust a real distance
            # calc against (see Phase 3 for the real implementation) — this
            # fixture provider only supports geo filtering approximately, by
            # returning everything and letting a test assert on count changes
            # elsewhere. Kept unfiltered here deliberately; document if used.
            pass
        return results[:limit]

    def get_feed_metadata(self) -> dict[str, Any]:
        return self._metadata
