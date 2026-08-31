# Market Research Agent — Comparable Home Analysis (MVP)

A demo application that finds comparable closed home sales for a subject
property, using a real-estate data API, and produces a traceable one-page
briefing. See the project plan for full architecture and framing.

**Active provider: [Repliers](https://repliers.com)** (migrated from
SimplyRETS — see [docs/phase2b-repliers-migration.md](docs/phase2b-repliers-migration.md)
for why and what changed). Both are sample/sandbox data, not real
transactions — this MVP demonstrates the comparable-analysis workflow, it
does not estimate the value of arbitrary real homes.

## Demo Scope

This is a **LangGraph-based comparable-analysis application using frozen
Repliers sample data**. A user selects a known demonstration property or
enters an exact MLS number, reviews the workflow's search decisions,
approves the final comparable set, and receives a traceable value briefing.

- Exact MLS numbers and presets are supported; arbitrary address lookup is out of scope.
- Repliers is the only active provider and fixture mode is the default.
- The demo evaluates workflow correctness, not real-world market accuracy, and is not an appraisal.
- Single-family residential property is the primary target.
- Three approved comparables is the normal minimum and ten is the maximum; fewer than three requires explicit low-evidence confirmation.
- Fixture mode always uses the frozen dataset's latest valid close date (**2026-03-17**) as the **Demo analysis date**. Live mode alone defaults to today.
- Data and analysis agents are deterministic. An optional OpenAI API reporting agent adds qualitative commentary from verified facts only; it cannot alter comparable IDs, eligibility, confidence, or calculations, and automatically falls back to the deterministic report.

## Status

- [x] Phase 1 — SimplyRETS demo feed audit (archived; see migration doc)
- [x] Phase 1 (Repliers) — migration audit
- [x] Phase 2 — canonical schema, provider interface, validation/dedup
- [x] Phase 2b — migrated active provider from SimplyRETS to Repliers
- [x] Phase 3 — comparable analysis engine (Agent 2)
- [x] Phase 4 — LangGraph orchestration + human-in-the-loop (Agent 3)
- [x] Phase 5 — Streamlit briefing UI

## Setup

```bash
cp .env.example .env
# fill in REPLIERS_API_KEY with your own key from https://repliers.com
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # requests + langgraph + streamlit
```

## Run the demo

```bash
.venv/bin/streamlit run app.py
```

To enable AI-assisted commentary, set `OPENAI_API_KEY` in `.env`. The
reporting model defaults to `gpt-5.4-mini` and can be changed with
`OPENAI_REPORT_MODEL`. This uses the OpenAI Responses API; a ChatGPT
subscription is not used as application credentials. Without a valid key,
the complete deterministic briefing is generated normally.

Expected live-source failures are classified separately: missing key,
authentication, rate limit, timeout, network connection, incomplete subject
data, invalid MLS number, no comparable evidence, and checkpoint-resume
failure. Recoverable live failures provide retry and one-click fixture-mode
actions. See [docs/demo-evaluation.md](docs/demo-evaluation.md) for the
ten-case technical evaluation and completed human-review result.

The result screen places a deterministic evidence-confidence banner above
the briefing. All six preset subjects have frozen regression expectations
for search path, approval points, and selected comparable IDs.

Opens in your browser. Defaults to the frozen fixture data source (no API
quota used, reliable for repeated demos) with a curated "try an example"
subject picker and fixed 2026-03-17 analysis date — flip to live Repliers in the sidebar any time. See
[docs/phase5-design-notes.md](docs/phase5-design-notes.md).

For a repeatable recorded walkthrough, use
[docs/loom-demo-script.md](docs/loom-demo-script.md).

Repliers requires your own signup and API key (`REPLIERS-API-KEY` header).
SimplyRETS's public demo credentials (`simplyrets`/`simplyrets`) still work
for the archived reference path, no signup needed.

