"""
Maps raw SimplyRETS listing dicts into CanonicalProperty records.

Pure and side-effect free: no network calls, no field-plausibility judgment
(that's validation.py). This module only answers "what did the provider
literally say", copied into the canonical shape with provider-specific
field names translated to ours. Missing raw fields become None; nothing is
inferred or defaulted here.
"""
from __future__ import annotations

from typing import Any

from canonical_schema import (
    Address,
    Attribution,
    CanonicalProperty,
    Characteristics,
    GeoLocation,
    Transaction,
)


def _get(d: dict[str, Any] | None, *path: str) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def map_simplyrets_listing(raw: dict[str, Any]) -> CanonicalProperty:
    address = Address(
        full=_get(raw, "address", "full"),
        street_number=_get(raw, "address", "streetNumberText") or _get(raw, "address", "streetNumber"),
        street_name=_get(raw, "address", "streetName"),
        unit=_get(raw, "address", "unit"),
        city=_get(raw, "address", "city"),
        state=_get(raw, "address", "state"),
        postal_code=_get(raw, "address", "postalCode"),
    )

    geo = GeoLocation(
        lat=_get(raw, "geo", "lat"),
        lng=_get(raw, "geo", "lng"),
        county=_get(raw, "geo", "county"),
        market_area=_get(raw, "geo", "marketArea"),
    )

    characteristics = Characteristics(
        property_type=_get(raw, "property", "type"),
        property_subtype=_get(raw, "property", "subType"),
        bedrooms=_get(raw, "property", "bedrooms"),
        baths_full=_get(raw, "property", "bathsFull"),
        baths_half=_get(raw, "property", "bathsHalf"),
        living_area_sqft=_get(raw, "property", "area"),
        lot_size_area=_get(raw, "property", "lotSizeArea"),
        lot_size_units=_get(raw, "property", "lotSizeAreaUnits"),
        lot_size_text=_get(raw, "property", "lotSize"),
        year_built=_get(raw, "property", "yearBuilt"),
    )

    transaction = Transaction(
        status=_get(raw, "mls", "status"),
        list_price=raw.get("listPrice"),
        list_date=raw.get("listDate"),
        close_price=_get(raw, "sales", "closePrice"),
        close_date=_get(raw, "sales", "closeDate"),
        days_on_market=_get(raw, "mls", "daysOnMarket"),
    )

    attribution = Attribution(
        disclaimer=raw.get("disclaimer"),
        internet_address_display=raw.get("internetAddressDisplay"),
        internet_entire_listing_display=raw.get("internetEntireListingDisplay"),
    )

    return CanonicalProperty(
        source="simplyrets",
        source_listing_id=str(raw.get("mlsId")),
        address=address,
        geo=geo,
        characteristics=characteristics,
        transaction=transaction,
        attribution=attribution,
        raw=raw,
    )
