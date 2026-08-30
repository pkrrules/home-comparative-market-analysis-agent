# Phase 2b — Migrating the Active Provider from SimplyRETS to Repliers

Full replacement, not a second provider: SimplyRETS's trial feed was too
small (13 closed sales, one state, 1990–2013) and its radius search was
confirmed non-functional (Phase 1 audit). The user signed up for a
personal Repliers API key; this doc records what changed and why.

**Framing carries over unchanged:** Repliers' listings are sample/sandbox
data too (every sampled record's description literally contains
`**** SAMPLE DATA ****`). This is a better *demo substrate* — bigger,
broader, more realistic dates and prices — not a source of real market
accuracy. See [phase1-repliers-audit.md](phase1-repliers-audit.md) §0.

## What changed

| | Before (SimplyRETS) | After (Repliers) |
|---|---|---|
| Active client/provider/mapping | `simplyrets_client.py` / `simplyrets_provider.py` / `simplyrets_mapping.py` — **kept, reference only** | `repliers_client.py` / `repliers_provider.py` / `repliers_mapping.py` |
| Active fixture provider | `simplyrets_fixture_provider.py` | `repliers_fixture_provider.py` |
| `PropertyDataAgent` construction | `PropertyDataAgent(provider)` — mapper hardcoded to SimplyRETS | `PropertyDataAgent(provider, map_listing)` — mapper injected (see §4) |
| `PropertyDataProvider.search_closed_sales` | `cities`, `postal_codes`, `limit` only | adds `lat`, `lng`, `radius_km`, `property_type` — real capabilities, not aspirational (§2) |
| `validation.py` | unchanged in structure; `_CONSISTENT_SUBTYPES_BY_TYPE` gained Repliers' vocabulary alongside SimplyRETS' (disjoint keys, no collision) |
| Demonstration clock | fixed at dataset's latest close date (2013-09-27) | may use real `datetime.now()` — data is recent enough (§3) |

Nothing in `canonical_schema.py`, `dedup.py`, or the eligibility-relevant
parts of `validation.py` needed to change — that's the payoff of Phase 2's
original separation of concerns.

## 1. Why full replacement, not a second provider

Asked the user directly (this was a real fork, not a default to assume):
replace entirely, conditioned on Repliers having live data. It doesn't
(§0) — but the user chose to proceed anyway, since it's still a strictly
better demo substrate than SimplyRETS on every axis that matters here:
volume (19,292 vs 8 closed-residential sales), geography (10+ states vs
1), working radius search (vs none), and realistic price ratios (vs
random 0.01x–4.67x). Full detail: [phase1-repliers-audit.md](phase1-repliers-audit.md).

## 2. Two real bugs caught by testing against the live API, not just docs

**Pagination: `page` is not the parameter — `pageNum` is.** Built
`RepliersProvider.search_closed_sales` to paginate past Repliers' 100/page
cap using `page=`, matching what seemed like the obvious param name. It
compiled, ran, and silently returned page 1 over and over — confirmed by
diffing listing ids across "pages" (100% overlap) and, more damningly, by
the response envelope's own `unrecognizedParams: ["query.page"]`. A live
end-to-end check (`load_closed_sales(cities=["Charlotte"], limit=250)`)
then showed the actual downstream damage: 250 requested, 100 kept, **150
flagged as dedup drops** — because the "3 pages" were 3 identical copies
of page 1, correctly recognized as duplicates by `dedup.py`, which was
completely innocent of the bug. Fixed to `pageNum=`; the same request now
returns 250 unique records with zero dedup drops. Same shape of bug as
SimplyRETS' ignored `radius` param, worth naming as a pattern: **provider
APIs that accept-and-ignore unknown params instead of rejecting them will
hide integration bugs behind plausible-looking code.** Always check the
response envelope for an unrecognized-params signal if the provider
offers one, and verify a "next page" actually differs before trusting it.

