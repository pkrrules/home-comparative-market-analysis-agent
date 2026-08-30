"""
Phase 5: Streamlit briefing UI.

Drives orchestrator.py's LangGraph directly — the same interrupt/resume
mechanism run_interactive() simulates synchronously for tests, here driven
by real button clicks across Streamlit reruns. See docs/phase5-design-notes.md
for why the graph (and its checkpointer) must be cached across reruns, not
rebuilt each time, and the other Streamlit-specific gotchas found while
building this.

Run with:  .venv/bin/streamlit run app.py
"""
from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from comparable_engine import SEARCH_EXPANSION_STEPS  # noqa: E402
from data_agent import PropertyDataAgent  # noqa: E402
from demo_subjects import DEMO_SUBJECTS  # noqa: E402
from langgraph.types import Command  # noqa: E402
from orchestrator import build_graph, initial_state  # noqa: E402
from repliers_fixture_provider import RepliersFixtureProvider  # noqa: E402
from repliers_mapping import map_repliers_listing  # noqa: E402
from repliers_provider import RepliersProvider  # noqa: E402
from repliers_client import RepliersError  # noqa: E402
from reporting_agent import OpenAIReportingAgent  # noqa: E402

st.set_page_config(page_title="Comparable Home Analysis (Demo)", layout="wide")

FIXTURE_LABEL = "Frozen fixture sample (recommended — no API quota used)"
LIVE_LABEL = "Live Repliers API (uses your personal quota)"
FIXTURE_ANALYSIS_DATE = RepliersFixtureProvider().analysis_date


@st.cache_resource(show_spinner=False)
def get_graph(data_source: str):
    """Cached for the life of the server process, not just one rerun —
    the checkpointer inside the compiled graph must survive across
    Streamlit reruns for Command(resume=...) to find the paused state it's
    resuming. Rebuilding the graph (and its InMemorySaver) on every rerun
    would silently lose every in-progress thread. Keyed by data_source so
    switching sources gets its own graph/agent/checkpointer, not a mix.
    """
    if data_source == FIXTURE_LABEL:
        agent = PropertyDataAgent(RepliersFixtureProvider(), map_repliers_listing)
        provider_limit = 500  # fixture provider doesn't filter by geo — see Phase 4 notes
    else:
        agent = PropertyDataAgent(RepliersProvider(), map_repliers_listing)
        provider_limit = 100  # live provider does real server-side radius filtering
    return build_graph(
        agent,
        provider_limit=provider_limit,
        reporting_agent=OpenAIReportingAgent(),
    )


def reset_run() -> None:
    st.session_state.thread_id = None
    st.session_state.stage = "idle"
    st.session_state.pending_interrupt = None
    st.session_state.final_state = None
    st.session_state.error = None
    st.session_state.working_state = None


if "stage" not in st.session_state:
    reset_run()

st.title("Comparable Home Analysis — Demonstration")
st.caption(
    "This MVP demonstrates the comparable-analysis workflow using sample Repliers records. "
    "It does not estimate the present value of an arbitrary real home."
)

with st.sidebar:
    st.header("Setup")
    data_source = st.radio("Data source", [FIXTURE_LABEL, LIVE_LABEL], key="data_source", on_change=reset_run)

    subject_labels = [d.label for d in DEMO_SUBJECTS] + ["Custom MLS number…"]
    subject_choice = st.selectbox("Subject property", subject_labels, on_change=reset_run)
    if subject_choice == "Custom MLS number…":
        subject_id = st.text_input(
            "MLS number",
            help="Free-text address search is unreliable on this API (see docs/phase2b-repliers-migration.md) "
                 "— enter an exact MLS number.",
        )
    else:
        subject_id = next(d.mls_number for d in DEMO_SUBJECTS if d.label == subject_choice)

    if data_source == FIXTURE_LABEL:
        analysis_date = FIXTURE_ANALYSIS_DATE
        st.info(f"Demo analysis date: **{analysis_date.isoformat()}** (fixed from the frozen dataset)")
    else:
        analysis_date = st.date_input("Analysis date", value=date.today(), help="Live mode defaults to today.")

    st.divider()
    st.caption("Search sequence: radius expansions are automatic; older-sale windows require approval:")
    for step in SEARCH_EXPANSION_STEPS:
        st.caption(f"• {step.label}")

    st.divider()
    if st.button("Start over", width="stretch"):
        reset_run()
        st.rerun()

try:
    graph = get_graph(data_source)
except Exception as e:  # noqa: BLE001 — e.g. REPLIERS_API_KEY not set for the live source
    st.error(f"Could not initialize the {data_source} data source: {e}")
    st.stop()

run_clicked = st.button("Run analysis", type="primary", disabled=not subject_id)

stage_order = ["Resolve property", "Find sales", "Expand search", "Review comparables", "Calculate value", "Generate report"]
stage_position = {"idle": 0, "awaiting_approval": 2, "awaiting_review": 3, "done": 6}.get(st.session_state.stage, 0)
st.progress(stage_position / len(stage_order), text=" → ".join(
    (f"✅ {label}" if i < stage_position else f"● {label}" if i == stage_position else label)
    for i, label in enumerate(stage_order)
))


def _accept_graph_result(result) -> None:
    st.session_state.working_state = result
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        st.session_state.pending_interrupt = payload
        st.session_state.stage = "awaiting_review" if payload.get("type") in {
            "comparable_review", "low_evidence_confirmation"
        } else "awaiting_approval"
    else:
        st.session_state.stage = "done"
        st.session_state.final_state = result
