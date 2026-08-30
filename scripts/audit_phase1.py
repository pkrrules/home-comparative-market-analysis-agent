"""
Phase 1, step 2: compute the audit statistics from the frozen fixtures and
render docs/phase1-api-audit.md.

Reads only from fixtures/ (no live API calls) so the report is reproducible.
Run scripts/fetch_fixtures.py first (or again, to refresh the fixtures).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def pct(n: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{100 * n / total:.0f}%"


def field_present(record: dict, path: list[str]) -> bool:
    """True if the dotted path resolves to a non-None, non-empty value."""
    cur = record
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return False
        cur = cur[key]
    if cur is None:
        return False
    if isinstance(cur, str) and not cur.strip():
        return False
    return True


def main() -> None:
    options = load("options_properties.json")
    by_status = load("properties_by_status.json")
    all_listings = load("properties_all.json")
    probe_notes = load("probe_notes.json")

    n = len(all_listings)

    # --- geography / categories, derived from actual data since the
    # OPTIONS metadata enumerations (cities/counties/neighborhoods) come
    # back empty on this trial account ---
    cities = Counter(l["address"].get("city") for l in all_listings if l["address"].get("city"))
    states = Counter(l["address"].get("state") for l in all_listings if l["address"].get("state"))
    zips = Counter(l["address"].get("postalCode") for l in all_listings if l["address"].get("postalCode"))
    counties = Counter(l["geo"].get("county") for l in all_listings if l.get("geo", {}).get("county"))
    market_areas = Counter(l["geo"].get("marketArea") for l in all_listings if l.get("geo", {}).get("marketArea"))
    prop_types = Counter(l["property"].get("type") for l in all_listings if l["property"].get("type"))
    prop_subtypes = Counter(l["property"].get("subType") for l in all_listings if l["property"].get("subType"))
    statuses = Counter(l["mls"].get("status") for l in all_listings if l.get("mls", {}).get("status"))

    # --- closed sales ---
    # NOTE: property.type on the actual listing record is a short RETS code
    # ("RES"/"RNT"/"CND"), not the friendly label the OPTIONS metadata and the
    # `type=` query param use ("Residential"/"Rental"/"Condominium"/"Townhome").
    # `type=Residential` server-side maps to `RES` -- see section 3b below for
    # why matching on this code alone is still not a clean "single family home"
    # filter in this dataset.
    closed = by_status.get("Closed", [])
    closed_residential = [
        l for l in closed if l["property"].get("type") == "RES"
    ]
    close_dates = sorted(d for d in (parse_dt(l.get("sales", {}).get("closeDate")) for l in closed) if d)
    earliest_close = close_dates[0].date().isoformat() if close_dates else None
    latest_close = close_dates[-1].date().isoformat() if close_dates else None

    # --- field completeness (computed over the CLOSED set, since that's
    # the population the comparable engine actually draws from) ---
    def completeness(paths: dict[str, list[str]]) -> dict[str, str]:
        return {
            label: pct(sum(field_present(l, path) for l in closed), len(closed))
            for label, path in paths.items()
        }

    core_completeness = completeness({
        "coordinates (geo.lat)": ["geo", "lat"],
        "coordinates (geo.lng)": ["geo", "lng"],
        "living area (property.area)": ["property", "area"],
        "bedrooms": ["property", "bedrooms"],
        "bathsFull": ["property", "bathsFull"],
        "bathsHalf": ["property", "bathsHalf"],
        "lot size (property.lotSize text)": ["property", "lotSize"],
        "lot size (property.lotSizeArea numeric)": ["property", "lotSizeArea"],
        "year built": ["property", "yearBuilt"],
        "list price": ["listPrice"],
        "close price (sales.closePrice)": ["sales", "closePrice"],
        "close date (sales.closeDate)": ["sales", "closeDate"],
    })

    # --- price field semantics: does closePrice differ from listPrice, and
    # by how much (sanity: are these plausible, or all identical placeholders)? ---
    price_diffs = []
    for l in closed:
        lp = l.get("listPrice")
        cp = l.get("sales", {}).get("closePrice")
        if lp and cp:
            price_diffs.append((cp - lp) / lp)
    if price_diffs:
        avg_diff = sum(price_diffs) / len(price_diffs)
        pct_identical = sum(1 for d in price_diffs if d == 0) / len(price_diffs)
    else:
        avg_diff = None
        pct_identical = None

    # --- IDX / display / attribution fields ---
    idx_fields = ["internetAddressDisplay", "internetEntireListingDisplay"]
    idx_nonnull_counts = {f: sum(1 for l in all_listings if l.get(f) is not None) for f in idx_fields}
    disclaimer_present = sum(1 for l in all_listings if field_present(l, ["disclaimer"]))

    # --- report ---
    lines = []
    lines.append("# Phase 1 API Audit — SimplyRETS Demo Feed")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).date().isoformat()} (UTC), from fixtures in `fixtures/`.")
    lines.append("Source: SimplyRETS trial account (`simplyrets`/`simplyrets`), `https://api.simplyrets.com`.")
    lines.append("")

    lines.append("## 1. Feed size and scope")
    lines.append("")
    lines.append(f"- Total unique listings across all statuses: **{n}**")
    lines.append(f"- Per-status counts: {dict(statuses)}")
    lines.append(f"- Property types present: {dict(prop_types)}")
    lines.append(f"- Property subtypes present: {dict(prop_subtypes)}")
    lines.append(
        "- **Default `GET /properties` (no status param) excludes Closed listings** — "
        f"it returned {probe_notes['default_search_no_status_filter_count']} records, covering only "
        f"statuses {probe_notes['default_search_statuses_seen']}. Closed sales must be requested explicitly "
        "with `status=Closed`."
    )
    lines.append("")

    lines.append("## 2. Geography")
    lines.append("")
    lines.append(
        "`OPTIONS /properties` metadata enumerations for cities/counties/neighborhoods/areaMinor/features "
        "come back **empty** on this trial account (only `status` and `type` are populated — see "
        "`fixtures/options_properties.json`). Geography below is derived directly from the listing data instead."
    )
    lines.append("")
    lines.append(f"- States: {dict(states)}")
    lines.append(f"- Cities ({len(cities)} distinct): {dict(cities.most_common(15))}"
                 + (" …" if len(cities) > 15 else ""))
    lines.append(f"- ZIP codes ({len(zips)} distinct): {dict(zips.most_common(15))}"
                 + (" …" if len(zips) > 15 else ""))
    lines.append(f"- Counties: {dict(counties)}")
    lines.append(f"- Market areas / neighborhoods ({len(market_areas)} distinct): {dict(market_areas.most_common(10))}"
                 + (" …" if len(market_areas) > 10 else ""))
    lines.append("")

    lines.append("## 3. Closed sales (the population comparable analysis draws from)")
    lines.append("")
    lines.append(f"- Closed listings, all types: **{len(closed)}**")
    lines.append(f"- Closed listings, `property.type == 'RES'` (the code behind `type=Residential`): **{len(closed_residential)}**")
    lines.append(f"- Earliest closed-sale date (`sales.closeDate`): **{earliest_close}**")
    lines.append(f"- Latest closed-sale date (`sales.closeDate`): **{latest_close}**")
    lines.append("")
    lines.append(
        "This is a small, fixed trial dataset (13 closed sales total). Radius/date expansion logic and "
        "the human-in-the-loop approval flow should be expected to trigger often and are exercised by design, "
        "not as an edge case."
    )
    lines.append("")

    lines.append("### 3b. Data-quality finding: `property.type` / `property.subType` are inconsistent")
    lines.append("")
    type_subtype_combo = Counter(
        (l["property"].get("type"), l["property"].get("subType")) for l in all_listings
    )
    lines.append(
        "Cross-tabulating the two fields across all 78 listings shows combinations that shouldn't "
        "co-occur on real data, e.g.:"
    )
    for (t, st), cnt in sorted(type_subtype_combo.items(), key=lambda kv: -kv[1]):
        flag = " ⚠️ implausible" if t == "CND" and st == "SingleFamilyResidence" else ""
        lines.append(f"  - type=`{t}`, subType=`{st}` — {cnt} listings{flag}")
    lines.append(
        "\n`type=CND` (Condominium) paired with `subType=SingleFamilyResidence` occurs "
        f"{type_subtype_combo.get(('CND', 'SingleFamilyResidence'), 0)} times — this trial feed's type/subType "
        "fields are not internally consistent (expected, since it's synthetic demo data). "
        "**Action for Phase 2:** the Property/Data Agent's field-plausibility check must include a "
        "type/subType consistency rule and flag mismatches, rather than trusting `property.type` alone "
        "to mean \"single-family home.\""
    )
    lines.append("")

    lines.append("## 4. Field completeness (measured over the Closed population, n="
                  f"{len(closed)})")
    lines.append("")
    for label, value in core_completeness.items():
        lines.append(f"- {label}: {value}")
    lines.append("")

    lines.append("## 5. List price vs. close price semantics")
    lines.append("")
    lines.append("- `listPrice` (top-level) = the asking price at time of listing.")
    lines.append("- `sales.closePrice` = the final sale price, present only once a listing reaches `status: Closed`.")
    lines.append("- `sales.closeDate` = the closing date; this is the field the 90-day/6-month/12-month "
                 "windows should be computed against, not `listDate` or `modified`.")
    if avg_diff is not None:
        lines.append(
            f"- Across {len(price_diffs)} closed listings with both fields present: mean "
            f"(closePrice − listPrice) / listPrice = {avg_diff:+.1%}; "
            f"{pct_identical:.0%} have closePrice == listPrice exactly. "
            "Values vary and aren't placeholder-identical, so both fields are usable for a demo, "
            "but should be labeled clearly as synthetic in the briefing."
        )
    lines.append("")

    lines.append("## 6. Address searchability")
    lines.append("")
    addr_probe = probe_notes.get("address_search", {})
    for label, result in addr_probe.items():
        lines.append(f"- {label}: `{json.dumps(result)}`")
    lines.append(
        "\nDirect `q=<full address>` and `q=<street name>` text search both resolved the target listing "
        "reliably in this probe. This supports the recommended UI: an address-search box scoped to the "
        "demo dataset is workable, backed by `q=`, in addition to a preset picker."
    )
    lines.append("")

    lines.append("## 7. Pagination behavior")
    lines.append("")
    lines.append(
        f"- `limit` was accepted up to 500+ without truncation error; the feed itself is small enough "
        "(78 total, 13 closed) that no result set ever hit a server-side page cap in this probe."
    )
    lines.append(
        "- `offset` is validated server-side: requesting `offset >= <matching count>` for a filtered query "
        f"returns HTTP 400 `InvalidArguments: \"offset too high\"` "
        f"(see `fixtures/probe_notes.json.pagination_probe`), not an empty array. "
        "Pagination loops must stop on this error (or precede it by tracking a running count), not assume "
        "an empty page signals the end."
    )
    lines.append(
        "- No `X-Total-Count`-style header was inspected in this pass; total counts are only knowable by "
        "requesting a limit larger than the true population and counting the returned array."
    )
    lines.append("")

    lines.append("## 8. IDX / display / attribution fields")
    lines.append("")
    lines.append(
        f"- `internetAddressDisplay`: non-null on {idx_nonnull_counts['internetAddressDisplay']}/{n} listings."
    )
    lines.append(
        f"- `internetEntireListingDisplay`: non-null on {idx_nonnull_counts['internetEntireListingDisplay']}/{n} listings."
    )
    lines.append(f"- `disclaimer` text present on {disclaimer_present}/{n} listings.")
    lines.append(
        "\nBoth IDX display-permission flags are `null` throughout this trial dataset (they are not "
        "meaningfully populated on trial data). The canonical schema should still carry these two fields "
        "plus `disclaimer` through unmodified — defaulting missing/null display flags to the conservative "
        "(non-display) assumption — so the plumbing is correct even though the demo values are all null."
    )
    lines.append("")

    lines.append("## 9. Recommended demonstration clock")
    lines.append("")
    lines.append(f"- **Analysis date = latest closed-sale date in the dataset = `{latest_close}`.**")
    if latest_close:
        latest_dt = datetime.fromisoformat(latest_close)
        real_gap_years = (datetime.now(timezone.utc).date() - latest_dt.date()).days / 365.25
        lines.append(
            f"- This is ~{real_gap_years:.0f} years before the real current date — far too old to treat "
            "today's date as usable for the 90-day/6-month/12-month windows. Use the dataset-derived "
            "analysis date, not `datetime.now()`, for all recency filtering."
        )
    lines.append(
        "- Display prominently in the briefing: "
        f'"Demonstration analysis as of {latest_close}, using sample SimplyRETS records — '
        'not current market transactions."'
    )
    lines.append("")

    lines.append("## 10. Suggested demo subject properties (\"Try an example\")")
    lines.append("")
    # Prefer closed-residential listings with the most complete core fields, so
    # the demo path (which needs comps for the subject's own market area) works cleanly.
    def completeness_score(l: dict) -> int:
        paths = [["geo", "lat"], ["geo", "lng"], ["property", "area"], ["property", "bedrooms"],
                  ["property", "bathsFull"], ["property", "yearBuilt"], ["property", "lotSizeArea"]]
        return sum(field_present(l, p) for p in paths)

    candidates = sorted(closed_residential, key=completeness_score, reverse=True)[:8]
    for l in candidates:
        addr = l["address"].get("full")
        city = l["address"].get("city")
        st = l["address"].get("state")
        close_date = l.get("sales", {}).get("closeDate", "")[:10]
        close_price = l.get("sales", {}).get("closePrice")
        lines.append(f"- `{l['mlsId']}` — {addr}, {city}, {st} — closed {close_date} at ${close_price:,}"
                     if close_price else f"- `{l['mlsId']}` — {addr}, {city}, {st} — closed {close_date}")
    lines.append("")
    lines.append(
        "These are ranked by completeness of the fields the comparable engine needs "
        "(coordinates, living area, beds, baths, year built, lot size). Use them as the preset picker list; "
        "restrict any free-text address box to resolving against this same dataset."
    )
    lines.append("")

    lines.append("## 11. Open items for Phase 2")
    lines.append("")
    lines.append("- Confirm whether a bounding-box/polygon geo search (vs. plain `q=` text) is available on "
                 "this trial tier — not yet probed here; needed for the radius-expansion search design.")
    lines.append("- With only 8 closed-Residential sales total, radius/date expansion will need to reach "
                 "6–12 months and/or include non-Residential subtypes fairly often to hit the ≥3-comparable "
                 "target — confirm this against the success criterion during Phase 2 design, not assumed here.")
    lines.append("")

    report = "\n".join(lines)
    out_path = DOCS / "phase1-api-audit.md"
    out_path.write_text(report)
    print(f"wrote {out_path}")
    print()
    print(report)


if __name__ == "__main__":
    main()
