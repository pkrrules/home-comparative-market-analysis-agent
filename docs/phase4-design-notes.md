# Phase 4 — LangGraph Orchestration & Human-in-the-Loop (Agent 3)

Implements the plan's Agent 3: controls progressive search expansion,
pauses for human approval when older/weaker evidence is needed, maintains
graph state via a checkpointer, and generates + checks the briefing.

## Environment note: needs a venv

This sandbox has no system `pip` (confirmed in Phase 1). `python3 -m venv`
+ its bundled pip work fine, so Phase 4 lives in `.venv/` (gitignored, per
the project's own `.gitignore`). **From Phase 4 onward, run the test suite
with `.venv/bin/python -m unittest discover -s tests`**, not bare
`python3` — everything through Phase 3 still runs on system Python (LangGraph
is the only new dependency), but `test_orchestrator.py` needs it and fails
an isolated, clean import error otherwise (confirmed: 84/85 other tests
still pass under system Python; only that one module errors).

## Modules

| Module | Responsibility |
|---|---|
| [src/report.py](../src/report.py) | Agent 3's report half: deterministic briefing template + self-check. No LangGraph dependency — independently testable. |
| [src/orchestrator.py](../src/orchestrator.py) | Agent 3's LangGraph half: the `StateGraph`, its nodes/edges, and the interrupt/resume plumbing. |

## Decisions worth recording

**The briefing is templated text from computed facts, not LLM prose.**
The plan's success criterion asks for a "fully traceable" briefing;
generating it with an LLM call would trade that traceability for fluency
and add a real dependency (API key, cost, latency, non-determinism) this
project doesn't otherwise have. `generate_briefing` returns `(text,
facts)` — a `BriefingFacts` record of exactly the numbers/ids it
embedded — and `check_briefing` verifies the *rendered text* actually
contains them. That's a real check against template bugs (a value
silently dropped, the wrong variable interpolated), not a re-trust of the
same computation.

**Two real bugs, again caught by running the graph, not by reading
LangGraph's docs:**

1. **Checkpoint serialization silently corrupted state.** The graph state
   holds live `CanonicalProperty`/`ComparableSearchResult`/etc. objects
   (not dicts), so `InMemorySaver`'s msgpack serializer warned
   `"Deserializing unregistered type ... will be blocked in a future
   version"` on every run. Passing `allowed_msgpack_modules` as bare
   module-name tuples (`[("canonical_schema",), ...]`) *looked* like a fix
   — the constructor accepted it silently — but actually allowed nothing:
   the next run **blocked** deserialization outright, and a blocked value
   comes back as a plain `dict` instead of raising, which then broke
   downstream attribute access (`'dict' object has no attribute
   'selected'`) in a node several steps removed from the real cause. Fixed
   by generating the exact `(module, classname)` pairs LangGraph actually
   requires, via `inspect.getmembers`, from the real classes in
   `canonical_schema`/`comparable_engine`/`report` — verified silent and
   correct end-to-end afterward, across an interrupt/resume cycle.

2. **`fetch_and_evaluate`'s default `provider_limit=100` produces
   misleading results against `RepliersFixtureProvider`.** That fixture
   provider doesn't filter by geography at all (documented in Phase 2b —
   it hands back everything and lets the exact local distance check do
   the work), so a small limit just means "the first 100 fixture records
   in file order," most of which aren't near any given subject. A first
   run of the full graph against a real Charlotte subject found 0
   comparables even at the widest step (5mi/12mo) — not because they
   don't exist (Phase 3 found 10 of them at 5mi/6mo, with a larger
   limit), but because they were never in the candidate pool to begin
   with. `build_graph` now takes a `provider_limit` parameter (default
   100, correct for the live provider, which does real server-side radius
   filtering) so fixture-backed tests/demos can pass a larger value
   instead of silently getting an artificially sparse market.

**`request_approval` is the only interrupt point, by design.** One
`interrupt()` call sits between `run_step` and either looping back (more
steps to try) or moving on (declined, or steps exhausted) — this is the
entire human-in-the-loop mechanism the plan asks for, no more machinery
than that. `run_interactive`'s synchronous callback loop is a test/demo
convenience; Phase 5's real UI will call `graph.invoke` /
`Command(resume=...)` directly, rendering the interrupt's question and
waiting for an actual button click in between — the same two-call
pause/resume shape, just driven by a browser event instead of a Python
callback.

**Top-level `status` tracks graph completion, not the approval outcome.**
It's `"running"` → `"no_subject"` (terminal, nothing to analyze) or
`"done"` (terminal, briefing generated) — `generate_briefing`'s node
always sets it to `"done"` once it runs, even after a decline. The
decline itself is preserved faithfully in `expansion_log` (an
`ExpansionLogEntry(kind="approval", decision="declined")`), which is the
correct place to look for it — conflating "how the search ended" into the
same field as "is the graph still running" would have made the state
machine harder to reason about for no real benefit. (An earlier draft of
the test suite assumed `status` would end as `"declined"`; that was the
test's wrong assumption, not a code bug — fixed in the test.)

**Question wording is generated from real counts, not the plan's
illustrative numbers.** `build_expansion_question` produces text like the
plan's own example ("Only 2 qualified comparables were found within 3
miles and 90 days...") but substitutes whatever `evaluate_candidates`
actually found, and gets the "was"/"were" grammar right for the n=1 case
— a genuine small bug caught while writing the test for it, fixed rather
than left in.

## Verified end-to-end, including the pause itself

Ran the real graph (via `run_interactive`, callback-driven) against the
frozen Repliers fixtures, subject `CAR3006094`:

```
[interrupt] Fewer than 3 qualified comparables remain (2 found). May the analysis
            include sales up to six months before the demonstration analysis date?
-> sufficient at 5 miles, 6 months: 10 selected, all 23 self-checks PASS
```

Matches Phase 3's current standalone result (0 → 1 → 2 → 10), with
radius changes automatic and the temporal expansion paused for real approval.
Also verified: declining temporal expansion terminates with an honest "insufficient"
briefing; an unknown subject id short-circuits straight to a briefing that
says so; a subject with zero available candidates runs all six steps
(two temporal approval pauses) and still terminates with a coherent, checked
"no comparables found" briefing rather than looping forever.

## Test coverage

`.venv/bin/python -m unittest discover -s tests` — 91 tests: 13 new
(`test_report.py`, `test_orchestrator.py`, the latter using a small
`FakeProvider` test double rather than the real fixtures, so every
approve/decline/exhausted/unknown-subject branch is exercised
deterministically instead of depending on what a particular fixture
snapshot happens to contain), 78 retained from Phases 1–3.
