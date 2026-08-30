# Phase 5 — Streamlit Briefing UI

Implements the plan's UI layer: a "try an example" subject picker (the
plan's own recommended demo UI, reinforced by Phase 2b's finding that
free-text address search is unreliable), real approve/decline buttons for
search expansion driving the actual LangGraph interrupt/resume mechanism
(not a simulation of it), and the one-page briefing with its self-check
results shown openly.

## Files

| File | Responsibility |
|---|---|
| [app.py](../app.py) | The Streamlit app (project root, so `streamlit run app.py` matches convention) |
| [src/demo_subjects.py](../src/demo_subjects.py) | The curated, live-validated "try an example" picker list |
| [tests/test_app.py](../tests/test_app.py) | Scripted UI tests via Streamlit's `AppTest` — no browser needed |

Run it: `.venv/bin/streamlit run app.py`

## Decisions worth recording

**The graph (and its checkpointer) is cached across Streamlit reruns via
`st.cache_resource`, not rebuilt per rerun.** Streamlit re-executes the
whole script on every interaction. `orchestrator.build_graph` compiles
with an `InMemorySaver` — if that were rebuilt every rerun, the checkpoint
for an in-progress `thread_id` would vanish before the user's approval
click could ever resume it. Caching is keyed by the data-source choice
(fixture vs. live), so switching sources gets its own graph/agent/
checkpointer pair rather than a mix.

**The UI drives `graph.invoke`/`Command(resume=...)` directly — it does
not use `orchestrator.run_interactive`.** That function's synchronous
callback loop exists for tests and CLI/notebook use; a real UI needs to
*return control to the browser* between the question and the answer (a
button click is a separate HTTP request, not a same-stack-frame
callback), so `app.py` calls `graph.invoke` once per button click and
stores whatever comes back (`__interrupt__` or a finished state) in
`st.session_state`, checking on the next rerun which one it got. This is
the same two-call pause/resume shape the design docs for Phase 4
anticipated, just driven by real browser events instead of a Python
callback answering hypothetically.

**Data source is a runtime toggle (fixture vs. live), not a build-time
choice.** Given the Repliers rate-limit history this project already hit
once (Phase 2b: quota dropped to 50/1800 during migration work), the
frozen fixture sample is the default — reliable, fast, and free to demo
repeatedly. Live is one click away and uses the exact same provider
interface and orchestrator graph, which is the actual point of Phase 2's
provider abstraction paying off a third time (after the SimplyRETS→
Repliers swap and the FakeProvider-based orchestrator tests).

**`provider_limit` differs by data source, carried over from Phase 4's
finding.** Fixture (500) vs. live (100) — see `docs/phase4-design-notes.md`
for why: the fixture provider doesn't filter by geography at all, so it
needs a much larger pool to have a chance of containing nearby records;
the live provider does real server-side radius filtering, so its default
pool is already the *right* small pool.

**Graph construction itself is wrapped in a try/except, not just
`graph.invoke`.** First pass only guarded the `invoke` calls; selecting
the live data source without `REPLIERS_API_KEY` set throws inside
`get_graph` (via `RepliersClient.__init__`), before any invoke happens —
caught while testing the live-source path, not left for a user to hit as
an unhandled traceback.

**The briefing is rendered via `st.markdown` on the exact text
`generate_briefing` produced and `check_briefing` verified** — no separate
UI-side re-formatting of the numbers. The self-check results are shown in
an open expander, not hidden or summarized away, since the whole point of
building `check_briefing` in Phase 4 was making the traceability claim
inspectable, not just assertable in a test.

## Verified

- **Scripted, no browser** (`tests/test_app.py`, via Streamlit's `AppTest`):
  app loads with no exception; the full approve-to-completion flow reaches
  a briefing with all self-checks passing; declining immediately still
  produces a coherent "insufficient" briefing; "Start over" actually clears
  session state; an unknown custom MLS number shows a clean error instead
  of a crash.
- **Real server** (`streamlit run app.py --server.headless true`): starts
  and serves HTTP 200 without needing any of the scripted-testing
  machinery — confirms `AppTest`'s results reflect the real app, not just
  the test harness's view of it.
# Demo UX update (2026-08-30)

Fixture mode is locked to the dataset-derived 2026-03-17 Demo analysis date;
only live mode defaults to the calendar date. The UI now includes workflow
progress, a subject summary, comparable inclusion/exclusion review, explicit
low-evidence confirmation, a confidence-bearing deterministic briefing,
Markdown download, collapsed diagnostics, and actionable live-provider
failure guidance.

The ten-case fixture regression contract lives in `src/demo_evaluation.py`
and is enforced by `tests/test_demo_evaluation.py`. The current frozen sample
contains no subjects with three qualified sales at 3 or 5 miles within 90
days of its latest sale date, so the evaluation honestly records the paths
the fixture can support rather than manufacturing the requested distribution.

## Optional OpenAI reporting agent

`src/reporting_agent.py` uses the OpenAI Responses API when
`OPENAI_API_KEY` is configured. It receives only a de-identified structured
fact packet derived from approved comparables and deterministic valuation.
Structured output is limited to qualitative commentary, and a post-condition
rejects output containing digits, currency symbols, or percentages. The
model output is appended to—not substituted for—the checked deterministic
briefing. Missing credentials, HTTP errors, malformed output, and constraint
violations all produce the same complete deterministic fallback.