**This sandbox has no system `pip`** (see Phase 1 audit) — `python3 -m venv`
works and bundles its own pip, so **use `.venv/bin/python`** for anything
from Phase 4 onward (it needs LangGraph). Everything through Phase 3 also
runs fine on bare `system python3` if you'd rather skip the venv for those
parts — `requests` alone is already installed system-wide here.

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
.venv/bin/python -m unittest discover -s tests -v
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
.venv/bin/python -m unittest discover -s tests -v
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
analysis_date = date.today()  # live mode; fixture mode uses RepliersFixtureProvider().analysis_date

for step in SEARCH_EXPANSION_STEPS:
    result = fetch_and_evaluate(agent, subject, step, analysis_date)
    print(step.label, "->", len(result.selected), "selected, sufficient =", result.sufficient)
    if result.sufficient:
        break
```

See [docs/phase3-design-notes.md](docs/phase3-design-notes.md) for the
eligibility rules, the deterministic scoring formula and its weights, the
confidence model, and a fixture-backed Wonderwood run producing 0 → 1 → 2
→ 10 comparables. Agent 2 evaluates one search step at a time; the
orchestrator automatically expands radius and pauses before widening the
sale-date window.

## Phase 4: LangGraph orchestration & human-in-the-loop (Agent 3)

```bash
.venv/bin/python -m unittest discover -s tests -v   # needs langgraph, so use the venv
```

```python
import sys; sys.path.insert(0, "src")
from datetime import date
from data_agent import PropertyDataAgent
from repliers_provider import RepliersProvider
from repliers_mapping import map_repliers_listing
from orchestrator import build_graph, run_interactive

agent = PropertyDataAgent(RepliersProvider(), map_repliers_listing)
graph = build_graph(agent)

def approve(payload):
    print(payload["question"])
    return input("approve? [y/n] ").strip().lower() == "y"

final = run_interactive(graph, "thread-1", "CAR3006094", date.today(), approve)
print(final["briefing"])
```

`run_interactive` is a synchronous convenience for scripts/tests/notebooks.
The graph itself pauses via LangGraph's `interrupt()`/`Command(resume=...)`
— Phase 5's UI will call those directly (render the question, wait for a
real button click, then resume), the same mechanism `run_interactive`
only simulates with a callback. See
[docs/phase4-design-notes.md](docs/phase4-design-notes.md) for the graph
shape, two real bugs caught while wiring it up (checkpoint serialization
silently corrupting state; a fixture-provider/limit interaction that
produced a misleadingly "no comparables anywhere" result), and a verified
end-to-end run reproducing Phase 3's exact numbers through automatic radius
changes and a real temporal-approval interrupt.

## Phase 5: Streamlit briefing UI

```bash
.venv/bin/streamlit run app.py                       # the real app
.venv/bin/python -m unittest discover -s tests -v     # 110 tests, including Streamlit AppTest coverage
```

The UI drives `orchestrator.py`'s graph directly with real button clicks
(`graph.invoke` / `Command(resume=...)`, cached across Streamlit's rerun
model via `st.cache_resource` so an in-progress approval isn't lost
between clicks) — not the synchronous `run_interactive` helper, which
remains a test/notebook convenience. Defaults to the frozen fixture data
source; a sidebar toggle switches to live Repliers. See
[docs/phase5-design-notes.md](docs/phase5-design-notes.md) for why the
graph must be cached (not rebuilt) across reruns, and what got verified
both via scripted `AppTest` runs and a real `streamlit run` launch.

---

All five phases of the plan are now implemented: API tool use,
deterministic component delegation (data/validation, comparable analysis,
and orchestration/reporting), stateful LangGraph
orchestration, conditional search expansion, human-in-the-loop decisions,
deterministic comparable analysis, structured report generation, and a
Streamlit front end.

Current verification baseline: **110 tests passing** with no network calls
from the automated suite. The OpenAI reporting path is mocked in tests and
has also been validated separately against the live Responses API.
