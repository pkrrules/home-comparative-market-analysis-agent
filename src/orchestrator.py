"""
Agent 3: Orchestrator and Report Agent (LangGraph half).

Controls progressive search expansion, pauses for human approval when
older or weaker evidence is needed, maintains graph state via a
checkpointer, and calls report.py to generate and check the briefing.

Graph shape:

    load_subject --> run_step --(sufficient)--> generate_briefing --> check_briefing --> END
                        ^  \--(insufficient, steps remain)--> request_approval --(granted)--/
                        |                                           \--(declined)--> generate_briefing
                        \------------------------------------------------------------/
                    (insufficient, no steps remain) --> generate_briefing

`request_approval` is where the pause happens: it calls LangGraph's
`interrupt()`, which suspends the graph and returns control to the caller
(see run_interactive / the CLI demo script) until resumed with
`Command(resume=<bool>)` — the mechanism Phase 5's UI will drive directly
with a real approve/decline button, in place of run_interactive's
synchronous callback.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Any, Callable, TypedDict

import inspect

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import canonical_schema
import comparable_engine
import report
from canonical_schema import CanonicalProperty
from comparable_engine import (
    MIN_QUALIFIED,
    SEARCH_EXPANSION_STEPS,
    ComparableSearchResult,
    fetch_and_evaluate,
)
from data_agent import PropertyDataAgent
from report import BriefingFacts, ExpansionLogEntry, check_briefing, generate_briefing
from reporting_agent import OpenAIReportingAgent, ReportingOutcome


def _classes_in(module) -> list[tuple[str, str]]:
    return [
        (module.__name__, name)
        for name, obj in inspect.getmembers(module, inspect.isclass)
        if obj.__module__ == module.__name__
    ]


class OrchestratorState(TypedDict):
    subject_identifier: str
    analysis_date: date
    subject: CanonicalProperty | None
    step_index: int
    last_result: ComparableSearchResult | None
    proposed_result: ComparableSearchResult | None
    approved_comparable_ids: list[str]
    rejection_reasons: dict[str, str]
    expansion_log: list[ExpansionLogEntry]
    status: str  # "running" | "no_subject" | "invalid_subject" | "declined" | "done"
    briefing: str | None
    briefing_facts: BriefingFacts | None
    briefing_checks: list[str] | None
    reporting_status: str | None
    reporting_model: str | None


def _month_phrase(days: int) -> str:
    return {180: "six months", 365: "twelve months"}.get(days, f"{days} days")


def build_expansion_question(result: ComparableSearchResult, next_step) -> str:
    """Mirrors the project plan's own human-in-the-loop wording, with real
    counts substituted in rather than the plan's illustrative "two"."""
    found = len(result.selected)
    cur = result.step
    plural = "" if found == 1 else "s"
    verb = "was" if found == 1 else "were"
    if next_step.radius_miles != cur.radius_miles and next_step.max_age_days == cur.max_age_days:
        return (
            f"Only {found} qualified comparable{plural} {verb} found within {cur.radius_miles:g} miles "
            f"and {cur.max_age_days} days of the demonstration analysis date. "
            f"May the search expand to {next_step.radius_miles:g} miles?"
        )
    return (
        f"Fewer than {MIN_QUALIFIED} qualified comparables remain ({found} found). "
        f"May the analysis include sales up to {_month_phrase(next_step.max_age_days)} "
        "before the demonstration analysis date?"
    )


# Our own dataclasses/enums travel through checkpointed state as-is (state
# holds live CanonicalProperty/ComparableSearchResult objects, not dicts) —
# tell the checkpoint serializer these are trusted, rather than leaving the
# "will be blocked in a future version" warning unaddressed. Needs exact
# (module, classname) pairs — a bare module-name tuple is accepted by the
# constructor but silently allows nothing, so this is generated from the
# actual classes rather than hand-listed (verified against the concrete
# failure: without this, blocked deserialization leaves plain dicts in
# state instead of raising, which then breaks downstream attribute access).
_TRUSTED_MSGPACK_MODULES = (
    _classes_in(canonical_schema) + _classes_in(comparable_engine) + _classes_in(report)
)


