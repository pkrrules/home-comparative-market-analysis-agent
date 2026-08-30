"""
Canonical property schema.

One provider (SimplyRETS) feeds this today, but the schema itself is the
contract between "whatever the provider returned" and everything downstream
(validation, dedup, the comparable engine, the briefing). Fields are named
for what they mean in this application, not copied verbatim from SimplyRETS'
RETS-flavored field names.

Kept deliberately small and tailored to comparable-home analysis — not a
general real-estate data model. Add a field only when the comparable engine
or the briefing actually needs it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FieldStatus(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    IMPLAUSIBLE = "implausible"


@dataclass
class FieldFlag:
    status: FieldStatus
    reason: str | None = None


@dataclass
class Address:
    full: str | None = None
    street_number: str | None = None
    street_name: str | None = None
    unit: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None


@dataclass
class GeoLocation:
    lat: float | None = None
    lng: float | None = None
    county: str | None = None
    market_area: str | None = None


@dataclass
class Characteristics:
    property_type: str | None = None       # raw SimplyRETS code, e.g. "RES" / "RNT" / "CND"
    property_subtype: str | None = None    # e.g. "SingleFamilyResidence" / "Condominium" / "Townhouse"
    bedrooms: int | None = None
    baths_full: int | None = None
    baths_half: int | None = None
    living_area_sqft: float | None = None
    lot_size_area: float | None = None     # numeric lot size; see Phase 1 audit — 0% populated on closed sales
    lot_size_units: str | None = None
    lot_size_text: str | None = None       # free-text fallback (SimplyRETS `property.lotSize`)
    year_built: int | None = None


@dataclass
class Transaction:
    status: str | None = None
    list_price: float | None = None
    list_date: str | None = None    # ISO 8601 string, as returned by the provider
    close_price: float | None = None
    close_date: str | None = None
    days_on_market: int | None = None


@dataclass
class Attribution:
    """Display-permission and attribution metadata. Kept even though it is
    null throughout the SimplyRETS trial data (Phase 1 audit §8) — real
    feeds populate it, and dropping it here would silently make correct
    IDX handling impossible later."""
    disclaimer: str | None = None
    internet_address_display: bool | None = None
    internet_entire_listing_display: bool | None = None


@dataclass
class CanonicalProperty:
    source: str                  # e.g. "simplyrets"
    source_listing_id: str       # provider's primary id (SimplyRETS mlsId), as a string
    address: Address = field(default_factory=Address)
    geo: GeoLocation = field(default_factory=GeoLocation)
    characteristics: Characteristics = field(default_factory=Characteristics)
    transaction: Transaction = field(default_factory=Transaction)
    attribution: Attribution = field(default_factory=Attribution)

    # Populated by validation.flag_fields — present/missing/implausible per
    # tracked field, keyed by a stable field name (see validation.py).
    field_flags: dict[str, FieldFlag] = field(default_factory=dict)

    # The untouched source record, retained for traceability (so the
    # briefing can always point back to "what the provider actually said").
    # Never used for calculations — those read only the typed fields above.
    raw: dict[str, Any] | None = None
