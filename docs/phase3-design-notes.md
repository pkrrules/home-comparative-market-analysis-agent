# Phase 3 — Comparable Analysis Agent (Agent 2)

Implements the plan's Agent 2: applies eligibility rules, runs
deterministic calculations, ranks candidates, selects the top 3–10, and
explains similarities/differences/exclusions/confidence. Pure and
provider-agnostic — everything operates on `CanonicalProperty` records
already produced by Agent 1.

## Modules

| Module | Responsibility |
|---|---|
| [src/distance.py](../src/distance.py) | Haversine great-circle distance, miles ↔ km |
| [src/comparable_engine.py](../src/comparable_engine.py) | Eligibility, scoring, ranking, selection, explanation |

Tests: `tests/test_distance.py`, `tests/test_comparable_engine.py` — 26
tests, all synthetic/deterministic (no fixtures needed for correctness,
though a live sanity check against real frozen data is below).

## Decisions worth recording

**Agent 2 evaluates one search step; it does not loop through
`SEARCH_EXPANSION_STEPS` itself.** The four steps —
`(3mi,90d) → (5mi,90d) → (5mi,6mo) → (5mi,12mo)` — are defined as public
constants matching the project plan's own human-in-the-loop dialogue
verbatim, but *deciding* to move to the next step is Agent 3 /
LangGraph's job (Phase 4), because that decision needs to pause for human
approval between steps. `evaluate_candidates` (and `fetch_and_evaluate`)
does exactly one step and returns whether it was `sufficient` (≥3
selected); nothing in this module auto-advances.

**Implausible core-valuation fields are excluded outright, not
downweighted.** A candidate whose `close_price` or `living_area_sqft` is
flagged `IMPLAUSIBLE` (Agent 1) is dropped at the eligibility stage, not
merely marked low-confidence — a sale price failing a sanity check can't
be trusted enough to feed `$/sqft` or the similarity score at all, which
is a stronger statement than "include with a caveat." Consequence:
`_confidence()`'s "low" tier is defined and directly unit-tested, but
never actually produced by `evaluate_candidates` in practice, since those
candidates are excluded before scoring runs. Documented in
`comparable_engine.py` rather than removed, since it's still the correct
place to express what "low" would mean if eligibility rules ever changed.
Everything else Agent 1 flags (missing/implausible bedrooms, baths, lot
size, year built, type/subtype or status consistency) surfaces as
`medium` confidence instead of exclusion — those don't corrupt the core
price/size math the way a bad price or area would.

**Property-type eligibility checks the broad type only, not subtype.**
Comparing a house to a condo (subtype) is a similarity/confidence
question; comparing a house sale to a *land* sale (type) is a category
error — no valid distance-price relationship exists between them.

**Scoring is a documented, fixed-weight composite, not a learned model** —
consistent with the plan's "deterministic calculations" requirement:

```
score = 0.30·distance_score + 0.20·recency_score + 0.30·size_score
       + 0.10·bed_score      + 0.10·bath_score
```

Each component is normalized to `[0, 1]` (1.0 = perfect match) before
weighting; a missing field on either side of the comparison scores 0.5
(neutral) rather than 0 or excluding the candidate — a single missing
secondary field shouldn't zero out an otherwise-good comp. Weights favor
distance and size roughly equally over recency, with beds/baths as minor
tie-breakers; these are stated design choices, not derived from data, and
easy to retune in one place if Phase 5's briefing reveals they rank
oddly in practice.

**`fetch_and_evaluate` requests a 25% larger radius from the provider than
the step actually calls for.** Per the plan's "Search behavior" split —
provider does coarse filtering (status/type/geo), the app does exact
circular distance — this margin absorbs any difference between Repliers'
own radius/great-circle implementation and this project's haversine
formula, so a comp just inside the true radius doesn't get silently
dropped by the provider before the app ever sees it to judge for itself.
The app still enforces the exact cutoff locally regardless.

## Verified against real (frozen) data, not just synthetic tests

Ran the actual expansion sequence against the Repliers migration audit's
Charlotte fixture sample, subject `CAR3006094` (447 Wonderwood Drive):

```
3 miles, 90 days   -> 0 selected  (insufficient)
5 miles, 90 days   -> 2 selected  (insufficient)
5 miles, 6 months  -> 10 selected (sufficient)
```

This is the exact shape of the project plan's own human-in-the-loop
example ("Only two qualified comparables were found within three miles
and 90 days... may the search expand to five miles?"), produced from real
data rather than asserted in the abstract — a genuine, not contrived,
demonstration of why progressive expansion is needed on this dataset.
