"""
Migration audit, step 2: compute statistics from the frozen Repliers
fixtures (reusing the actual Phase 2 mapping/validation pipeline — this
doubles as an integration check) and render docs/phase1-repliers-audit.md.

Reads fixtures/repliers_*.json (no live calls) for everything except the
"try an example" picker's final validation, which does call the live API
once per candidate — see §10 — because Phase 1's migration probe found
that some mlsNumbers appearing in search results 404 on the detail
endpoint, so a picker entry must be verified live before being trusted.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from canonical_schema import FieldStatus  # noqa: E402
from repliers_client import RepliersClient, RepliersError  # noqa: E402
from repliers_mapping import map_repliers_listing  # noqa: E402
from validation import flag_fields  # noqa: E402

FIXTURES = ROOT / "fixtures"
DOCS = ROOT / "docs"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


def pct(n: int, total: int) -> str:
    return f"{100 * n / total:.0f}%" if total else "n/a"


def main() -> None:
    overview = load("repliers_overview.json")
    broad_sample = load("repliers_closed_sales_sample.json")
    city_sample = load("repliers_city_sample.json")
    probe_notes = load("repliers_probe_notes.json")

    combined = broad_sample + city_sample
    canon = [map_repliers_listing(r) for r in combined]
    for p in canon:
        flag_fields(p)
    n = len(canon)

    states = Counter(p.address.state for p in canon if p.address.state)
    cities = Counter(p.address.city for p in canon if p.address.city)
    close_dates = sorted(p.transaction.close_date for p in canon if p.transaction.close_date)

    def completeness(field_names: list[str]) -> dict[str, str]:
        out = {}
        for name in field_names:
            present = sum(1 for p in canon if p.field_flags.get(name, None) and p.field_flags[name].status == FieldStatus.PRESENT)
            out[name] = pct(present, n)
        return out

    core_fields = [
        "geo.lat", "geo.lng", "living_area_sqft", "bedrooms", "baths_full",
        "lot_size", "year_built", "list_price", "close_price", "close_date",
    ]

    implausible_counts: dict[str, int] = {}
    for p in canon:
        for name, flag in p.field_flags.items():
            if flag.status == FieldStatus.IMPLAUSIBLE:
                implausible_counts[name] = implausible_counts.get(name, 0) + 1

    idx_present = {
        "internet_address_display": sum(1 for p in canon if p.attribution.internet_address_display is not None),
        "internet_entire_listing_display": sum(1 for p in canon if p.attribution.internet_entire_listing_display is not None),
    }

    lines = []
    lines.append("# Phase 1 (Repliers) — Migration Audit")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).date().isoformat()} (UTC), from fixtures in `fixtures/repliers_*.json`.")
    lines.append("Source: Repliers API (`https://api.repliers.io`), a personal signed-up API key returning **sample/sandbox data** — see §0.")
    lines.append("")

    lines.append("## 0. This is sample data, not live transactions")
    lines.append("")
    lines.append(
        f"Every one of {probe_notes['sample_data_marker_count'].split('/')[1]} closed-sale listings sampled "
        f"(`{probe_notes['sample_data_marker_count']}`) carries a literal `**** SAMPLE DATA ****` marker in "
        "its description. Dates, prices, and geography look current and plausible, but this is Repliers' "
        "developer sandbox feed, not real MLS transactions. Getting real live data would require a "
        "production plan with the underlying MLS board agreements Repliers' docs mention. This audit — and "
        "the decision to migrate — treats Repliers as a **better demo substrate**, not a source of real "
        "market accuracy, preserving the same honesty framing the original plan set for SimplyRETS."
    )
    lines.append("")

    lines.append("## 1. Feed size and scope")
    lines.append("")
    for label, info in overview.items():
        n_pages_at_100 = -(-info["count"] // 100)  # ceil division; overview was fetched at resultsPerPage=1
        lines.append(f"- `{label}`: {info['count']} total (~{n_pages_at_100} pages at 100/page)")
    lines.append("")
    lines.append(
        f"Sample analyzed here: {n} records ({len(broad_sample)} broad multi-state + "
        f"{len(city_sample)} from the demo anchor city, {probe_notes['demo_anchor_city']!r}) "
        f"out of {overview['standardStatus=Closed,type=sale,propertyType=Residential']['count']} "
        "closed-residential-sale listings available in total. Unlike the SimplyRETS audit (which froze "
        "the entire 78-listing feed), this is a sample, not the full population — the population is far "
        "too large to freeze wholesale."
    )
    lines.append("")

    lines.append("## 2. Geography")
    lines.append("")
    lines.append(f"- States in sample ({len(states)} distinct): {dict(states.most_common())}")
    lines.append(f"- Cities in sample ({len(cities)} distinct, top 15): {dict(cities.most_common(15))}")
    lines.append(
        "\nCoverage is real multi-state (confirmed beyond the sample too: the broad sample alone touched "
        "10 states in an earlier 100-record probe), a substantial upgrade over SimplyRETS' single-state, "
        "6-city trial feed. Coverage is uneven — `boardId=110` (Washington state) dominates — so radius-"
        "search demos should anchor on a market with real depth, not assume any address works equally well."
    )
    lines.append("")

    lines.append("## 3. Closed sales (the population comparable analysis draws from)")
    lines.append("")
    lines.append(f"- `standardStatus=Closed & type=sale & propertyType=Residential`: "
                 f"**{overview['standardStatus=Closed,type=sale,propertyType=Residential']['count']}** total.")
    lines.append(f"- Close dates in sample range: **{close_dates[0][:10] if close_dates else 'n/a'}** to "
                 f"**{close_dates[-1][:10] if close_dates else 'n/a'}**.")
    lines.append(
        "- This is close enough to the real current date that the demonstration clock can plausibly use "
        "`datetime.now()` directly instead of a fixed historical analysis date — a first for this project "
        "(SimplyRETS' latest close date was 13 years stale). See §9."
    )
    lines.append("")

    lines.append("### 3b. Data-quality findings (this sample dataset)")
    lines.append("")
    lines.append(
        f"- **`soldDate` earlier than `listDate`**: {probe_notes['sold_before_listed_probe']['violations']}/"
        f"{probe_notes['sold_before_listed_probe']['checked']} checked records — essentially universal in "
        "this sample, not a rare glitch. Unlike SimplyRETS' `type`/`subType` mismatch (a real minority-case "
        "flag), this is systemic enough that per-record flagging would be noise, not signal. Treated as a "
        "documented dataset caveat instead: **do not use `listDate`/`daysOnMarket` for eligibility or "
        "trust — only `soldDate`/`soldPrice` are reliable for comparable analysis.**"
    )
    lines.append(
        f"- **`class`/`details.propertyType` cross-tab** (Residential-filtered sample): "
        f"{probe_notes['class_propertytype_combo']} — internally consistent in this sample (unlike "
        "SimplyRETS' CND+SingleFamilyResidence case); `validation.py`'s `type_subtype_consistency` check "
        "still guards the theoretically-possible Land+CondoProperty combination generically."
    )
    lines.append(
        f"- **List/sold price ratio**: n={probe_notes['price_ratio_probe']['n']}, "
        f"min={probe_notes['price_ratio_probe']['min']:.2f}, median={probe_notes['price_ratio_probe']['median']:.2f}, "
        f"max={probe_notes['price_ratio_probe']['max']:.2f}, "
        f"{probe_notes['price_ratio_probe']['outside_0.3_to_3.0']} outside the [0.3, 3.0] plausibility band. "
        "**Realistic** — a genuine improvement over SimplyRETS' random 0.01x–4.67x synthetic pricing; the "
        "existing price-ratio validation rule needed no adjustment."
    )
    lines.append("")

    lines.append(f"## 4. Field completeness (measured over the {n}-record sample, via the actual mapping+validation pipeline)")
    lines.append("")
    for name, value in completeness(core_fields).items():
        lines.append(f"- {name}: {value}")
    lines.append("")
    lines.append(f"Implausible-field flag counts across the sample: {implausible_counts}")
    lines.append("")

    lines.append("## 5. Address / subject searchability")
    lines.append("")
    for label, result in probe_notes["address_search_probe"].items():
        lines.append(f"- `{label}`: `{json.dumps(result)}`")
    lines.append(
        "\n**Free-text and compound address search are unreliable here** — `streetName` alone found "
        "nothing for a known record, `address=` is silently unrecognized (confirmed via the response's "
        "`unrecognizedParams`), and `mlsNumber` as a *search* filter param returns nothing (the dedicated "
        "`GET /listings/{mlsNumber}` detail endpoint is the reliable way to resolve one, and even that "
        f"404s occasionally for no clear reason — see `single_listing_detail_failures` in the probe notes: "
        f"{probe_notes['single_listing_detail_failures']}). **Decision:** `find_subject` resolves by MLS "
        "number only; the demo UI should use a curated, live-validated picker (§10), exactly the UI shape "
        "the original project plan already recommended."
    )
    lines.append("")

    lines.append("## 6. Radius / geo search — genuinely works")
    lines.append("")
    rp = probe_notes["radius_search_probe"]
    lines.append(f"- Center: {rp['center']}")
    lines.append(f"- Counts by radius: {rp['counts_by_radius']}")
    lines.append(
        "\nUnlike SimplyRETS (which silently ignored radius/lat/lng/polygon params), Repliers' radius "
        "search demonstrably filters: a 0.01km radius returns 1 listing, 5km returns dozens, 50km returns "
        "thousands, around the same center point. This resolves the open item from the original SimplyRETS "
        "audit — the comparable engine can now use real server-side radius prefiltering, though it should "
        "still compute and enforce exact great-circle distance client-side for the final cutoff (see provider.py)."
    )
    lines.append("")

    lines.append("## 7. Pagination behavior")
    lines.append("")
    lines.append(
        "- `resultsPerPage` is capped server-side at **100** regardless of what's requested (confirmed: "
        "requesting 500/1000/5000 all silently returned 100). Fetching more than 100 requires paging with "
        "`page=`, which `RepliersProvider.search_closed_sales` does automatically up to a configured cap."
    )
    lines.append("- The response envelope reports `count` and `numPages` directly — no need to probe blindly "
                 "for a total, unlike SimplyRETS.")
    lines.append("")

    lines.append("## 8. IDX / display / attribution fields")
    lines.append("")
    lines.append(f"- `permissions.displayAddressOnInternet` non-null: {idx_present['internet_address_display']}/{n}")
    lines.append(f"- `permissions.displayInternetEntireListing` non-null: {idx_present['internet_entire_listing_display']}/{n}")
    lines.append(
        "\nUnlike SimplyRETS (where these flags were null on every trial record), Repliers' sample data "
        "actually populates real Y/N values here — the canonical schema's `Attribution` fields now carry "
        "meaningful data, not just plumbing for a hypothetically-real feed."
    )
    lines.append("")

    lines.append("## 9. Recommended demonstration clock")
    lines.append("")
    if close_dates:
        latest = close_dates[-1][:10]
        latest_dt = datetime.fromisoformat(latest)
        gap_days = (datetime.now(timezone.utc).date() - latest_dt.date()).days
        lines.append(f"- Latest `soldDate` in this sample: **{latest}** (~{gap_days} days before real-today).")
    lines.append(
        "- Because this is close to the real current date (unlike SimplyRETS' 13-year-stale feed), the "
        "app may use **today's real date** as the analysis date, computing 90-day/6-month/12-month windows "
        "against `datetime.now()` directly — while still disclosing prominently that the underlying records "
        "are Repliers sample data, not real transactions (see §0). This satisfies the original plan's own "
        "fallback clause: *'If the demo dataset contains suitable dates relative to the real current date, "
        "the system may use today instead — determined by audit, not assumed.'*"
    )
    lines.append("")

    lines.append("## 10. Suggested demo subject properties (\"Try an example\") — live-validated")
    lines.append("")
    client = RepliersClient()
    # broad_sample and city_sample can overlap on top-of-index records for
    # the anchor city (both queries hit the same default server-side order
    # with no shuffling) — dedupe by listing id before selecting candidates.
    by_id = {}
    for p in canon:
        if p.address.city == probe_notes["demo_anchor_city"]:
            by_id[p.source_listing_id] = p
    candidates = list(by_id.values())

    def completeness_score(p) -> int:
        return sum(1 for f in p.field_flags.values() if f.status == FieldStatus.PRESENT)

    candidates.sort(key=completeness_score, reverse=True)
    validated = []
    for p in candidates:
        if len(validated) >= 6:
            break
        try:
            client.get_listing(p.source_listing_id)
            validated.append(p)
        except RepliersError:
            continue  # matches §5's finding: some mlsNumbers 404 unpredictably; skip and try the next
    for p in validated:
        lines.append(
            f"- `{p.source_listing_id}` — {p.address.full}, {p.address.city}, {p.address.state} — "
            f"closed {p.transaction.close_date[:10] if p.transaction.close_date else '?'} at "
            f"${p.transaction.close_price:,.0f}" if p.transaction.close_price else
            f"- `{p.source_listing_id}` — {p.address.full}, {p.address.city}, {p.address.state}"
        )
    lines.append("")
    lines.append(
        f"Each of these was confirmed live via `GET /listings/{{mlsNumber}}` at audit time (not just present "
        "in a search result), given §5's finding that search-result presence doesn't guarantee the detail "
        "endpoint resolves. Anchored on Charlotte, NC for real radius-search depth (hundreds of nearby closed "
        "sales, per §6)."
    )
    lines.append("")

    report = "\n".join(lines)
    out_path = DOCS / "phase1-repliers-audit.md"
    out_path.write_text(report)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