def build_graph(
    agent: PropertyDataAgent,
    provider_limit: int = 100,
    reporting_agent: OpenAIReportingAgent | None = None,
):
    """provider_limit is passed straight through to fetch_and_evaluate.
    Against the live RepliersProvider the default is fine — the server
    applies real radius filtering, so even a small pool is the *right*
    small pool. Against RepliersFixtureProvider, which does NOT filter by
    lat/lng/radius (see its docstring), a small limit instead means "the
    first N fixture records in file order", most of which won't be near
    any given subject — tests/demos run against the fixture provider
    should pass a larger limit (e.g. 500) to get a geographically
    representative candidate pool.
    """
    def load_subject(state: OrchestratorState) -> dict:
        subject = agent.find_subject(state["subject_identifier"])
        if subject is None:
            return {"status": "no_subject"}
        missing = []
        if subject.geo.lat is None or subject.geo.lng is None:
            missing.append("coordinates")
        if not subject.characteristics.living_area_sqft:
            missing.append("living area")
        if missing:
            return {"subject": subject, "status": "invalid_subject", "briefing": f"Subject property is missing {', '.join(missing)}; comparable valuation cannot proceed."}
        return {"subject": subject, "status": "running"}

    def route_after_load(state: OrchestratorState) -> str:
        return "run_step" if state["status"] == "running" else "generate_briefing"

    def run_step(state: OrchestratorState) -> dict:
        step = SEARCH_EXPANSION_STEPS[state["step_index"]]
        result = fetch_and_evaluate(agent, state["subject"], step, state["analysis_date"], provider_limit=provider_limit)
        log_entry = ExpansionLogEntry(
            kind="step", step_label=step.label, found=len(result.selected), sufficient=result.sufficient,
        )
        return {"last_result": result, "expansion_log": state["expansion_log"] + [log_entry]}

    def route_after_step(state: OrchestratorState) -> str:
        result = state["last_result"]
        if result.sufficient:
            return "review_comparables"
        if state["step_index"] + 1 < len(SEARCH_EXPANSION_STEPS):
            next_step = SEARCH_EXPANSION_STEPS[state["step_index"] + 1]
            if next_step.max_age_days == result.step.max_age_days:
                return "auto_expand_radius"
            return "request_approval"
        return "review_comparables"  # review even a low-evidence set

    def auto_expand_radius(state: OrchestratorState) -> dict:
        """Radius-only expansion is deterministic and low-risk in the demo.
        Preserve it in the trace without interrupting the user; temporal
        expansion still requires explicit approval."""
        next_step = SEARCH_EXPANSION_STEPS[state["step_index"] + 1]
        log_entry = ExpansionLogEntry(
            kind="approval", step_label=next_step.label, decision="automatic",
        )
        return {
            "step_index": state["step_index"] + 1,
            "expansion_log": state["expansion_log"] + [log_entry],
        }

    def request_approval(state: OrchestratorState) -> dict:
        next_step = SEARCH_EXPANSION_STEPS[state["step_index"] + 1]
        question = build_expansion_question(state["last_result"], next_step)
        approved = interrupt({
            "question": question,
            "current_step": state["last_result"].step.label,
            "found_so_far": len(state["last_result"].selected),
            "proposed_next_step": next_step.label,
        })
        decision = "granted" if approved else "declined"
        log_entry = ExpansionLogEntry(kind="approval", step_label=next_step.label, decision=decision)
        if approved:
            return {"step_index": state["step_index"] + 1, "expansion_log": state["expansion_log"] + [log_entry]}
        return {"status": "declined", "expansion_log": state["expansion_log"] + [log_entry]}

    def route_after_approval(state: OrchestratorState) -> str:
        return "review_comparables" if state["status"] == "declined" else "run_step"

    def review_comparables(state: OrchestratorState) -> dict:
        proposed = state["last_result"]
        rows = []
        for sc in proposed.selected:
            c = sc.candidate
            rows.append({
                "id": c.source_listing_id,
                "address": c.address.full or c.source_listing_id,
                "distance_miles": round(sc.distance_miles, 2),
                "sale_date": (c.transaction.close_date or "")[:10],
                "sale_price": c.transaction.close_price,
                "living_area_sqft": c.characteristics.living_area_sqft,
                "price_per_sqft": round(sc.price_per_sqft, 2) if sc.price_per_sqft else None,
                "similarity_score": round(sc.similarity_score, 3),
                "confidence": sc.confidence,
                "why_selected": "; ".join(sc.differences) if sc.differences else "close match on scored attributes",
            })
        decision = interrupt({
            "type": "comparable_review",
            "question": "Review the automatically proposed comparable set and confirm the records to use.",
            "comparables": rows,
            "minimum_required": MIN_QUALIFIED,
        })
        if isinstance(decision, bool):
            selected_ids = [row["id"] for row in rows] if decision else []
            reasons = {}
            confirm_low = decision
        else:
            selected_ids = list(decision.get("selected_ids", []))
            reasons = dict(decision.get("rejection_reasons", {}))
            confirm_low = bool(decision.get("confirm_low_evidence", False))
        valid_ids = {row["id"] for row in rows}
        selected_ids = [value for value in selected_ids if value in valid_ids]
        if len(selected_ids) < MIN_QUALIFIED and not confirm_low:
            confirmation = interrupt({
                "type": "low_evidence_confirmation",
                "question": f"Only {len(selected_ids)} comparable(s) remain. Confirm a low-evidence report?",
                "selected_ids": selected_ids,
            })
            if not confirmation:
                selected_ids = [row["id"] for row in rows]
        approved = [sc for sc in proposed.selected if sc.candidate.source_listing_id in selected_ids]
        reviewed = replace(proposed, selected=approved, sufficient=len(approved) >= MIN_QUALIFIED)
        return {
            "proposed_result": proposed,
            "last_result": reviewed,
            "approved_comparable_ids": selected_ids,
            "rejection_reasons": reasons,
        }

    def generate_briefing_node(state: OrchestratorState) -> dict:
        if state["status"] == "no_subject":
            return {"briefing": f"No subject property could be resolved for '{state['subject_identifier']}'.", "briefing_facts": None}
        if state["status"] == "invalid_subject":
            return {"briefing": state["briefing"], "briefing_facts": None}
        text, facts = generate_briefing(
            state["subject"], state["analysis_date"], state["expansion_log"], state["last_result"],
        )
        outcome = (
            reporting_agent.generate(state["subject"], state["last_result"])
            if reporting_agent
            else ReportingOutcome(None, "deterministic fallback: AI reporting disabled")
        )
        if outcome.narrative:
            text = f"{text}\n\n{outcome.narrative}\n"
        return {
            "briefing": text,
            "briefing_facts": facts,
            "reporting_status": outcome.status,
            "reporting_model": outcome.model,
            "status": "done",
        }

    def check_briefing_node(state: OrchestratorState) -> dict:
        if state["briefing_facts"] is None:
            return {"briefing_checks": []}
        return {"briefing_checks": check_briefing(state["briefing"], state["briefing_facts"])}

    graph = StateGraph(OrchestratorState)
    graph.add_node("load_subject", load_subject)
    graph.add_node("run_step", run_step)
    graph.add_node("request_approval", request_approval)
    graph.add_node("auto_expand_radius", auto_expand_radius)
    graph.add_node("review_comparables", review_comparables)
    graph.add_node("generate_briefing", generate_briefing_node)
    graph.add_node("check_briefing", check_briefing_node)

    graph.add_edge(START, "load_subject")
    graph.add_conditional_edges("load_subject", route_after_load, ["run_step", "generate_briefing"])
    graph.add_conditional_edges("run_step", route_after_step, ["auto_expand_radius", "request_approval", "review_comparables"])
    graph.add_edge("auto_expand_radius", "run_step")
    graph.add_conditional_edges("request_approval", route_after_approval, ["run_step", "review_comparables"])
    graph.add_edge("review_comparables", "generate_briefing")
    graph.add_edge("generate_briefing", "check_briefing")
    graph.add_edge("check_briefing", END)

    serde = JsonPlusSerializer(allowed_msgpack_modules=_TRUSTED_MSGPACK_MODULES)
    return graph.compile(checkpointer=InMemorySaver(serde=serde))


