# Phase 1 (Repliers) — Migration Audit

Generated: 2026-08-30 (UTC), from fixtures in `fixtures/repliers_*.json`.
Source: Repliers API (`https://api.repliers.io`), a personal signed-up API key returning **sample/sandbox data** — see §0.

## 0. This is sample data, not live transactions

Every one of 300 closed-sale listings sampled (`298/300`) carries a literal `**** SAMPLE DATA ****` marker in its description. Dates, prices, and geography look current and plausible, but this is Repliers' developer sandbox feed, not real MLS transactions. Getting real live data would require a production plan with the underlying MLS board agreements Repliers' docs mention. This audit — and the decision to migrate — treats Repliers as a **better demo substrate**, not a source of real market accuracy, preserving the same honesty framing the original plan set for SimplyRETS.

## 1. Feed size and scope

- `all`: 42886 total (~429 pages at 100/page)
- `standardStatus=Closed`: 25388 total (~254 pages at 100/page)
- `standardStatus=Closed,type=sale`: 22975 total (~230 pages at 100/page)
- `standardStatus=Closed,type=lease`: 2413 total (~25 pages at 100/page)
- `standardStatus=Closed,type=sale,propertyType=Residential`: 19292 total (~193 pages at 100/page)
- `status=U`: 26817 total (~269 pages at 100/page)

Sample analyzed here: 500 records (300 broad multi-state + 200 from the demo anchor city, 'Charlotte') out of 19292 closed-residential-sale listings available in total. Unlike the SimplyRETS audit (which froze the entire 78-listing feed), this is a sample, not the full population — the population is far too large to freeze wholesale.

## 2. Geography

- States in sample (10 distinct): {'NC': 244, 'WA': 157, 'CO': 34, 'MO': 15, 'TN': 12, 'FL': 11, 'SC': 8, 'KS': 8, 'TX': 8, 'IL': 3}
- Cities in sample (174 distinct, top 15): {'Charlotte': 214, 'Seattle': 16, 'Tacoma': 11, 'Bothell': 6, 'Monroe': 5, 'Bellevue': 5, 'Port Orchard': 4, 'Kansas City': 4, 'Bellingham': 4, 'Puyallup': 4, 'Gig Harbor': 4, 'Arvada': 4, 'Everett': 4, 'Lincolnton': 4, 'Olympia': 4}

Coverage is real multi-state (confirmed beyond the sample too: the broad sample alone touched 10 states in an earlier 100-record probe), a substantial upgrade over SimplyRETS' single-state, 6-city trial feed. Coverage is uneven — `boardId=110` (Washington state) dominates — so radius-search demos should anchor on a market with real depth, not assume any address works equally well.

## 3. Closed sales (the population comparable analysis draws from)

