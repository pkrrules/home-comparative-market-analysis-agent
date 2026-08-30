# Phase 1 API Audit — SimplyRETS Demo Feed

Generated: 2026-08-30 (UTC), from fixtures in `fixtures/`.
Source: SimplyRETS trial account (`simplyrets`/`simplyrets`), `https://api.simplyrets.com`.

## 1. Feed size and scope

- Total unique listings across all statuses: **78**
- Per-status counts: {'Active': 42, 'Pending': 23, 'Closed': 13}
- Property types present: {'RES': 53, 'RNT': 12, 'CND': 13}
- Property subtypes present: {'Condominium': 16, 'Townhouse': 13, 'SingleFamilyResidence': 19}
- **Default `GET /properties` (no status param) excludes Closed listings** — it returned 65 records, covering only statuses ['Active', 'Pending']. Closed sales must be requested explicitly with `status=Closed`.

## 2. Geography

`OPTIONS /properties` metadata enumerations for cities/counties/neighborhoods/areaMinor/features come back **empty** on this trial account (only `status` and `type` are populated — see `fixtures/options_properties.json`). Geography below is derived directly from the listing data instead.

- States: {'Texas': 78}
- Cities (6 distinct): {'Oak Ridge': 18, 'Houston': 14, 'Tomball': 14, 'Cypress': 13, 'The Woodlands': 11, 'Katy': 8}
- ZIP codes (28 distinct): {'77433': 12, '77429': 6, '77018': 6, '77007': 5, '77095': 4, '77024': 4, '77096': 3, '77004': 3, '77346': 3, '77375': 3, '77379': 2, '77006': 2, '77377': 2, '77055': 2, '77008': 2} …
- Counties: {'North': 15, 'West': 26, 'East': 19, 'South': 18}
- Market areas / neighborhoods (30 distinct): {'Cypress North': 11, 'Memorial West': 5, 'Copperfield Area': 5, 'Meyerland Area': 4, 'Cypress South': 4, 'Champions Area': 4, 'Spring/Klein/Tomball': 4, 'Montrose': 3, '1960/Cypress Creek South': 3, 'Garden Oaks': 3} …

## 3. Closed sales (the population comparable analysis draws from)

- Closed listings, all types: **13**
- Closed listings, `property.type == 'RES'` (the code behind `type=Residential`): **8**
- Earliest closed-sale date (`sales.closeDate`): **1990-02-19**
- Latest closed-sale date (`sales.closeDate`): **2013-09-27**

This is a small, fixed trial dataset (13 closed sales total). Radius/date expansion logic and the human-in-the-loop approval flow should be expected to trigger often and are exercised by design, not as an edge case.

### 3b. Data-quality finding: `property.type` / `property.subType` are inconsistent

Cross-tabulating the two fields across all 78 listings shows combinations that shouldn't co-occur on real data, e.g.:
  - type=`RES`, subType=`SingleFamilyResidence` — 16 listings
  - type=`RES`, subType=`Condominium` — 14 listings
  - type=`RES`, subType=`None` — 12 listings
  - type=`RNT`, subType=`None` — 12 listings
  - type=`RES`, subType=`Townhouse` — 11 listings
  - type=`CND`, subType=`None` — 6 listings
  - type=`CND`, subType=`SingleFamilyResidence` — 3 listings ⚠️ implausible
  - type=`CND`, subType=`Condominium` — 2 listings
  - type=`CND`, subType=`Townhouse` — 2 listings

`type=CND` (Condominium) paired with `subType=SingleFamilyResidence` occurs 3 times — this trial feed's type/subType fields are not internally consistent (expected, since it's synthetic demo data). **Action for Phase 2:** the Property/Data Agent's field-plausibility check must include a type/subType consistency rule and flag mismatches, rather than trusting `property.type` alone to mean "single-family home."

## 4. Field completeness (measured over the Closed population, n=13)

- coordinates (geo.lat): 100%
- coordinates (geo.lng): 100%
- living area (property.area): 100%
- bedrooms: 100%
- bathsFull: 100%
- bathsHalf: 100%
- lot size (property.lotSize text): 100%
- lot size (property.lotSizeArea numeric): 0%
- year built: 100%
- list price: 100%
- close price (sales.closePrice): 100%
- close date (sales.closeDate): 100%

## 5. List price vs. close price semantics