def initial_state(subject_identifier: str, analysis_date: date) -> OrchestratorState:
    return OrchestratorState(
        subject_identifier=subject_identifier,
        analysis_date=analysis_date,
        subject=None,
        step_index=0,
        last_result=None,
        proposed_result=None,
        approved_comparable_ids=[],
        rejection_reasons={},
        expansion_log=[],
        status="running",
        briefing=None,
        briefing_facts=None,
        briefing_checks=None,
        reporting_status=None,
        reporting_model=None,
    )


def run_interactive(
    graph, thread_id: str, subject_identifier: str, analysis_date: date,
    approval_callback: Callable[[dict[str, Any]], bool],
) -> OrchestratorState:
    """Drives the graph synchronously to completion, answering each
    interrupt via approval_callback(interrupt_payload) -> bool. This is a
    convenience for tests and a CLI/notebook demo — Phase 5's UI will call
    graph.invoke / Command(resume=...) directly instead, showing the
    question and waiting for a real button click between calls, matching
    the same pause-and-resume mechanism this function only simulates
    synchronously.
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(initial_state(subject_identifier, analysis_date), config=config)
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        if payload.get("type") == "comparable_review":
            answer = {
                "selected_ids": [row["id"] for row in payload["comparables"]],
                "rejection_reasons": {},
                "confirm_low_evidence": True,
            }
        elif payload.get("type") == "low_evidence_confirmation":
            answer = True
        else:
            answer = approval_callback(payload)
        result = graph.invoke(Command(resume=answer), config=config)
    return result
