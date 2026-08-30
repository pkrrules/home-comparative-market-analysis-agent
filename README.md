# Market Research Agent — Comparable Home Analysis (MVP)

A demo application that finds comparable closed home sales for a subject
property, using a real-estate data API, and produces a traceable one-page
briefing. See the project plan for full architecture and framing.

**Active provider: [Repliers](https://repliers.com)** (migrated from
SimplyRETS — see [docs/phase2b-repliers-migration.md](docs/phase2b-repliers-migration.md)
for why and what changed). Both are sample/sandbox data, not real
transactions — this MVP demonstrates the comparable-analysis workflow, it
does not estimate the value of arbitrary real homes.

## Status

- [x] Phase 1 — SimplyRETS demo feed audit (archived; see migration doc)
- [x] Phase 1 (Repliers) — migration audit
- [x] Phase 2 — canonical schema, provider interface, validation/dedup
- [x] Phase 2b — migrated active provider from SimplyRETS to Repliers
- [x] Phase 3 — comparable analysis engine (Agent 2)
- [ ] Phase 4 — LangGraph orchestration + human-in-the-loop
- [ ] Phase 5 — Streamlit briefing UI

## Setup

```bash
cp .env.example .env
# fill in REPLIERS_API_KEY with your own key from https://repliers.com
python3 -m venv .venv && source .venv/bin/activate  # if pip is available
pip install -r requirements.txt                      # only dependency: requests
```

Repliers requires your own signup and API key (`REPLIERS-API-KEY` header).
SimplyRETS's public demo credentials (`simplyrets`/`simplyrets`) still work
for the archived reference path, no signup needed.

**Rate limit:** a personal Repliers key is capped around 1800 requests per
rolling window (`X-RateLimit-*` response headers). `RepliersProvider`
fans one call out into several HTTP requests when paginating past 100
results — be mindful of `limit` when experimenting live; prefer the
frozen fixtures / `RepliersFixtureProvider` for anything repetitive.

## Phase 1 (Repliers): migration audit

```bash
python3 scripts/fetch_repliers_fixtures.py   # hits the live API, freezes fixtures/repliers_*.json
python3 scripts/audit_repliers.py            # reads fixtures/, writes docs/phase1-repliers-audit.md
```

See [docs/phase1-repliers-audit.md](docs/phase1-repliers-audit.md) for
findings (feed size, geography, closed-sale population, field
completeness, price semantics, address searchability, radius search,
pagination, IDX/attribution fields, the demonstration clock
recommendation, and a live-validated "try an example" picker) and
[docs/phase2b-repliers-migration.md](docs/phase2b-repliers-migration.md)
for the migration decision and two real bugs caught while building it
(a wrong pagination parameter name, and unreliable address search).

The original SimplyRETS audit is preserved at
[docs/phase1-api-audit.md](docs/phase1-api-audit.md) (archived, no longer
the active provider — `src/simplyrets_*.py` still work standalone if
you want to run it).

## Phase 2: canonical schema, provider interface, validation & dedup

```bash
python3 -m unittest discover -s tests -v   # 52 tests, all against fixtures — no network
```

```python
import sys; sys.path.insert(0, "src")
from data_agent import PropertyDataAgent
from repliers_provider import RepliersProvider          # or repliers_fixture_provider.RepliersFixtureProvider for offline
from repliers_mapping import map_repliers_listing

agent = PropertyDataAgent(RepliersProvider(), map_repliers_listing)
subject = agent.find_subject("CAR3006094")                          # by MLS number — see migration doc §2 for why not free-text
result = agent.load_closed_sales(cities=["Charlotte"], property_type="Residential", limit=100)
print(len(result.properties), result.dropped_hard_requirements, result.dedup_drops)
```

See [docs/phase2-design-notes.md](docs/phase2-design-notes.md) for the
original module layout and design decisions (provider interface scope,
the missing-vs-implausible split between Agent 1 and Agent 2, dedup's
matching key) — all still accurate for the current Repliers-backed code,
since the canonical schema, dedup, and eligibility-relevant validation
logic are provider-agnostic and didn't need to change in the migration.

## Phase 3: comparable analysis engine (Agent 2)

```bash
python3 -m unittest discover -s tests -v   # 78 tests, all deterministic/fixture-based — no network
```

```python
import sys; sys.path.insert(0, "src")
from datetime import date
from data_agent import PropertyDataAgent
from repliers_provider import RepliersProvider
from repliers_mapping import map_repliers_listing
from comparable_engine import fetch_and_evaluate, SEARCH_EXPANSION_STEPS

agent = PropertyDataAgent(RepliersProvider(), map_repliers_listing)
subject = agent.find_subject("CAR3006094")
analysis_date = date.today()  # or a dataset-derived date — see phase1-repliers-audit.md §9

for step in SEARCH_EXPANSION_STEPS:
    result = fetch_and_evaluate(agent, subject, step, analysis_date)
    print(step.label, "->", len(result.selected), "selected, sufficient =", result.sufficient)
    if result.sufficient:
        break
```

See [docs/phase3-design-notes.md](docs/phase3-design-notes.md) for the
eligibility rules, the deterministic scoring formula and its weights, the
confidence model, and a real run against frozen data reproducing the
project plan's own human-in-the-loop example (0 comps at 3mi/90d → 2 at
5mi/90d → 10 at 5mi/6mo). Agent 2 evaluates one search step at a time and
does not decide on its own to expand — that pause-for-approval loop is
Phase 4's job.
