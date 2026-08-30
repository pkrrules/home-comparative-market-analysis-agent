"""
Deduplicates a list of CanonicalProperty records.

Two duplicate signatures, per the project plan ("deduplicate by MLS ID,
address, and transaction facts"):

  1. Exact same (source, source_listing_id) — defensive; the provider layer
     shouldn't produce these, but a dedup pass that trusts the id alone is
     the shallowest possible check and no fixture from Phase 1 needed it.
  2. Same normalized address + same close date + same close price, under
     *different* listing ids — the shape a real duplicate takes when the
     same sale is re-listed or (in a future multi-provider world) reported
     by two sources. Worth keeping even with a single provider today: it's
     the seam that would matter as soon as a second provider is added, and
     it's cheap to test now with synthetic fixtures.

Whichever record in a duplicate group has fewer MISSING/IMPLAUSIBLE field
flags is kept; ties keep the first one encountered. Every drop is recorded
with a reason, so the pipeline's output stays traceable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from canonical_schema import CanonicalProperty, FieldStatus


@dataclass
class DedupDrop:
    dropped_id: str
    kept_id: str
    reason: str


def _normalize_address(addr: str | None) -> str:
    if not addr:
        return ""
    addr = addr.lower().strip()
    addr = re.sub(r"[^a-z0-9]+", " ", addr)
    return re.sub(r"\s+", " ", addr).strip()


def _quality_score(prop: CanonicalProperty) -> int:
    """Higher = fewer problems. Used only to pick which duplicate to keep."""
    return sum(1 for f in prop.field_flags.values() if f.status == FieldStatus.PRESENT)


def _better(a: CanonicalProperty, b: CanonicalProperty) -> CanonicalProperty:
    return a if _quality_score(a) >= _quality_score(b) else b


def deduplicate(properties: list[CanonicalProperty]) -> tuple[list[CanonicalProperty], list[DedupDrop]]:
    drops: list[DedupDrop] = []

    # Pass 1: exact (source, source_listing_id)
    by_id: dict[tuple[str, str], CanonicalProperty] = {}
    for prop in properties:
        key = (prop.source, prop.source_listing_id)
        if key not in by_id:
            by_id[key] = prop
            continue
        existing = by_id[key]
        kept = _better(existing, prop)
        dropped = prop if kept is existing else existing
        by_id[key] = kept
        drops.append(DedupDrop(
            dropped_id=dropped.source_listing_id, kept_id=kept.source_listing_id,
            reason=f"exact duplicate source_listing_id ({prop.source}:{prop.source_listing_id})",
        ))
    stage1 = list(by_id.values())

    # Pass 2: normalized address + close date + close price, across
    # different listing ids
    by_signature: dict[tuple[str, str | None, float | None], int] = {}  # signature -> index in result
    result: list[CanonicalProperty] = []
    for prop in stage1:
        sig = (
            _normalize_address(prop.address.full),
            prop.transaction.close_date,
            prop.transaction.close_price,
        )
        if not sig[0] or sig[1] is None or sig[2] is None:
            # Not enough signal to claim a match either way — keep as-is.
            result.append(prop)
            continue
        if sig not in by_signature:
            by_signature[sig] = len(result)
            result.append(prop)
            continue
        existing = result[by_signature[sig]]
        kept = _better(existing, prop)
        dropped = prop if kept is existing else existing
        if kept is not existing:
            result[by_signature[sig]] = kept
        drops.append(DedupDrop(
            dropped_id=dropped.source_listing_id, kept_id=kept.source_listing_id,
            reason=(
                f"same address+close_date+close_price as {kept.source}:{kept.source_listing_id} "
                f"(address={prop.address.full!r}, close_date={sig[1]}, close_price={sig[2]})"
            ),
        ))

    return result, drops
