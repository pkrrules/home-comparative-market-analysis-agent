"""
Agent 1: Property and Data Agent.

Ties provider -> canonical schema -> validation -> dedup together, matching
the architecture:

    SimplyRETS -> Provider interface -> Canonical property schema ->
    Validation and deduplication -> (Agent 2, next)

Responsibilities (per the project plan): find the subject, retrieve
closed-sale candidates, convert to canonical schema, validate required
fields, deduplicate, and label fields present/missing/implausible. No
cross-provider reconciliation — there is exactly one provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from canonical_schema import CanonicalProperty
from dedup import DedupDrop, deduplicate
from mapping import map_simplyrets_listing
from provider import PropertyDataProvider
from validation import flag_fields, missing_hard_requirements


@dataclass
class ClosedSalesResult:
    # Records kept here may still carry IMPLAUSIBLE field flags — Agent 1
    # only drops a record when a hard-required field is entirely MISSING
    # (calculation is literally impossible). Deciding whether an implausible
    # value disqualifies a record is Agent 2's eligibility-rule job, not
    # Agent 1's; the flags travel with the record so that decision has
    # something to work from.
    properties: list[CanonicalProperty]
    dropped_hard_requirements: list[tuple[CanonicalProperty, list[str]]] = field(default_factory=list)
    dedup_drops: list[DedupDrop] = field(default_factory=list)


class PropertyDataAgent:
    def __init__(self, provider: PropertyDataProvider):
        self.provider = provider

    def find_subject(self, identifier: str) -> CanonicalProperty | None:
        raw = self.provider.find_subject(identifier)
        if raw is None:
            return None
        subject = map_simplyrets_listing(raw)
        flag_fields(subject)
        return subject

    def load_closed_sales(
        self,
        *,
        cities: list[str] | None = None,
        postal_codes: list[str] | None = None,
        limit: int = 500,
    ) -> ClosedSalesResult:
        raw_listings = self.provider.search_closed_sales(
            cities=cities, postal_codes=postal_codes, limit=limit
        )

        mapped: list[CanonicalProperty] = []
        for raw in raw_listings:
            prop = map_simplyrets_listing(raw)
            flag_fields(prop)
            mapped.append(prop)

        deduped, dedup_drops = deduplicate(mapped)

        kept: list[CanonicalProperty] = []
        dropped_hard: list[tuple[CanonicalProperty, list[str]]] = []
        for prop in deduped:
            problems = missing_hard_requirements(prop)
            if problems:
                dropped_hard.append((prop, problems))
            else:
                kept.append(prop)

        return ClosedSalesResult(
            properties=kept,
            dropped_hard_requirements=dropped_hard,
            dedup_drops=dedup_drops,
        )