- `standardStatus=Closed & type=sale & propertyType=Residential`: **19292** total.
- Close dates in sample range: **2024-03-10** to **2026-03-17**.
- This is close enough to the real current date that the demonstration clock can plausibly use `datetime.now()` directly instead of a fixed historical analysis date — a first for this project (SimplyRETS' latest close date was 13 years stale). See §9.

### 3b. Data-quality findings (this sample dataset)

- **`soldDate` earlier than `listDate`**: 289/300 checked records — essentially universal in this sample, not a rare glitch. Unlike SimplyRETS' `type`/`subType` mismatch (a real minority-case flag), this is systemic enough that per-record flagging would be noise, not signal. Treated as a documented dataset caveat instead: **do not use `listDate`/`daysOnMarket` for eligibility or trust — only `soldDate`/`soldPrice` are reliable for comparable analysis.**
- **`class`/`details.propertyType` cross-tab** (Residential-filtered sample): {'ResidentialProperty|Residential': 170, 'CondoProperty|Residential': 130} — internally consistent in this sample (unlike SimplyRETS' CND+SingleFamilyResidence case); `validation.py`'s `type_subtype_consistency` check still guards the theoretically-possible Land+CondoProperty combination generically.
- **List/sold price ratio**: n=300, min=0.48, median=1.00, max=1.14, 0 outside the [0.3, 3.0] plausibility band. **Realistic** — a genuine improvement over SimplyRETS' random 0.01x–4.67x synthetic pricing; the existing price-ratio validation rule needed no adjustment.

## 4. Field completeness (measured over the 500-record sample, via the actual mapping+validation pipeline)

- geo.lat: 100%
- geo.lng: 100%
- living_area_sqft: 98%
- bedrooms: 98%
- baths_full: 98%
- lot_size: 53%
- year_built: 98%
- list_price: 100%
- close_price: 100%
- close_date: 100%

Implausible-field flag counts across the sample: {'type_subtype_consistency': 1}

## 5. Address / subject searchability

- `streetNumber_only`: `{"count": 4, "unrecognizedParams": []}`
- `streetName_only`: `{"count": 0, "unrecognizedParams": []}`
- `address_free_text`: `{"count": 42886, "unrecognizedParams": ["query.address"]}`
- `mlsNumber_as_search_param`: `{"count": 0, "unrecognizedParams": []}`

**Free-text and compound address search are unreliable here** — `streetName` alone found nothing for a known record, `address=` is silently unrecognized (confirmed via the response's `unrecognizedParams`), and `mlsNumber` as a *search* filter param returns nothing (the dedicated `GET /listings/{mlsNumber}` detail endpoint is the reliable way to resolve one, and even that 404s occasionally for no clear reason — see `single_listing_detail_failures` in the probe notes: [{'mlsNumber': 'CAR3666470', 'status': 404}]). **Decision:** `find_subject` resolves by MLS number only; the demo UI should use a curated, live-validated picker (§10), exactly the UI shape the original project plan already recommended.

## 6. Radius / geo search — genuinely works

- Center: {'lat': 35.053492, 'lng': -80.828155}
- Counts by radius: {'tiny_0.01km': 1, '5km': 143, '50km': 3080}

Unlike SimplyRETS (which silently ignored radius/lat/lng/polygon params), Repliers' radius search demonstrably filters: a 0.01km radius returns 1 listing, 5km returns dozens, 50km returns thousands, around the same center point. This resolves the open item from the original SimplyRETS audit — the comparable engine can now use real server-side radius prefiltering, though it should still compute and enforce exact great-circle distance client-side for the final cutoff (see provider.py).

## 7. Pagination behavior

- `resultsPerPage` is capped server-side at **100** regardless of what's requested (confirmed: requesting 500/1000/5000 all silently returned 100). Fetching more than 100 requires paging with `page=`, which `RepliersProvider.search_closed_sales` does automatically up to a configured cap.
- The response envelope reports `count` and `numPages` directly — no need to probe blindly for a total, unlike SimplyRETS.

## 8. IDX / display / attribution fields

- `permissions.displayAddressOnInternet` non-null: 500/500
- `permissions.displayInternetEntireListing` non-null: 500/500

Unlike SimplyRETS (where these flags were null on every trial record), Repliers' sample data actually populates real Y/N values here — the canonical schema's `Attribution` fields now carry meaningful data, not just plumbing for a hypothetically-real feed.

## 9. Recommended demonstration clock

- Latest `soldDate` in this sample: **2026-03-17** (~166 days before real-today).
- Because this is close to the real current date (unlike SimplyRETS' 13-year-stale feed), the app may use **today's real date** as the analysis date, computing 90-day/6-month/12-month windows against `datetime.now()` directly — while still disclosing prominently that the underlying records are Repliers sample data, not real transactions (see §0). This satisfies the original plan's own fallback clause: *'If the demo dataset contains suitable dates relative to the real current date, the system may use today instead — determined by audit, not assumed.'*

## 10. Suggested demo subject properties ("Try an example") — live-validated

- `CAR3638662` — 8107 Hudson Forest Drive Unit 45, Charlotte, NC — closed 2025-08-19 at $244,640
- `CAR3006094` — 447 Wonderwood Drive, Charlotte, NC — closed 2024-05-18 at $756,500
- `CAR3638442` — 15131 Cimarron Hills Lane Unit PME146, Charlotte, NC — closed 2025-07-29 at $533,699
- `CAR4177999` — 3619 Maple Glenn Lane, Charlotte, NC — closed 2024-09-21 at $299,900
- `CAR4197739` — 1417 Collier Walk Alley Unit CSW0207, Charlotte, NC — closed 2025-07-13 at $569,950
- `CAR4214421` — 9500 Big Cone Place, Charlotte, NC — closed 2025-07-06 at $275,000

Each of these was confirmed live via `GET /listings/{mlsNumber}` at audit time (not just present in a search result), given §5's finding that search-result presence doesn't guarantee the detail endpoint resolves. Anchored on Charlotte, NC for real radius-search depth (hundreds of nearby closed sales, per §6).
