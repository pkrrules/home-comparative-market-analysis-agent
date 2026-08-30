"""
Agent 3's report half: generates and checks the one-page demonstration
briefing. Pure and deterministic — templated text built directly from
computed facts, not LLM prose, matching the project plan's emphasis on a
"fully traceable" briefing (see the plan's success criterion). No network,
no LangGraph dependency — the orchestrator (orchestrator.py) calls these
as its last two graph nodes.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from canonical_schema import CanonicalProperty
from comparable_engine import ComparableSearchResult, MIN_QUALIFIED

SAMPLE_DATA_DISCLAIMER = (
    "using sample Repliers records — not current market transactions"
)


@dataclass
class ExpansionLogEntry:
    kind: str  # "step" | "approval"
    step_label: str
    found: int | None = None
    sufficient: bool | None = None
    decision: str | None = None  # "granted" | "declined", for kind="approval"


def _categorize_exclusion(reason: str) -> str:
    """Buckets the free-text exclusion reasons comparable_engine.py produces
    into a small set of categories for summary counts. Coupled to that
    module's exact wording by design (both are owned together) — if the
    wording there changes, update the substrings below."""
    if "subject property itself" in reason:
        return "is the subject property"
    if "Not a closed sale" in reason:
        return "not a closed sale"
    if "Missing coordinates" in reason:
        return "missing coordinates"
    if "exceeds the" in reason and "search radius" in reason:
        return "outside search radius"
    if "after the analysis date" in reason:
        return "closed after the analysis date"
    if "before the analysis date" in reason and "window" in reason:
        return "outside the date window"
    if "Property type mismatch" in reason:
        return "property type mismatch"
    if "Sale price fails plausibility" in reason:
        return "implausible sale price"
    if "Living area fails plausibility" in reason:
        return "implausible living area"
    if "Missing or unparseable close date" in reason:
        return "missing close date"
    return "other"


def _fmt_money(value: float) -> str:
    return f"${value:,.0f}"


def _subject_line(subject: CanonicalProperty) -> str:
    addr = subject.address
    parts = [p for p in [addr.full, addr.city, addr.state, addr.postal_code] if p]
    return ", ".join(parts) if parts else f"{subject.source}:{subject.source_listing_id}"


@dataclass
class BriefingFacts:
    """The exact numbers/ids the briefing text is built from — check_briefing
    verifies the rendered text actually contains these, catching template
    bugs rather than re-trusting the same computation twice."""
    subject_id: str
    selected_ids: list[str]
    median_price_per_sqft: float | None
    weighted_price_per_sqft: float | None
    low_estimate: float | None
    high_estimate: float | None
    point_estimate: float | None
    analysis_date: date
    final_step_label: str
    sufficient: bool


@dataclass
class ValuationSummary:
    weighted_price_per_sqft: float | None
    median_price_per_sqft: float | None
    low_estimate: float | None
    high_estimate: float | None
    point_estimate: float | None
    outlier_ids: list[str]
    confidence: str


def calculate_valuation(subject: CanonicalProperty, selected: list) -> ValuationSummary:
    """Reproducible robust valuation. Obvious $/sqft outliers (1.5 IQR)
    are flagged and excluded from the weighted indication, never hidden."""
    usable = [sc for sc in selected if sc.price_per_sqft is not None]
    values = [sc.price_per_sqft for sc in usable]
    median_ppsf = statistics.median(values) if values else None
    outlier_ids: list[str] = []
    retained = usable
    if len(values) >= 4:
        quartiles = statistics.quantiles(values, n=4, method="inclusive")
        q1, q3 = quartiles[0], quartiles[2]
        lower, upper = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
        retained = [sc for sc in usable if lower <= sc.price_per_sqft <= upper]
        outlier_ids = [sc.candidate.source_listing_id for sc in usable if sc not in retained]
    weights = [max(sc.similarity_score, 0.01) for sc in retained]
    weighted = (
        sum(sc.price_per_sqft * weight for sc, weight in zip(retained, weights)) / sum(weights)
        if retained else None
    )
    sqft = subject.characteristics.living_area_sqft
    point = sqft * weighted if sqft and weighted else None
    low = high = None
    if sqft and retained:
        clean = sorted(sc.price_per_sqft for sc in retained)
        if len(clean) >= 3:
            qs = statistics.quantiles(clean, n=4, method="inclusive")
            low, high = sqft * qs[0], sqft * qs[2]
        else:
            low, high = sqft * min(clean), sqft * max(clean)
        sale_prices = sorted(sc.candidate.transaction.close_price for sc in retained if sc.candidate.transaction.close_price)
        if sale_prices and point is not None:
            # Cross-check against the observed sale-price distribution; keep
            # the indication inside a defensible, traceable evidence band.
            point = min(max(point, sale_prices[0]), sale_prices[-1])
    if len(retained) < MIN_QUALIFIED:
        confidence = "low"
    elif outlier_ids or any(sc.confidence != "high" for sc in retained):
        confidence = "medium"
    else:
        confidence = "high"
    return ValuationSummary(weighted, median_ppsf, low, high, point, outlier_ids, confidence)


def generate_briefing(
    subject: CanonicalProperty,
    analysis_date: date,
    expansion_log: list[ExpansionLogEntry],
    final_result: ComparableSearchResult,
) -> tuple[str, BriefingFacts]:
    selected = final_result.selected
    valuation = calculate_valuation(subject, selected)
    median_ppsf = valuation.median_price_per_sqft
    low_estimate, high_estimate, point_estimate = valuation.low_estimate, valuation.high_estimate, valuation.point_estimate
    subject_sqft = subject.characteristics.living_area_sqft

    lines: list[str] = []
    lines.append("# Comparable Home Analysis — Demonstration Briefing")
    lines.append("")
    lines.append(f"**Subject property:** {_subject_line(subject)}  (source id: `{subject.source_listing_id}`)")
    lines.append(
        f"**Demonstration analysis as of {analysis_date.isoformat()}**, {SAMPLE_DATA_DISCLAIMER}. "
        "This briefing demonstrates the comparable-analysis workflow; it does not estimate the "
        "present value of an arbitrary real home."
    )
    lines.append("")

    lines.append("## Search process")
    lines.append("")
    for entry in expansion_log:
        if entry.kind == "step":
            status = "sufficient ✅" if entry.sufficient else "insufficient"
            lines.append(f"- **{entry.step_label}** → {entry.found} qualified comparable(s) found ({status})")
        else:
            if entry.decision == "automatic":
                lines.append(f"  - Search radius automatically expanded to **{entry.step_label}**")
            else:
                verb = "approved" if entry.decision == "granted" else "declined"
                lines.append(f"  - Search expansion to **{entry.step_label}** {verb} by user")
    lines.append("")

    lines.append(f"## Selected comparables ({len(selected)})")
    lines.append("")
    if selected:
        lines.append("| # | Address | Distance | Closed | Price | $/sqft | Confidence | Notable differences |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for i, sc in enumerate(selected, 1):
            c = sc.candidate
            addr = c.address.full or f"{c.source}:{c.source_listing_id}"
            close_date = (c.transaction.close_date or "")[:10]
            price = _fmt_money(c.transaction.close_price) if c.transaction.close_price else "n/a"
            ppsf = f"${sc.price_per_sqft:,.0f}" if sc.price_per_sqft else "n/a"
            diffs = "; ".join(sc.differences) if sc.differences else "no notable differences"
            lines.append(
                f"| {i} | {addr} (`{c.source_listing_id}`) | {sc.distance_miles:.1f} mi | {close_date} | "
                f"{price} | {ppsf} | {sc.confidence} | {diffs} |"
            )
    else:
        lines.append("_No qualified comparables were found within the search parameters tried._")
    lines.append("")

    lines.append("## Valuation estimate (derived from sample data — not an appraisal)")
    lines.append("")
    if point_estimate is not None:
        lines.append(f"- Subject living area: {subject_sqft:,.0f} sqft")
        lines.append(f"- Approved comparables: {len(selected)}")
        lines.append(f"- Similarity-weighted $/sqft: ${valuation.weighted_price_per_sqft:,.0f}")
        lines.append(f"- Median $/sqft sanity check: ${median_ppsf:,.0f}")
        lines.append(f"- Central indication: **{_fmt_money(point_estimate)}**")
        lines.append(f"- Robust indicative range: {_fmt_money(low_estimate)} – {_fmt_money(high_estimate)}")
        lines.append(f"- Confidence: **{valuation.confidence}**")
        lines.append("- Method: similarity-weighted $/sqft × subject area; IQR outliers excluded, quartile range, sale-price cross-check.")
        if valuation.outlier_ids:
            lines.append(f"- Flagged $/sqft outliers (excluded from calculation): {', '.join(f'`{x}`' for x in valuation.outlier_ids)}")
    else:
        lines.append("_Not computed — insufficient comparables with both a sale price and living area._")
    lines.append("")

    lines.append(f"## Excluded candidates ({len(final_result.excluded)})")
    lines.append("")
    if final_result.excluded:
        counts: dict[str, int] = {}
        for ex in final_result.excluded:
            cat = _categorize_exclusion(ex.reason)
            counts[cat] = counts.get(cat, 0) + 1
        for cat, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {n} — {cat}")
    else:
        lines.append("_None excluded — every candidate considered was subject or otherwise trivially out of scope._")
    lines.append("")

    lines.append("## Data provenance")
    lines.append("")
    lines.append(
        f"- Source: {subject.source} API (sample/sandbox data — see project docs for details)."
    )
    lines.append("- Every comparable above is traceable to its own source listing id, shown in parentheses.")
    disclaimers = {sc.candidate.attribution.disclaimer for sc in selected if sc.candidate.attribution.disclaimer}
    for d in disclaimers:
        lines.append(f"- {d}")
    lines.append("")

    text = "\n".join(lines)
    facts = BriefingFacts(
        subject_id=subject.source_listing_id,
        selected_ids=[sc.candidate.source_listing_id for sc in selected],
        median_price_per_sqft=median_ppsf,
        weighted_price_per_sqft=valuation.weighted_price_per_sqft,
        low_estimate=low_estimate,
        high_estimate=high_estimate,
        point_estimate=point_estimate,
        analysis_date=analysis_date,
        final_step_label=final_result.step.label,
        sufficient=final_result.sufficient,
    )
    return text, facts


def check_briefing(text: str, facts: BriefingFacts) -> list[str]:
    """Deterministic self-check: does the rendered text actually contain
    what was computed? Each result is prefixed PASS/FAIL. Not a substitute
    for generate_briefing's correctness — a check against template bugs
    (wrong variable interpolated, a value silently dropped), which is
    exactly the kind of traceability gap the project plan asks for."""
    results: list[str] = []

    def check(label: str, condition: bool) -> None:
        results.append(f"{'PASS' if condition else 'FAIL'}: {label}")

    check("subject id appears in briefing", f"`{facts.subject_id}`" in text)
    for cid in facts.selected_ids:
        check(f"selected comparable `{cid}` id appears in briefing", f"`{cid}`" in text)
    check("analysis date appears in briefing", facts.analysis_date.isoformat() in text)
    check("sample-data disclaimer appears in briefing", SAMPLE_DATA_DISCLAIMER in text)

    if facts.point_estimate is not None:
        check("point estimate value appears in briefing", _fmt_money(facts.point_estimate) in text)
        check("low estimate value appears in briefing", _fmt_money(facts.low_estimate) in text)
        check("high estimate value appears in briefing", _fmt_money(facts.high_estimate) in text)
    else:
        check("briefing states valuation was not computed", "Not computed" in text)

    # Every selected comp should render as its own numbered table row —
    # catches a table that silently drops or miscounts rows.
    for i in range(1, len(facts.selected_ids) + 1):
        check(f"comparable table row #{i} rendered", f"| {i} |" in text)

    return results
