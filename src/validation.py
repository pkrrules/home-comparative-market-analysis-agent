"""
Field-level validation: labels each tracked field on a CanonicalProperty as
present, missing, or implausible.

This module only flags — it does not decide whether a record is usable for
comparable analysis (that eligibility judgment belongs to the comparable
analysis engine / Agent 2). Agent 1's job is to make the confidence picture
explicit so downstream logic and the briefing can reason about it instead of
silently trusting every field.

Bounds below are deliberately generous sanity checks, not market judgment —
they exist to catch bad/synthetic data (nulls, placeholder zeros, swapped
fields), not to second-guess plausible-but-unusual real values.
"""
from __future__ import annotations

from datetime import datetime, timezone

from canonical_schema import CanonicalProperty, FieldFlag, FieldStatus

# Fields a comparable-home analysis fundamentally depends on. Used by Agent 1
# to decide whether a record is worth keeping at all (see data_agent.py),
# separately from the fine-grained flags this module produces for every field.
HARD_REQUIRED_FIELDS = [
    "geo.lat",
    "geo.lng",
    "close_date",
    "close_price",
    "living_area_sqft",
]

# type -> subtypes considered internally consistent for that type code.
# `None` subtype is always allowed (SimplyRETS leaves it blank often).
# See Phase 1 audit §3b: type=CND paired with SingleFamilyResidence/Townhouse
# occurs in this trial feed and is not a plausible combination.
_CONSISTENT_SUBTYPES_BY_TYPE = {
    "CND": {None, "Condominium"},
    "RNT": None,  # no constraint — rentals span house/condo/apartment
    "RES": None,  # no constraint — RES is used broadly across subtypes here
}

_CURRENT_YEAR = datetime.now(timezone.utc).year


def _set(flags: dict[str, FieldFlag], name: str, status: FieldStatus, reason: str | None = None) -> None:
    flags[name] = FieldFlag(status=status, reason=reason)


