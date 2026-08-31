# Phase 2 — Canonical Schema, Provider Interface, Validation & Dedup

> Historical phase record. The active implementation is Repliers-backed;
> provider migration details are in `phase2b-repliers-migration.md` and the
> current end-to-end behavior is summarized in the README.

Implements the `SimplyRETS -> Provider interface -> Canonical property
schema -> Validation and deduplication` slice of the architecture, i.e.
the data half of Agent 1 (Property and Data Agent).

## Modules

| Module | Responsibility |
|---|---|
| [src/canonical_schema.py](../src/canonical_schema.py) | `CanonicalProperty` and its sub-dataclasses; `FieldStatus`/`FieldFlag` |
| [src/provider.py](../src/provider.py) | `PropertyDataProvider` — the app-tailored interface |
| [src/simplyrets_provider.py](../src/simplyrets_provider.py) | Live implementation, wraps `SimplyRETSClient` |
| [src/simplyrets_fixture_provider.py](../src/simplyrets_fixture_provider.py) | Archived SimplyRETS frozen-fixture implementation |
| [src/simplyrets_mapping.py](../src/simplyrets_mapping.py) | Raw SimplyRETS dict -> `CanonicalProperty` (pure, no judgment calls) |
| [src/validation.py](../src/validation.py) | Per-field present/missing/implausible flagging |
| [src/dedup.py](../src/dedup.py) | Collapses duplicate records |
| [src/data_agent.py](../src/data_agent.py) | `PropertyDataAgent` — wires the above into `find_subject` / `load_closed_sales` |

Tests: [tests/](../tests/), runnable with `python3 -m unittest discover -s tests`
(no pytest available in this environment — plain `unittest` instead).

## Decisions worth recording

**Provider interface has no radius/geo params, by design, not oversight.**
Probed empirically before writing the interface: `cities=` and
`postalCodes=` filter server-side on the SimplyRETS trial tier (an unknown
city correctly returns zero results), but `radius=`/`lat=`/`lng=`/`polygon=`
are silently ignored — a 0.001-mile radius around `(0, 0)` still returned
every closed listing. So `PropertyDataProvider.search_closed_sales` only
exposes the filters that actually work; all distance/radius logic happens
client-side downstream (comparable engine, Phase 3), against canonical
records. This resolves the Phase 1 "open item" about geo search.

**Agent 1 drops a record only when a hard-required field is entirely
missing — never for an implausible one.** First cut of `data_agent.py`
treated `IMPLAUSIBLE` the same as `MISSING` for `close_price`, and running
it against the live feed silently dropped 4 of 13 closed sales (this trial
feed's list/close price ratios are essentially random, from 0.01x to
4.67x — synthetic data, not realistic price movement). That conflated two
different jobs: Agent 1's is to make problems *visible*; deciding whether
an implausible value disqualifies a comp (and explaining that exclusion)
belongs to Agent 2's eligibility rules per the project plan. Fixed so
`missing_hard_requirements()` only fires on `FieldStatus.MISSING`;
implausible fields stay flagged but the record stays in play.

**`property.type`/`property.subType` inconsistency and `status`/`sales`
inconsistency are both real, both caught.** Phase 1's audit found
`type=CND` paired with `subType=SingleFamilyResidence` in the raw feed;
`validation.py` flags that combination (`type_subtype_consistency`).
While building the mapping test fixtures, a second inconsistency turned up
that Phase 1 hadn't documented: `single_property_sample.json` (mlsId
1005192) has `status=Active` but a fully populated `sales.closeDate` /
`closePrice` block — a listing that is not closed but carries a closing.
Added `status_consistency` to catch this; it matters most for
`find_subject`, which (unlike `load_closed_sales`) can resolve a listing of
any status, so this scenario is reachable in normal use, not just theory.

**Lot size falls back to the text field, but that fallback is only a
note, not a value.** Phase 1 audit: `property.lotSizeArea` (numeric) is 0%
populated on closed sales in this feed, while `property.lotSize` (free
text, e.g. `"127X146"`) is 100% populated. The canonical schema carries
both; validation reports `lot_size` as `MISSING` (a calculation can't use
free text) but records in the flag's `reason` that a text description
exists, so the briefing can still show *something* to a human even when
the comparable engine can't compute with it.

**Dedup matches on address + close date + close price, not just address.**
A single provider makes exact-id duplicates unlikely (confirmed: 0 dedup
drops against the real feed) and address-only matching would be too broad
(two different homes can share a generic-looking address fragment). Address
+ close date + close price together is specific enough that a collision
is almost certainly the same real-world sale — including across a future
second provider, which is the actual reason this pass exists per the
project plan ("deduplicate by MLS ID, address, and transaction facts")
even though nothing in today's single-source data needs it yet.

## Verified against the live feed (not just fixtures)

```
kept: 13   dropped-for-hard-requirements: 0   dedup drops: 0
implausible field flags on kept records:
  close_price:                4 records (mlsId 1005226, 1005250, 1005247, 1005176)
  type_subtype_consistency:   2 records (mlsId 1005226, 1005162)
```

All 13 closed sales survive into Agent 2's input, each carrying whatever
flags apply — which is the point: Phase 2 hands Agent 2 a fully labeled,
deduplicated set, and stays out of the eligibility decision itself.
