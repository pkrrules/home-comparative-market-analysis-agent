"""
SimplyRETS implementation of the PropertyDataProvider interface.

Kept for reference (see docs/phase1-api-audit.md, docs/phase2-design-notes.md)
after the project's active provider moved to Repliers
(docs/phase2b-repliers-migration.md) — SimplyRETS' trial tier turned out not
to support real geo-radius filtering or a usably large closed-sales
population for this project's needs. No longer used by data_agent.py's
default wiring, but still a valid, testable PropertyDataProvider.
"""
from __future__ import annotations

from typing import Any

from provider import PropertyDataProvider
from simplyrets_client import SimplyRETSClient, SimplyRETSError


class SimplyRETSProvider(PropertyDataProvider):
    def __init__(self, client: SimplyRETSClient | None = None):
        self.client = client or SimplyRETSClient()

    def find_subject(self, identifier: str) -> dict[str, Any] | None:
        identifier = str(identifier).strip()
        if identifier.isdigit():
            try:
                return self.client.get_property(identifier)
            except SimplyRETSError as e:
                if e.status_code == 404:
                    return None
                raise
        results = self.client.search_properties(q=identifier, limit=5)
        return results[0] if results else None

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
        # lat/lng/radius_km are accepted (interface conformance) but ignored:
        # Phase 1 audit confirmed SimplyRETS' trial tier silently ignores
        # radius/lat/lng/polygon params rather than filtering on them.
        params: dict[str, Any] = {"status": "Closed", "limit": limit}
        if cities:
            params["cities"] = cities
        if postal_codes:
            params["postalCodes"] = postal_codes
        if property_type:
            params["type"] = property_type
        return self.client.search_properties(**params)

    def get_feed_metadata(self) -> dict[str, Any]:
        return self.client.options_properties()