def flag_fields(prop: CanonicalProperty) -> dict[str, FieldFlag]:
    """Populate prop.field_flags in place and return it."""
    flags: dict[str, FieldFlag] = {}
    c = prop.characteristics
    t = prop.transaction
    g = prop.geo

    # --- coordinates ---
    if g.lat is None or g.lng is None:
        _set(flags, "geo.lat", FieldStatus.MISSING if g.lat is None else FieldStatus.PRESENT)
        _set(flags, "geo.lng", FieldStatus.MISSING if g.lng is None else FieldStatus.PRESENT)
    else:
        plausible_lat = -90 <= g.lat <= 90 and not (g.lat == 0 and g.lng == 0)
        plausible_lng = -180 <= g.lng <= 180
        # Loose US-plus-territories sanity band; flags obviously wrong data
        # (null island, swapped lat/lng, out-of-range values) without
        # asserting anything about which US region is "correct".
        in_us_band = 15 <= g.lat <= 72 and -180 <= g.lng <= -60
        if not (plausible_lat and plausible_lng) or not in_us_band:
            reason = f"lat={g.lat}, lng={g.lng} outside plausible US range"
            _set(flags, "geo.lat", FieldStatus.IMPLAUSIBLE, reason)
            _set(flags, "geo.lng", FieldStatus.IMPLAUSIBLE, reason)
        else:
            _set(flags, "geo.lat", FieldStatus.PRESENT)
            _set(flags, "geo.lng", FieldStatus.PRESENT)

    # --- living area ---
    if c.living_area_sqft is None:
        _set(flags, "living_area_sqft", FieldStatus.MISSING)
    elif c.living_area_sqft <= 0 or c.living_area_sqft > 50_000:
        _set(flags, "living_area_sqft", FieldStatus.IMPLAUSIBLE, f"value={c.living_area_sqft}")
    else:
        _set(flags, "living_area_sqft", FieldStatus.PRESENT)

    # --- bedrooms / bathrooms ---
    for name, value in [("bedrooms", c.bedrooms), ("baths_full", c.baths_full), ("baths_half", c.baths_half)]:
        if value is None:
            _set(flags, name, FieldStatus.MISSING)
        elif value < 0 or value > 20:
            _set(flags, name, FieldStatus.IMPLAUSIBLE, f"value={value}")
        else:
            _set(flags, name, FieldStatus.PRESENT)

    # --- lot size: numeric field, with the free-text field as a fallback
    # note only (Phase 1 audit: lot_size_area is 0% populated on closed
    # sales in this feed, while the text field is 100% populated) ---
    if c.lot_size_area is not None:
        if c.lot_size_area <= 0:
            _set(flags, "lot_size", FieldStatus.IMPLAUSIBLE, f"value={c.lot_size_area}")
        else:
            _set(flags, "lot_size", FieldStatus.PRESENT)
    elif c.lot_size_text:
        _set(flags, "lot_size", FieldStatus.MISSING, "numeric lotSizeArea absent; text description present as fallback")
    else:
        _set(flags, "lot_size", FieldStatus.MISSING)

    # --- year built ---
    if c.year_built is None:
        _set(flags, "year_built", FieldStatus.MISSING)
    elif c.year_built < 1800 or c.year_built > _CURRENT_YEAR + 1:
        _set(flags, "year_built", FieldStatus.IMPLAUSIBLE, f"value={c.year_built}")
    else:
        _set(flags, "year_built", FieldStatus.PRESENT)

    # --- prices ---
    if t.list_price is None:
        _set(flags, "list_price", FieldStatus.MISSING)
    elif t.list_price <= 0:
        _set(flags, "list_price", FieldStatus.IMPLAUSIBLE, f"value={t.list_price}")
    else:
        _set(flags, "list_price", FieldStatus.PRESENT)

    if t.close_price is None:
        _set(flags, "close_price", FieldStatus.MISSING)
    elif t.close_price <= 0:
        _set(flags, "close_price", FieldStatus.IMPLAUSIBLE, f"value={t.close_price}")
    elif t.list_price and t.list_price > 0:
        ratio = t.close_price / t.list_price
        if ratio < 0.3 or ratio > 3.0:
            _set(
                flags, "close_price", FieldStatus.IMPLAUSIBLE,
                f"close/list ratio={ratio:.2f} (close={t.close_price}, list={t.list_price})",
            )
        else:
            _set(flags, "close_price", FieldStatus.PRESENT)
    else:
        _set(flags, "close_price", FieldStatus.PRESENT)

    if t.close_date is None:
        _set(flags, "close_date", FieldStatus.MISSING)
    else:
        _set(flags, "close_date", FieldStatus.PRESENT)

    # --- status / sales-data consistency ---
    # find_subject can resolve a listing of any status (Active, Pending, ...),
    # not just Closed. A non-closed listing that already carries sales.closeDate
    # / closePrice is internally inconsistent (seen in this trial feed — see
    # fixtures/single_property_sample.json, status=Active with a populated
    # sales block) and should not be read as a real closing.
    if t.status and t.status != "Closed" and (t.close_date or t.close_price):
        _set(
            flags, "status_consistency", FieldStatus.IMPLAUSIBLE,
            f"status={t.status!r} but sales.closeDate/closePrice are populated",
        )
    else:
        _set(flags, "status_consistency", FieldStatus.PRESENT)

    # --- type / subtype consistency (composite cross-field check) ---
    allowed = _CONSISTENT_SUBTYPES_BY_TYPE.get(c.property_type)
    if allowed is not None and c.property_subtype not in allowed:
        _set(
            flags, "type_subtype_consistency", FieldStatus.IMPLAUSIBLE,
            f"type={c.property_type!r} with subType={c.property_subtype!r} is not a consistent combination",
        )
    else:
        _set(flags, "type_subtype_consistency", FieldStatus.PRESENT)

    prop.field_flags = flags
    return flags


def missing_hard_requirements(prop: CanonicalProperty) -> list[str]:
    """Which of HARD_REQUIRED_FIELDS are entirely MISSING (None) on this
    record — i.e. a comparable-home calculation is literally impossible,
    not merely suspicious. An empty list means every hard-required field
    has *some* value.

    Deliberately does not treat IMPLAUSIBLE as missing here: an implausible
    close price (say) is still a value the record can be scored and shown
    with — deciding whether to exclude it, and explaining why, is the
    comparable analysis engine / Agent 2's job (eligibility rules), not
    Agent 1's. Agent 1's role stops at making the flag visible.
    """
    problems = []
    for name in HARD_REQUIRED_FIELDS:
        flag = prop.field_flags.get(name)
        if flag is None or flag.status == FieldStatus.MISSING:
            problems.append(name)
    return problems