**Address/subject search is unreliable enough to change the interface
contract.** Probed several approaches against a known record: `streetName`
alone found nothing; `streetNumber` combined with `city` or `zip` found
nothing (`streetNumber` alone did work); a free-text `address=` param is
silently unrecognized (`unrecognizedParams: ["query.address"]`); `mlsNumber`
as a *search* filter (as opposed to the dedicated detail endpoint) returns
zero results. On top of that, **some MLS numbers that appear in search
results 404 on `GET /listings/{mlsNumber}`** with no pattern by board or
display permissions (2/20 in one probe). Given this, `find_subject`
resolves by MLS number via the detail endpoint only, and the "try an
example" picker (§10 of the audit) is built by live-validating each
candidate with an actual `get_listing` call at audit time, not by trusting
search-result presence. This isn't a regression from SimplyRETS — the
original project plan already recommended a curated picker over open
address search as the primary demo UI.

## 3. Demonstration clock: may now use real `datetime.now()`

Sampled `soldDate` values range from 2024-03 to 2026-03 — within roughly
six months of the real current date, unlike SimplyRETS' 13-year-stale
feed. Per the original plan's own fallback clause ("if the demo dataset
contains suitable dates relative to the real current date, the system may
use today instead — determined by audit, not assumed"), Phase 3 may
compute the 90-day/6-month/12-month windows against the real current date.
The "this is sample data" disclosure (§0) still needs to be prominent in
the briefing regardless — a current-looking date must not be read as
"live."

## 4. `PropertyDataAgent` now takes an injected mapping function

`data_agent.py` previously imported `map_simplyrets_listing` directly —
harmless with one provider, wrong the moment a second mapping function
existed. Changed the constructor to `PropertyDataAgent(provider,
map_listing)`, so the agent stays provider-agnostic (no branching on which
provider it was given) and the two lines that changed to complete the
migration were the construction call sites, not this class:

```python
# before
agent = PropertyDataAgent(SimplyRETSProvider())
# after
agent = PropertyDataAgent(RepliersProvider(), map_repliers_listing)
```

## 5. Data-quality findings specific to Repliers' sample data

- **`soldDate` earlier than `listDate` in 297/300 sampled records** —
  essentially universal, not a rare glitch worth a per-record implausible
  flag (that would flag ~99% of records, which is noise, not signal).
  Documented as a dataset caveat instead: don't trust `listDate` /
  `daysOnMarket` for anything; `soldDate`/`soldPrice` are reliable.
- **List/sold price ratios are realistic** (0.75x–1.06x, median ~1.0 in
  sample) — unlike SimplyRETS' random synthetic pricing, so the existing
  `validation.py` price-ratio rule needed no adjustment.
- **IDX display permissions are real, not always-null** —
  `permissions.displayAddressOnInternet`/`displayInternetEntireListing`
  are populated Y/N on every sampled record, so `Attribution` now carries
  meaningful values for the first time in this project.
- **`class`/`propertyType` are internally consistent** in the sampled
  Residential-filtered data (no equivalent to SimplyRETS' CND +
  SingleFamilyResidence mismatch turned up), but `validation.py`'s
  `type_subtype_consistency` check still guards the theoretically-possible
  Land + CondoProperty combination for whenever non-Residential records
  are pulled in.

## 6. Operational note: rate limits

This key's quota is **1800 requests per rolling window** (`X-RateLimit-Limit`
/ `X-RateLimit-Remaining` headers), reset at a specific timestamp
(`X-RateLimit-Reset`, epoch ms). `RepliersProvider.search_closed_sales`
fans a single call out into multiple HTTP requests when paginating past
100 results — a `limit=500` call can cost up to 5 requests. Building and
re-running this migration's fixture fetch + live verification consumed
most of a 1800-request window in one session; be mindful of `limit` and
of how often fixtures need refreshing versus just re-running tests against
the frozen sample.

## Test coverage

`python3 -m unittest discover -s tests` — 52 tests, all against frozen
fixtures (no network): 18 new/updated for Repliers (mapping, data agent,
validation's Repliers-vocabulary type/subtype cases), 34 retained
unchanged for the archived SimplyRETS path. A live end-to-end check
(not part of the automated suite, to avoid burning quota on every test
run) confirmed subject lookup, multi-page fetch, and radius search all
work correctly post-fix against the real API.