- `listPrice` (top-level) = the asking price at time of listing.
- `sales.closePrice` = the final sale price, present only once a listing reaches `status: Closed`.
- `sales.closeDate` = the closing date; this is the field the 90-day/6-month/12-month windows should be computed against, not `listDate` or `modified`.
- Across 13 closed listings with both fields present: mean (closePrice − listPrice) / listPrice = +81.0%; 0% have closePrice == listPrice exactly. Values vary and aren't placeholder-identical, so both fields are usable for a demo, but should be labeled clearly as synthetic in the briefing.

## 6. Address searchability

- full_address: `{"query": "74434 East Sweet Bottom Br #18393", "result_count": 1, "target_found": true}`
- street_name_only: `{"query": "East Sweet Bottom Br", "result_count": 1, "target_found": true}`

Direct `q=<full address>` and `q=<street name>` text search both resolved the target listing reliably in this probe. This supports the recommended UI: an address-search box scoped to the demo dataset is workable, backed by `q=`, in addition to a preset picker.

## 7. Pagination behavior

- `limit` was accepted up to 500+ without truncation error; the feed itself is small enough (78 total, 13 closed) that no result set ever hit a server-side page cap in this probe.
- `offset` is validated server-side: requesting `offset >= <matching count>` for a filtered query returns HTTP 400 `InvalidArguments: "offset too high"` (see `fixtures/probe_notes.json.pagination_probe`), not an empty array. Pagination loops must stop on this error (or precede it by tracking a running count), not assume an empty page signals the end.
- No `X-Total-Count`-style header was inspected in this pass; total counts are only knowable by requesting a limit larger than the true population and counting the returned array.

## 8. IDX / display / attribution fields

- `internetAddressDisplay`: non-null on 0/78 listings.
- `internetEntireListingDisplay`: non-null on 0/78 listings.
- `disclaimer` text present on 78/78 listings.

Both IDX display-permission flags are `null` throughout this trial dataset (they are not meaningfully populated on trial data). The canonical schema should still carry these two fields plus `disclaimer` through unmodified — defaulting missing/null display flags to the conservative (non-display) assumption — so the plumbing is correct even though the demo values are all null.

## 9. Recommended demonstration clock

- **Analysis date = latest closed-sale date in the dataset = `2013-09-27`.**
- This is ~13 years before the real current date — far too old to treat today's date as usable for the 90-day/6-month/12-month windows. Use the dataset-derived analysis date, not `datetime.now()`, for all recency filtering.
- Display prominently in the briefing: "Demonstration analysis as of 2013-09-27, using sample SimplyRETS records — not current market transactions."

## 10. Suggested demo subject properties ("Try an example")

- `1005250` — 73458 West HEYWARD Freeway #18393, Tomball, Texas — closed 2012-06-11 at $1,974,103
- `1005206` — 22530 East ASTRIDA DR #3 Knolls #1, The Woodlands, Texas — closed 2000-02-23 at $18,871,472
- `1005247` — 5806 East Perry Hill Falls #1021-B, Tomball, Texas — closed 1990-02-19 at $178,574
- `1005223` — 44715 East ARABIAN WAY Knolls #7610, The Woodlands, Texas — closed 2006-09-03 at $9,112,449
- `1005228` — 7450 West Northbridge Oval #S5, Tomball, Texas — closed 1991-02-19 at $7,616,551
- `1005249` — 86155 East TEE SIDE Link #1573, Tomball, Texas — closed 2013-09-27 at $1,505,249
- `1005202` — 9098 West Zuelke Knolls #8020, Oak Ridge, Texas — closed 2007-11-18 at $23,022,100
- `1005197` — 11729 North SW 368 ST& SW 214 AV Junction #104-7B, Houston, Texas — closed 1993-02-06 at $16,350,636

These are ranked by completeness of the fields the comparable engine needs (coordinates, living area, beds, baths, year built, lot size). Use them as the preset picker list; restrict any free-text address box to resolving against this same dataset.

## 11. Open items for Phase 2

- Confirm whether a bounding-box/polygon geo search (vs. plain `q=` text) is available on this trial tier — not yet probed here; needed for the radius-expansion search design.
- With only 8 closed-Residential sales total, radius/date expansion will need to reach 6–12 months and/or include non-Residential subtypes fairly often to hit the ≥3-comparable target — confirm this against the success criterion during Phase 2 design, not assumed here.
