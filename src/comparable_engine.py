"""
Agent 2: Comparable Analysis Agent.

Applies eligibility rules, runs deterministic calculations, ranks
candidates, and explains similarities/differences/exclusions/confidence —
per the project plan. Pure and provider-agnostic: everything here operates
on CanonicalProperty records already produced by Agent 1 (data_agent.py).

Deliberately does NOT loop through the search-expansion steps and decide
on its own to move to the next one — that decision belongs to Agent 3 /
the LangGraph orchestration (Phase 4), which pauses for human approval
between steps. This module exposes `evaluate_candidates` (and
`fetch_and_evaluate`, for convenience) as a single, deterministic
operation for one step; SEARCH_EXPANSION_STEPS documents the sequence
Agent 3 is expected to drive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable

from canonical_schema import CanonicalProperty, FieldStatus
from distance import haversine_miles, miles_to_km
from data_agent import PropertyDataAgent

# The exact sequence described in the project plan's human-in-the-loop
# example: "Only two qualified comparables were found within three miles
# and 90 days ... expand to five miles?" then "... include sales up to six
# months / twelve months before the analysis date?"
@dataclass(frozen=True)
class SearchStep:
    radius_miles: float
    max_age_days: int
    label: str


SEARCH_EXPANSION_STEPS: list[SearchStep] = [
    SearchStep(3, 90, "3 miles, 90 days"),
    SearchStep(5, 90, "5 miles, 90 days"),
    SearchStep(5, 180, "5 miles, 6 months"),
    SearchStep(5, 365, "5 miles, 12 months"),
]

MIN_QUALIFIED = 3
MAX_SELECTED = 10

# Scoring weights — a deterministic, documented composite, not a learned
# model. Each component is normalized to roughly [0, 1] (higher = better
# match) before weighting; see _score_candidate.
WEIGHT_DISTANCE = 0.30
WEIGHT_RECENCY = 0.20
WEIGHT_SIZE = 0.30
WEIGHT_BEDS = 0.10
WEIGHT_BATHS = 0.10


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


@dataclass
class Exclusion:
    candidate: CanonicalProperty
    reason: str


@dataclass
class ScoredComparable:
    candidate: CanonicalProperty
    distance_miles: float
    days_before_analysis: int
    similarity_score: float
    confidence: str  # "high" | "medium" | "low"
    confidence_reasons: list[str]
    price_per_sqft: float | None
    differences: list[str]  # human-readable, e.g. "200 sqft larger", "1 fewer bedroom"


@dataclass
class ComparableSearchResult:
    step: SearchStep
    analysis_date: date
    candidates_considered: int
    selected: list[ScoredComparable]
    excluded: list[Exclusion]
    sufficient: bool  # len(selected) >= MIN_QUALIFIED


def _is_subject(subject: CanonicalProperty, candidate: CanonicalProperty) -> bool:
    return subject.source == candidate.source and subject.source_listing_id == candidate.source_listing_id


def _property_type_compatible(subject: CanonicalProperty, candidate: CanonicalProperty) -> bool:
    """Broad type must match (e.g. both "Residential", or both "RES").
    Deliberately does not compare subtype (house vs. condo) — that's a
    scoring/confidence signal, not a hard eligibility gate."""
    st, ct = subject.characteristics.property_type, candidate.characteristics.property_type
    if st is None or ct is None:
        return True  # can't judge; let downstream field-flag checks handle missing data
    return st == ct


def _check_eligibility(
    subject: CanonicalProperty,
    candidate: CanonicalProperty,
    step: SearchStep,
    analysis_date: date,
) -> tuple[bool, str | None, float | None, int | None]:
    """Returns (eligible, exclusion_reason, distance_miles, days_before_analysis).
    distance/days are returned even on exclusion where computable, so callers
    can explain *how close* an excluded candidate came."""
    if _is_subject(subject, candidate):
        return False, "This is the subject property itself", None, None

    if candidate.transaction.status != "Closed":
        return False, f"Not a closed sale (status={candidate.transaction.status!r})", None, None

    if candidate.geo.lat is None or candidate.geo.lng is None:
        return False, "Missing coordinates", None, None

    # Subject coordinates are validated once, up front, by evaluate_candidates
    # — not re-checked per candidate here.
    distance = haversine_miles(subject.geo.lat, subject.geo.lng, candidate.geo.lat, candidate.geo.lng)

    close_date = _parse_date(candidate.transaction.close_date)
    if close_date is None:
        return False, "Missing or unparseable close date", distance, None
    days_before = (analysis_date - close_date).days

    if close_date > analysis_date:
        return False, f"Closed {-days_before} day(s) after the analysis date", distance, days_before

    if distance > step.radius_miles:
        return False, f"{distance:.1f} mi exceeds the {step.radius_miles} mi search radius", distance, days_before

    if days_before > step.max_age_days:
        return False, f"Closed {days_before} days before the analysis date, outside the {step.max_age_days}-day window", distance, days_before

    if not _property_type_compatible(subject, candidate):
        return False, (
            f"Property type mismatch (subject: {subject.characteristics.property_type!r}, "
            f"candidate: {candidate.characteristics.property_type!r})"
        ), distance, days_before

    price_flag = candidate.field_flags.get("close_price")
    if price_flag and price_flag.status == FieldStatus.IMPLAUSIBLE:
        return False, f"Sale price fails plausibility check ({price_flag.reason})", distance, days_before

    area_flag = candidate.field_flags.get("living_area_sqft")
    if area_flag and area_flag.status == FieldStatus.IMPLAUSIBLE:
        return False, f"Living area fails plausibility check ({area_flag.reason})", distance, days_before

    return True, None, distance, days_before


def _normalized(value: float, worst: float) -> float:
    """1.0 at value=0, 0.0 at value=worst (clamped)."""
    if worst <= 0:
        return 1.0
    return max(0.0, 1.0 - value / worst)


def _score_candidate(
    subject: CanonicalProperty, candidate: CanonicalProperty, distance: float, days_before: int, step: SearchStep,
) -> tuple[float, list[str]]:
    differences: list[str] = []

    distance_score = _normalized(distance, step.radius_miles)
    recency_score = _normalized(days_before, step.max_age_days)

    s_area, c_area = subject.characteristics.living_area_sqft, candidate.characteristics.living_area_sqft
    if s_area and c_area and s_area > 0:
        pct_diff = abs(c_area - s_area) / s_area
        size_score = max(0.0, 1.0 - pct_diff)
        if abs(c_area - s_area) >= 50:
            direction = "larger" if c_area > s_area else "smaller"
            differences.append(f"{abs(c_area - s_area):.0f} sqft {direction} ({pct_diff:.0%})")
    else:
        size_score = 0.5  # neutral — can't judge

    s_beds, c_beds = subject.characteristics.bedrooms, candidate.characteristics.bedrooms
    if s_beds is not None and c_beds is not None:
        bed_diff = c_beds - s_beds
        bed_score = max(0.0, 1.0 - min(abs(bed_diff), 3) / 3)
        if bed_diff != 0:
            differences.append(f"{abs(bed_diff)} {'more' if bed_diff > 0 else 'fewer'} bedroom(s)")
    else:
        bed_score = 0.5

    s_baths = (subject.characteristics.baths_full or 0) + 0.5 * (subject.characteristics.baths_half or 0)
    c_baths = (candidate.characteristics.baths_full or 0) + 0.5 * (candidate.characteristics.baths_half or 0)
    if subject.characteristics.baths_full is not None and candidate.characteristics.baths_full is not None:
        bath_diff = c_baths - s_baths
        bath_score = max(0.0, 1.0 - min(abs(bath_diff), 3) / 3)
        if bath_diff != 0:
            differences.append(f"{abs(bath_diff):g} {'more' if bath_diff > 0 else 'fewer'} bathroom(s)")
    else:
        bath_score = 0.5

    score = (
        WEIGHT_DISTANCE * distance_score
        + WEIGHT_RECENCY * recency_score
        + WEIGHT_SIZE * size_score
        + WEIGHT_BEDS * bed_score
        + WEIGHT_BATHS * bath_score
    )
    return score, differences


def _confidence(candidate: CanonicalProperty) -> tuple[str, list[str]]:
    """High/medium/low, derived from Agent 1's field flags — not re-deriving
    plausibility, just summarizing it for the briefing.

    Note: within evaluate_candidates, "low" (core valuation fields —
    close_price/living_area_sqft — implausible) is defined here but never
    actually reached, because _check_eligibility already excludes those
    candidates outright: a sale price or living area that fails a sanity
    check can't be trusted enough to feed $/sqft or the similarity score at
    all, which is a stronger statement than "include with a caveat". Kept
    as its own branch (and unit-tested directly) rather than removed, since
    it documents the intended meaning of "low" precisely and stays correct
    if eligibility rules ever change to include such candidates instead."""
    reasons = []
    core_implausible = False
    other_flagged = False
    for name in ("close_price", "living_area_sqft"):
        flag = candidate.field_flags.get(name)
        if flag and flag.status == FieldStatus.IMPLAUSIBLE:
            core_implausible = True
            reasons.append(f"{name} implausible: {flag.reason}")
    for name, flag in candidate.field_flags.items():
        if name in ("close_price", "living_area_sqft"):
            continue
        if flag.status != FieldStatus.PRESENT:
            other_flagged = True
            reasons.append(f"{name} {flag.status.value}" + (f": {flag.reason}" if flag.reason else ""))

    if core_implausible:
        return "low", reasons
    if other_flagged:
        return "medium", reasons
    return "high", reasons


def evaluate_candidates(
    subject: CanonicalProperty,
    candidates: list[CanonicalProperty],
    step: SearchStep,
    analysis_date: date,
) -> ComparableSearchResult:
    """Pure: filter candidates for eligibility, score and rank the eligible
    ones, select the top MIN..MAX, and explain every exclusion. Does not
    fetch anything and does not decide whether to try another step."""
    if subject.geo.lat is None or subject.geo.lng is None:
        raise ValueError("Subject property is missing coordinates; cannot evaluate comparables")

    excluded: list[Exclusion] = []
    scored: list[ScoredComparable] = []

    for candidate in candidates:
        eligible, reason, distance, days_before = _check_eligibility(subject, candidate, step, analysis_date)
        if not eligible:
            excluded.append(Exclusion(candidate=candidate, reason=reason))
            continue

        score, differences = _score_candidate(subject, candidate, distance, days_before, step)
        confidence, confidence_reasons = _confidence(candidate)
        price_per_sqft = None
        if candidate.transaction.close_price and candidate.characteristics.living_area_sqft:
            price_per_sqft = candidate.transaction.close_price / candidate.characteristics.living_area_sqft

        scored.append(ScoredComparable(
            candidate=candidate,
            distance_miles=distance,
            days_before_analysis=days_before,
            similarity_score=score,
            confidence=confidence,
            confidence_reasons=confidence_reasons,
            price_per_sqft=price_per_sqft,
            differences=differences,
        ))

    scored.sort(key=lambda sc: sc.similarity_score, reverse=True)
    selected = scored[:MAX_SELECTED]

    return ComparableSearchResult(
        step=step,
        analysis_date=analysis_date,
        candidates_considered=len(candidates),
        selected=selected,
        excluded=excluded,
        sufficient=len(selected) >= MIN_QUALIFIED,
    )


def fetch_and_evaluate(
    agent: PropertyDataAgent,
    subject: CanonicalProperty,
    step: SearchStep,
    analysis_date: date,
    provider_limit: int = 100,
    radius_safety_margin: float = 1.25,
) -> ComparableSearchResult:
    """Convenience wrapper implementing the plan's "Search behavior" split:
    ask the provider for a server-side-filtered pool (status/type/geo
    radius — a coarse prefilter, requested slightly larger than needed to
    absorb any provider/app distance-formula mismatch), then run the exact,
    deterministic eligibility/scoring/ranking locally via evaluate_candidates.
    """
    if subject.geo.lat is None or subject.geo.lng is None:
        raise ValueError("Subject property is missing coordinates; cannot search for comparables")

    result = agent.load_closed_sales(
        lat=subject.geo.lat,
        lng=subject.geo.lng,
        radius_km=miles_to_km(step.radius_miles * radius_safety_margin),
        property_type=subject.characteristics.property_type,
        limit=provider_limit,
    )
    return evaluate_candidates(subject, result.properties, step, analysis_date)
