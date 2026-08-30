# Market Research Agent — Comparable Home Analysis (MVP)

A demo application that finds comparable closed home sales for a subject
property, using the SimplyRETS demo real-estate API, and produces a
traceable one-page briefing. See the project plan for full architecture
and framing; this repo currently covers **Phase 1: API audit**.

## Status

- [x] Phase 1 — SimplyRETS demo feed audit
- [x] Phase 2 — canonical schema, provider interface, validation/dedup
- [ ] Phase 3 — comparable analysis engine
- [ ] Phase 4 — LangGraph orchestration + human-in-the-loop
- [ ] Phase 5 — Streamlit briefing UI

## Setup

```bash
cp .env.example .env   # public SimplyRETS demo credentials, already filled in
python3 -m venv .venv && source .venv/bin/activate  # if pip is available
pip install -r requirements.txt                      # only dependency: requests
```

No API key signup is required — SimplyRETS publishes open demo credentials
(`simplyrets` / `simplyrets`) for `https://api.simplyrets.com`.

## Phase 1: API audit

```bash
python3 scripts/fetch_fixtures.py   # hits the live demo API, freezes fixtures/
python3 scripts/audit_phase1.py     # reads fixtures/, writes docs/phase1-api-audit.md
```

- `src/simplyrets_client.py` — thin, tailored SimplyRETS client (Basic auth,
  retries, the handful of endpoints this project needs). Not a generic SDK.
- `fixtures/` — frozen raw API responses (metadata, all 78 listings across
  every status, one single-property detail call, and raw probe results).
  These are the basis for later test fixtures too.
- `docs/phase1-api-audit.md` — the audit findings: feed size, geography,
  closed-sale population, field completeness, price-field semantics,
  address searchability, pagination behavior, IDX/attribution fields,
  the recommended demonstration analysis date, and a preset "try an
  example" subject-property shortlist.

Key findings (see the report for detail): the trial feed has only 13
closed sales total (8 of them `type=RES`) spanning 1990–2013, so the
demonstration analysis date is fixed at the dataset's latest close date
(**2013-09-27**), not `datetime.now()`. `property.type`/`property.subType`
are not internally consistent in this synthetic data — Phase 2's
plausibility checks need to account for that.

## Phase 2: canonical schema, provider interface, validation & dedup

```bash
python3 -m unittest discover -s tests -v   # 34 tests, all against fixtures — no network
```

```python
import sys; sys.path.insert(0, "src")
from data_agent import PropertyDataAgent
from simplyrets_provider import SimplyRETSProvider   # or fixture_provider.FixtureProvider for offline

agent = PropertyDataAgent(SimplyRETSProvider())
subject = agent.find_subject("1005192")              # by mlsId or address text
result = agent.load_closed_sales()                    # -> ClosedSalesResult
print(len(result.properties), result.dropped_hard_requirements, result.dedup_drops)
```

See [docs/phase2-design-notes.md](docs/phase2-design-notes.md) for the
module layout and the design decisions that came out of building this
against the real feed (provider interface scope, the missing-vs-implausible
split between Agent 1 and Agent 2, the two data-inconsistency checks the
validator catches, dedup's matching key).
