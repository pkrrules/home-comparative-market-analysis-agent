"""
Maps raw Repliers listing dicts into CanonicalProperty records.

Pure and side-effect free, mirroring simplyrets_mapping.py's contract: no
network calls, no plausibility judgment (that's validation.py) — just
"what did the provider literally say", translated into the canonical shape.

Field choices below are grounded in docs/phase2b-repliers-migration.md
(built by inspecting real raw records, not guessed from docs alone).
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


def _to_float(value: Any) -> float | None:
    """Repliers sends several numeric fields (sqft, lot size) as strings."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _yn_to_bool(value: Any) -> bool | None:
    """Repliers' permissions.* fields are 'Y'/'N' strings, not booleans."""
    if value is None:
        return None
    return str(value).strip().upper() == "Y"


def _build_full_address(addr: dict[str, Any]) -> str | None:
    parts = [
        addr.get("streetNumber"),
        addr.get("streetDirectionPrefix"),
        addr.get("streetName"),
        addr.get("streetSuffix"),
        addr.get("streetDirection"),
    ]
    core = " ".join(str(p) for p in parts if p)
    if addr.get("unitNumber"):
        core = f"{core} Unit {addr['unitNumber']}" if core else f"Unit {addr['unitNumber']}"
    return core or None


def map_repliers_listing(raw: dict[str, Any]) -> CanonicalProperty:
    raw_address = raw.get("address") or {}

    address = Address(
        full=_build_full_address(raw_address),
        street_number=raw_address.get("streetNumber"),
        street_name=raw_address.get("streetName"),
        unit=raw_address.get("unitNumber"),
        city=raw_address.get("city"),
        state=raw_address.get("state"),
        postal_code=raw_address.get("zip"),
    )

    geo = GeoLocation(
        lat=_get(raw, "map", "latitude"),
        lng=_get(raw, "map", "longitude"),
        county=raw_address.get("area"),          # Repliers' "area" is county-like (e.g. "Pierce")
        market_area=raw_address.get("neighborhood"),
    )

    # property_type/subtype mirror SimplyRETS' broad/specific split, but
    # from Repliers' own vocabulary: details.propertyType is the broad
    # transaction category ("Residential"/"Land"/"Residential Lease"/
    # "Residential Income"); class is the structural category
    # ("ResidentialProperty"/"CondoProperty"). See migration notes §3b.
    characteristics = Characteristics(
        property_type=_get(raw, "details", "propertyType"),
        property_subtype=raw.get("class"),
        bedrooms=_to_int(_get(raw, "details", "numBedrooms")),
        baths_full=_to_int(_get(raw, "details", "numBathrooms")),
        baths_half=_to_int(_get(raw, "details", "numBathroomsHalf")),
        living_area_sqft=_to_float(_get(raw, "details", "sqft")),
        lot_size_area=_to_float(_get(raw, "lot", "squareFeet")),
        lot_size_units="sqft" if _get(raw, "lot", "squareFeet") is not None else None,
        lot_size_text=_get(raw, "lot", "size"),
        year_built=_to_int(_get(raw, "details", "yearBuilt")),
    )

    transaction = Transaction(
        status=raw.get("standardStatus"),
        list_price=_to_float(raw.get("listPrice")),
        list_date=raw.get("listDate"),
        close_price=_to_float(raw.get("soldPrice")),
        close_date=raw.get("soldDate"),
        days_on_market=_to_int(raw.get("daysOnMarket")),
    )

    attribution = Attribution(
        disclaimer=None,  # Repliers has no single equivalent field in this trial data
        internet_address_display=_yn_to_bool(_get(raw, "permissions", "displayAddressOnInternet")),
        internet_entire_listing_display=_yn_to_bool(_get(raw, "permissions", "displayInternetEntireListing")),
    )

    return CanonicalProperty(
        source="repliers",
        source_listing_id=str(raw.get("mlsNumber")),
        address=address,
        geo=geo,
        characteristics=characteristics,
        transaction=transaction,
        attribution=attribution,
        raw=raw,
    )
