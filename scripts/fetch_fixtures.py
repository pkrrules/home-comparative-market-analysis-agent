"""
Phase 1, step 1: pull raw SimplyRETS responses and freeze them as fixtures.

Freezing responses now means:
  - later phases (canonical schema, comparable engine, agents) can be built
    and tested against stable data instead of a live, mutable demo feed.
  - the Phase 1 audit report is reproducible from committed files.

Writes to fixtures/:
  - options_properties.json      raw OPTIONS /properties metadata
  - properties_by_status.json    {status: [listings]} for every status the
                                  feed's metadata advertises
  - properties_all.json          de-duplicated union of the above, keyed by mlsId
  - single_property_sample.json  GET /properties/{mlsId} for one listing
  - probe_notes.json             results of ad-hoc probes (pagination ceiling,
                                  address search, default-status behavior)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from simplyrets_client import SimplyRETSClient, SimplyRETSError  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)


def save(name: str, data) -> None:
    path = FIXTURES_DIR / name
    path.write_text(json.dumps(data, indent=2, sort_keys=False))
    print(f"wrote {path} ({len(json.dumps(data))} bytes)")


def main() -> None:
    client = SimplyRETSClient()
    probe_notes: dict = {}

    # 1. Feed metadata
    options = client.options_properties()
    save("options_properties.json", options)
    statuses = options.get("fields", {}).get("status", []) or []
    probe_notes["metadata_enumerations_populated"] = {
        k: bool(v) for k, v in options.get("fields", {}).items()
    }

    # 2. Default (no status filter) population, to learn the default status scope
    default_pop = client.search_properties(limit=500)
    probe_notes["default_search_no_status_filter_count"] = len(default_pop)
    probe_notes["default_search_statuses_seen"] = sorted(
        {p.get("mls", {}).get("status") for p in default_pop}
    )

    # 3. Pull every status explicitly (small demo feed: single page per status
    #    is enough, but we still probe the ceiling below).
    by_status: dict[str, list] = {}
    for status in statuses:
        listings = client.search_properties(status=status, limit=500)
        by_status[status] = listings
        print(f"status={status}: {len(listings)} listings")
    save("properties_by_status.json", by_status)

    # 4. De-duplicate into one master set keyed by mlsId
    all_by_id: dict[str, dict] = {}
    for listings in by_status.values():
        for listing in listings:
            all_by_id[str(listing["mlsId"])] = listing
    all_listings = list(all_by_id.values())
    save("properties_all.json", all_listings)
    probe_notes["union_unique_listing_count"] = len(all_listings)
    probe_notes["sum_of_per_status_counts"] = sum(len(v) for v in by_status.values())

    # 5. Pagination ceiling probe: offset just past the smallest status's count
    closed = by_status.get("Closed", [])
    probe_notes["pagination_probe"] = {}
    if closed:
        try:
            client.search_properties(status="Closed", offset=len(closed))
            probe_notes["pagination_probe"]["offset_at_count"] = "did not error"
        except SimplyRETSError as e:
            probe_notes["pagination_probe"]["offset_at_count"] = str(e)

    # 6. Single-property detail endpoint
    if all_listings:
        sample_id = str(all_listings[0]["mlsId"])
        try:
            detail = client.get_property(sample_id)
            save("single_property_sample.json", detail)
            probe_notes["get_by_mls_id"] = "ok"
        except SimplyRETSError as e:
            probe_notes["get_by_mls_id"] = str(e)

    # 7. Address text-search probe: can we reliably find one known listing by address?
    probe_notes["address_search"] = {}
    if all_listings:
        target = all_listings[0]
        full_addr = target["address"].get("full", "")
        street_name = target["address"].get("streetName", "")
        for label, q in [("full_address", full_addr), ("street_name_only", street_name)]:
            try:
                results = client.search_properties(q=q, limit=50)
                found = any(str(r["mlsId"]) == str(target["mlsId"]) for r in results)
                probe_notes["address_search"][label] = {
                    "query": q,
                    "result_count": len(results),
                    "target_found": found,
                }
            except SimplyRETSError as e:
                probe_notes["address_search"][label] = {"query": q, "error": str(e)}

    save("probe_notes.json", probe_notes)
    print("\nDone. See fixtures/probe_notes.json for raw probe results.")


if __name__ == "__main__":
    main()