if run_clicked:
    reset_run()
    st.session_state.thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    try:
        result = graph.invoke(initial_state(subject_id, analysis_date), config=config)
    except Exception as e:  # noqa: BLE001 — surface any live-API/network error to the UI, not a crash
        st.session_state.error = str(e)
        st.session_state.stage = "idle"
    else:
        _accept_graph_result(result)

if st.session_state.error:
    message = st.session_state.error
    if "REPLIERS_API_KEY" in message:
        message = "A Repliers API key is required for live mode. Add REPLIERS_API_KEY or use fixture mode."
    elif "429" in message:
        message = "The Repliers rate limit was reached. Wait for the quota window or use fixture mode."
    elif "401" in message or "403" in message:
        message = "Repliers authentication failed. Check the API key or use fixture mode."
    elif "timeout" in message.lower():
        message = "The Repliers request timed out. Retry or use fixture mode."
    st.error(f"Analysis failed: {message}")
    if data_source == LIVE_LABEL:
        st.info("Recovery: switch Data source to the frozen demonstration dataset.")

working = st.session_state.working_state
if working and working.get("subject"):
    subject = working["subject"]
    st.subheader("Subject property")
    st.write(
        f"{subject.address.full or subject.source_listing_id} — "
        f"{subject.characteristics.bedrooms or 'n/a'} bd, "
        f"{subject.characteristics.baths_full or 'n/a'} ba, "
        f"{subject.characteristics.living_area_sqft or 'n/a'} sqft"
    )

if st.session_state.stage == "awaiting_approval":
    payload = st.session_state.pending_interrupt
    st.warning(
        f"**{payload['question']}**\n\n"
        f"Current step: {payload['current_step']} — {payload['found_so_far']} qualified comparable(s) found so far."
    )
    col1, col2 = st.columns(2)

    def _resume(answer: bool) -> None:
        config = {"configurable": {"thread_id": st.session_state.thread_id}}
        try:
            result = graph.invoke(Command(resume=answer), config=config)
        except Exception as e:  # noqa: BLE001
            st.session_state.error = str(e)
            st.session_state.stage = "idle"
            return
        _accept_graph_result(result)

    with col1:
        if st.button(f"✅ Approve — expand to {payload['proposed_next_step']}", width="stretch"):
            _resume(True)
            st.rerun()
    with col2:
        if st.button("🛑 Decline — finish with what was found", width="stretch"):
            _resume(False)
            st.rerun()

if st.session_state.stage == "awaiting_review":
    payload = st.session_state.pending_interrupt
    if payload.get("type") == "low_evidence_confirmation":
        st.warning(payload["question"])
        if st.button("✅ Confirm low-evidence report"):
            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            _accept_graph_result(graph.invoke(Command(resume=True), config=config))
            st.rerun()
    else:
        rows = payload["comparables"]
        st.subheader("Review proposed comparables")
        st.caption("The checked listing IDs are the only records the valuation and briefing will use.")
        st.dataframe(rows, width="stretch", hide_index=True)
        all_ids = [row["id"] for row in rows]
        selected_ids = st.multiselect("Approved comparable IDs", all_ids, default=all_ids)
        rejected = [value for value in all_ids if value not in selected_ids]
        rejection_reason = st.text_input("Optional reason for rejected comparables", disabled=not rejected)
        low_evidence = len(selected_ids) < payload["minimum_required"]
        confirm_low = st.checkbox("I confirm a low-evidence report", disabled=not low_evidence)
        if low_evidence:
            st.warning(f"Fewer than {payload['minimum_required']} comparables remain.")
        if st.button("✅ Confirm comparable set", disabled=low_evidence and not confirm_low):
            answer = {
                "selected_ids": selected_ids,
                "rejection_reasons": {value: rejection_reason for value in rejected if rejection_reason},
                "confirm_low_evidence": confirm_low,
            }
            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            try:
                result = graph.invoke(Command(resume=answer), config=config)
                _accept_graph_result(result)
            except Exception as e:  # noqa: BLE001
                st.session_state.error = f"Graph resume/checkpoint failure: {e}"
                st.session_state.stage = "idle"
            st.rerun()
if st.session_state.stage == "done" and st.session_state.final_state:
    final = st.session_state.final_state
    if final["status"] in {"no_subject", "invalid_subject"}:
        st.error(final["briefing"])
    else:
        result = final["last_result"]
        m1, m2, m3 = st.columns(3)
        m1.metric("Comparables selected", len(result.selected))
        m2.metric("Search steps tried", sum(1 for e in final["expansion_log"] if e.kind == "step"))
        m3.metric("Sufficient (≥3 found)", "Yes" if result.sufficient else "No")

        st.markdown(final["briefing"])
        if final.get("reporting_status") == "AI narrative generated":
            st.success(f"AI reporting agent: {final['reporting_status']} ({final['reporting_model']})")
        else:
            st.info(f"AI reporting agent: {final.get('reporting_status') or 'deterministic fallback'}")
        st.download_button(
            "Download Markdown briefing",
            data=final["briefing"],
            file_name=f"comparable-analysis-{final['subject'].source_listing_id}.md",
            mime="text/markdown",
        )

        checks = final["briefing_checks"] or []
        n_pass = sum(1 for c in checks if c.startswith("PASS"))
        with st.expander(f"Report self-check — {n_pass}/{len(checks)} passed"):
            for c in checks:
                st.markdown(("✅ " if c.startswith("PASS") else "❌ ") + c)
