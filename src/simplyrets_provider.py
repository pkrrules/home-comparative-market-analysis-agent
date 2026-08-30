"""SimplyRETS implementation of the PropertyDataProvider interface."""
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
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"status": "Closed", "limit": limit}
        if cities:
            params["cities"] = cities
        if postal_codes:
            params["postalCodes"] = postal_codes
        return self.client.search_properties(**params)

    def get_feed_metadata(self) -> dict[str, Any]:
        return self.client.options_properties()
