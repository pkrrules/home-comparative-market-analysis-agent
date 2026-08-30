"""
Provider interface.

Small and tailored to this application, not a generic real-estate SDK:
it only exposes the three operations the Property/Data Agent actually
needs. It returns raw provider dicts, not canonical records — mapping
into CanonicalProperty, validation, and dedup all happen downstream
(see mapping.py / validation.py / dedup.py / data_agent.py), matching the
architecture's Provider -> Canonical schema -> Validation/dedup ordering.

Only one implementation exists (SimplyRETSProvider), but the interface
still buys us: (a) a documented contract for what "search" means in this
app, and (b) the ability to swap in frozen-fixture doubles for tests
without touching Agent 1's logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PropertyDataProvider(ABC):
    @abstractmethod
    def find_subject(self, identifier: str) -> dict[str, Any] | None:
        """Resolve one subject listing by the provider's own id or by an
        address/text query. Returns None if nothing matches."""

    @abstractmethod
    def search_closed_sales(
        self,
        *,
        cities: list[str] | None = None,
        postal_codes: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Raw closed-sale listings, filtered server-side only by what the
        provider actually supports.

        Phase 1 audit finding: on the SimplyRETS trial tier, `cities` and
        `postalCodes` filter server-side (confirmed: an unknown city returns
        zero results), but `radius`/`lat`/`lng`/`polygon` params are silently
        ignored (a 0-mile radius around (0, 0) still returned every closed
        listing). So this interface deliberately does NOT expose radius/geo
        params — the comparable engine must pull by city/postal code (or no
        filter, given how small this feed is) and do all distance and date
        filtering client-side, against canonical records.
        """

    @abstractmethod
    def get_feed_metadata(self) -> dict[str, Any]:
        """Raw feed metadata (SimplyRETS: OPTIONS /properties)."""
