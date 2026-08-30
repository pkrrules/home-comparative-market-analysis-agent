"""
Provider interface.

Small and tailored to this application, not a generic real-estate SDK: it
only exposes the operations the Property/Data Agent actually needs. It
returns raw provider dicts, not canonical records — mapping into
CanonicalProperty, validation, and dedup all happen downstream (see
mapping.py / validation.py / dedup.py / data_agent.py), matching the
architecture's Provider -> Canonical schema -> Validation/dedup ordering.

History: originally written against SimplyRETS only (see
docs/phase1-api-audit.md, docs/phase2-design-notes.md), whose trial tier
turned out not to support real geo-radius filtering. The project has since
switched its active provider to Repliers (docs/phase1-repliers-audit.md,
docs/phase2b-repliers-migration.md), which does support radius search for
real — confirmed empirically (a 0.01km radius returned 1 listing, 5km
returned 17, for the same center point). So `lat`/`lng`/`radius_km` are
first-class params here, not an afterthought; a provider that can't honor
them (SimplyRETSProvider, kept for reference) just ignores them and says so.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PropertyDataProvider(ABC):
    @abstractmethod
    def find_subject(self, identifier: str) -> dict[str, Any] | None:
        """Resolve one subject listing by the provider's own id (MLS number)
        or by an address/text query. Returns None if nothing matches.

        Address/text resolution is best-effort and provider-specific — for
        the current provider (Repliers), free-text and compound address
        filters proved unreliable in practice (see the migration notes), so
        callers should prefer resolving subjects by id where possible (e.g.
        a curated "try an example" picker), matching the project plan's own
        recommended demo UI.
        """

    @abstractmethod
    def search_closed_sales(
        self,
        *,
        cities: list[str] | None = None,
        postal_codes: list[str] | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
        property_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Raw closed-sale listings, filtered server-side by whatever the
        provider actually supports — a provider that can't honor a given
        filter should ignore it and document that, not raise or fake it.

        `lat`/`lng`/`radius_km` are a coarse, provider-side prefilter, not a
        substitute for the comparable engine's own exact great-circle
        distance calculation: different providers may define "radius"
        slightly differently, so the app still computes and enforces the
        final distance cutoff itself downstream, deterministically, against
        canonical records. This mirrors the project plan's original design
        even now that server-side radius filtering actually works.
        """

    @abstractmethod
    def get_feed_metadata(self) -> dict[str, Any]:
        """Raw, cheap feed-level metadata (counts/stats), not a full audit.
        A real audit belongs in scripts/, not here."""
