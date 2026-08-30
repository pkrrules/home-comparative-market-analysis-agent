"""
Phase 1 (Repliers) / migration step 1: pull raw Repliers responses and
freeze them as fixtures.

Unlike the SimplyRETS Phase 1 fetch (which froze the *entire* feed — it was
only 78 records), Repliers' closed-sales population is large (tens of
thousands), so this freezes a representative SAMPLE, not everything. That
sample is what scripts/audit_repliers.py and the test suite work from.

Writes to fixtures/:
  - repliers_overview.json           count/statistics for a handful of key filter combos
  - repliers_closed_sales_sample.json a broad, multi-state sample of closed residential sales
  - repliers_city_sample.json         a single-city sample (denser, for radius-search demos)
  - repliers_single_listing_sample.json  one full GET /listings/{mlsNumber} record
  - repliers_probe_notes.json         ad-hoc probe results (radius search, param recognition,
                                       price-ratio sanity, class/type cross-tab, rate limit)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from repliers_client import RepliersClient, RepliersError  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)

SAMPLE_PAGES = 3        # 3 x 100 = 300 records for the broad sample
CITY_SAMPLE_PAGES = 2   # 2 x 100 = 200 records for the city-scoped sample
DEMO_ANCHOR_CITY = "Charlotte"  # chosen for volume: 916 closed sales in a quick probe


def save(name: str, data) -> None:
    path = FIXTURES_DIR / name
    path.write_text(json.dumps(data, indent=2, sort_keys=False))
    print(f"wrote {path} ({len(json.dumps(data))} bytes)")


def fetch_pages(client: RepliersClient, params: dict, n_pages: int) -> list[dict]:
    # Pagination param is `pageNum`, not `page` — `page=` is silently
    # accepted-and-ignored by this API (confirmed: it shows up in the
    # response's own `unrecognizedParams`), so using it here would have
    # quietly re-fetched page 1 over and over. See repliers_provider.py.
    out = []
    for page_num in range(1, n_pages + 1):
        envelope = client.search_listings(**params, resultsPerPage=100, pageNum=page_num)
        out.extend(envelope.get("listings", []))
        if len(envelope.get("listings", [])) < 100:
            break
    return out


def main() -> None:
    client = RepliersClient()
    probe_notes: dict = {}

    # 1. Overview: counts for the filter combinations the provider/agent rely on
    overview = {}
    for label, params in {
        "all": {},
        "standardStatus=Closed": {"standardStatus": "Closed"},
        "standardStatus=Closed,type=sale": {"standardStatus": "Closed", "type": "sale"},
        "standardStatus=Closed,type=lease": {"standardStatus": "Closed", "type": "lease"},
        "standardStatus=Closed,type=sale,propertyType=Residential": {
            "standardStatus": "Closed", "type": "sale", "propertyType": "Residential",
        },
        "status=U": {"status": "U"},
    }.items():
        envelope = client.search_listings(**params, resultsPerPage=1)
        overview[label] = {"count": envelope.get("count"), "numPages": envelope.get("numPages")}
        print(f"{label}: count={envelope.get('count')}")
    save("repliers_overview.json", overview)

    # 2. Broad, multi-state sample of closed residential sales
    broad_sample = fetch_pages(
        client,
        {"standardStatus": "Closed", "type": "sale", "propertyType": "Residential"},
        SAMPLE_PAGES,
    )
    save("repliers_closed_sales_sample.json", broad_sample)

    # 3. Single-city sample (denser — supports a meaningful radius-search demo)
    city_sample = fetch_pages(
        client,
        {"standardStatus": "Closed", "type": "sale", "city": DEMO_ANCHOR_CITY},
        CITY_SAMPLE_PAGES,
    )
    save("repliers_city_sample.json", city_sample)
    probe_notes["demo_anchor_city"] = DEMO_ANCHOR_CITY
    probe_notes["demo_anchor_city_sample_count"] = len(city_sample)

    # 4. Single listing detail. NOTE: some mlsNumbers that appear in search
    # results 404 on GET /listings/{mlsNumber} with no clean pattern by board
    # or permissions (confirmed: 2/20 failed in one probe, including a
    # displayPublic='Y' record) — a sandbox quirk, not something this code
    # can predict. Try candidates until one resolves.
    detail = None
    detail_failures = []
    for candidate in broad_sample[:10]:
        mls = candidate["mlsNumber"]
        try:
            detail = client.get_listing(mls)
            break
        except RepliersError as e:
            detail_failures.append({"mlsNumber": mls, "status": e.status_code})
    if detail:
        save("repliers_single_listing_sample.json", detail)
    probe_notes["single_listing_detail_failures"] = detail_failures

    # 5. Radius-search probe: confirm it actually filters (not just accepted-and-ignored)
    if broad_sample:
        subject = broad_sample[0]
        lat, lng = subject["map"]["latitude"], subject["map"]["longitude"]
        radius_results = {}
        for label, radius in [("tiny_0.01km", 0.01), ("5km", 5), ("50km", 50)]:
            envelope = client.search_listings(
                standardStatus="Closed", lat=lat, long=lng, radius=radius, resultsPerPage=1
            )
            radius_results[label] = envelope.get("count")
        probe_notes["radius_search_probe"] = {
            "center": {"lat": lat, "lng": lng}, "counts_by_radius": radius_results,
        }

    # 6. Param-recognition probe: which address-search params are real vs. silently ignored
    address_probe = {}
    for label, params in {
        "streetNumber_only": {"streetNumber": subject["address"].get("streetNumber")},
        "streetName_only": {"streetName": subject["address"].get("streetName")},
        "address_free_text": {"address": subject["address"].get("streetName") or ""},
        "mlsNumber_as_search_param": {"mlsNumber": subject["mlsNumber"]},
    }.items():
        envelope = client.search_listings(**params, resultsPerPage=1)
        address_probe[label] = {
            "count": envelope.get("count"),
            "unrecognizedParams": envelope.get("unrecognizedParams"),
        }
    probe_notes["address_search_probe"] = address_probe

    # 7. list/sold price ratio sanity, and listDate vs soldDate ordering
    ratios = []
    date_order_violations = 0
    date_pairs_checked = 0
    for l in broad_sample:
        lp, sp = l.get("listPrice"), l.get("soldPrice")
        if lp and sp:
            ratios.append(sp / lp)
        ld, sd = l.get("listDate"), l.get("soldDate")
        if ld and sd:
            date_pairs_checked += 1
            if sd < ld:
                date_order_violations += 1
    ratios.sort()
    probe_notes["price_ratio_probe"] = {
        "n": len(ratios),
        "min": ratios[0] if ratios else None,
        "median": ratios[len(ratios) // 2] if ratios else None,
        "max": ratios[-1] if ratios else None,
        "outside_0.3_to_3.0": sum(1 for r in ratios if r < 0.3 or r > 3.0),
    }
    probe_notes["sold_before_listed_probe"] = {
        "violations": date_order_violations,
        "checked": date_pairs_checked,
        "note": "soldDate earlier than listDate — a data-quality caveat of this sample "
                "dataset, not a per-record plausibility rule (see migration notes).",
    }

    # 8. class/propertyType cross-tab and "SAMPLE DATA" marker frequency
    from collections import Counter
    combo = Counter((l.get("class"), l.get("details", {}).get("propertyType")) for l in broad_sample)
    probe_notes["class_propertytype_combo"] = {f"{k[0]}|{k[1]}": v for k, v in combo.items()}
    sample_marked = sum(
        1 for l in broad_sample if "SAMPLE DATA" in (l.get("details", {}).get("description") or "")
    )
    probe_notes["sample_data_marker_count"] = f"{sample_marked}/{len(broad_sample)}"

    save("repliers_probe_notes.json", probe_notes)
    print("\nDone. See fixtures/repliers_probe_notes.json for raw probe results.")


if __name__ == "__main__":
    main()
