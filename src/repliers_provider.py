"""Repliers implementation of the PropertyDataProvider interface.

Active provider as of the Repliers migration — see
docs/phase2b-repliers-migration.md for why, and for the empirical findings
(radius search actually filters; free-text/compound address search does
not reliably; results cap at 100/page; standardStatus+type+propertyType are
the reliable server-side filters) behind the choices below.
"""
from __future__ import annotations

from typing import Any

from provider import PropertyDataProvider
from repliers_client import RepliersClient, RepliersError

# Repliers caps resultsPerPage at 100 server-side (confirmed empirically:
# requesting 500/1000/5000 all silently returned 100). This client paginates
# to satisfy a larger `limit`, up to this many pages, to keep a single
# search_closed_sales call bounded (and rate-limit-friendly).
PAGE_SIZE = 100
MAX_PAGES = 20


class RepliersProvider(PropertyDataProvider):
    def __init__(self, client: RepliersClient | None = None):
        self.client = client or RepliersClient()

    def find_subject(self, identifier: str) -> dict[str, Any] | None:
        """Resolves by MLS number only — see provider.py docstring: this
        API's address/text search parameters proved unreliable in practice
        (streetName alone found nothing for a known record; streetNumber
        combined with city/zip returned nothing despite streetNumber alone
        working). A curated picker keyed by MLS number is the recommended
        subject-selection UI (matching the project plan's own guidance) and
        is the identifier this method is built to resolve."""
        identifier = str(identifier).strip()
        try:
            return self.client.get_listing(identifier)
        except RepliersError as e:
            if e.status_code == 404:
                return None
            raise

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
        params: dict[str, Any] = {
            "standardStatus": "Closed",
            "type": "sale",  # excludes closed *leases* (lastStatus=Lsd), confirmed via probe
        }
        # Only single-value city/zip filtering was verified during the
        # migration audit; multi-value list behavior for these params is
        # untested, so only the first value is used if more than one is given.
        if cities:
            params["city"] = cities[0]
        if postal_codes:
            params["zip"] = postal_codes[0]
        if lat is not None and lng is not None and radius_km is not None:
            params["lat"] = lat
            params["long"] = lng
            params["radius"] = radius_km
        if property_type:
            params["propertyType"] = property_type

        # NOTE: the pagination param is `pageNum`, not `page` — confirmed the
        # hard way: `page=` is silently accepted-and-ignored (it shows up in
        # the response's `unrecognizedParams`), so a naive `page += 1` loop
        # would have quietly re-fetched page 1 forever. See migration notes.
        results: list[dict[str, Any]] = []
        page_num = 1
        while len(results) < limit and page_num <= MAX_PAGES:
            envelope = self.client.search_listings(**params, resultsPerPage=PAGE_SIZE, pageNum=page_num)
            batch = envelope.get("listings", [])
            results.extend(batch)
            if len(batch) < PAGE_SIZE or page_num >= envelope.get("numPages", page_num):
                break
            page_num += 1
        return results[:limit]

    def get_feed_metadata(self) -> dict[str, Any]:
        envelope = self.client.search_listings(resultsPerPage=1)
        return {
            "count": envelope.get("count"),
            "numPages": envelope.get("numPages"),
            "statistics": envelope.get("statistics"),
            "apiVersion": envelope.get("apiVersion"),
        }
