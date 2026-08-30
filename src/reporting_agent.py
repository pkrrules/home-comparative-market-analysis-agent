"""Constrained OpenAI-backed narrative agent with deterministic fallback.

The model receives only verified, structured facts. Its output is additive:
the deterministic report, comparable set, confidence, and valuation are never
replaced. Narrative containing digits or currency symbols is rejected so the
model cannot introduce alternate measurements, prices, dates, or listing IDs.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from canonical_schema import CanonicalProperty
from comparable_engine import ComparableSearchResult
from report import calculate_valuation

DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class ReportingOutcome:
    narrative: str | None
    status: str
    model: str | None = None


def _extract_output_text(body: dict[str, Any]) -> str:
    """Support both the SDK convenience field and canonical REST shape."""
    if isinstance(body.get("output_text"), str) and body["output_text"]:
        return body["output_text"]
    texts: list[str] = []
    for item in body.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                value = content.get("text")
                if isinstance(value, str):
                    texts.append(value)
    if texts:
        return "".join(texts)
    status = body.get("status", "unknown")
    reason = (body.get("incomplete_details") or {}).get("reason")
    suffix = f" ({reason})" if reason else ""
    raise ValueError(f"OpenAI response contained no output text; status={status}{suffix}")


def _http_error_status(response: requests.Response) -> str:
    status = response.status_code
    try:
        error = response.json().get("error") or {}
        code = error.get("code") or error.get("type")
        message = error.get("message")
        detail = ": ".join(str(value) for value in (code, message) if value)
    except (ValueError, AttributeError):
        detail = ""
    return f"OpenAI HTTP {status}" + (f": {detail}" if detail else "")


def verified_reporting_facts(subject: CanonicalProperty, result: ComparableSearchResult) -> dict[str, Any]:
    valuation = calculate_valuation(subject, result.selected)
    return {
        "subject": {
            "property_type": subject.characteristics.property_type,
            "living_area_sqft": subject.characteristics.living_area_sqft,
            "bedrooms": subject.characteristics.bedrooms,
            "bathrooms_full": subject.characteristics.baths_full,
        },
        "approved_comparables": [
            {
                "distance_miles": round(sc.distance_miles, 2),
                "days_before_analysis": sc.days_before_analysis,
                "sale_price": sc.candidate.transaction.close_price,
                "living_area_sqft": sc.candidate.characteristics.living_area_sqft,
                "price_per_sqft": round(sc.price_per_sqft, 2) if sc.price_per_sqft else None,
                "similarity_score": round(sc.similarity_score, 3),
                "confidence": sc.confidence,
                "differences": sc.differences,
                "data_limitations": sc.confidence_reasons,
            }
            for sc in result.selected
        ],
        "deterministic_valuation": {
            "weighted_price_per_sqft": valuation.weighted_price_per_sqft,
            "median_price_per_sqft": valuation.median_price_per_sqft,
            "central_indication": valuation.point_estimate,
            "low_estimate": valuation.low_estimate,
            "high_estimate": valuation.high_estimate,
            "outlier_count": len(valuation.outlier_ids),
            "confidence": valuation.confidence,
        },
    }


class OpenAIReportingAgent:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 25):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_REPORT_MODEL", DEFAULT_MODEL)
        self.base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    def generate(self, subject: CanonicalProperty, result: ComparableSearchResult) -> ReportingOutcome:
        if not self.api_key:
            return ReportingOutcome(None, "deterministic fallback: OPENAI_API_KEY is not set")
        facts = verified_reporting_facts(subject, result)
        schema = {
            "type": "object",
            "properties": {
                "comparison_summary": {"type": "string"},
                "strengths": {"type": "string"},
                "limitations": {"type": "string"},
                "interpretation": {"type": "string"},
            },
            "required": ["comparison_summary", "strengths", "limitations", "interpretation"],
            "additionalProperties": False,
        }
        payload = {
            "model": self.model,
            "store": False,
            "max_output_tokens": 500,
            "instructions": (
                "You are a constrained real-estate reporting agent. Explain only the supplied verified facts. "
                "Do not calculate, estimate, recommend, add facts, name listing IDs, or change eligibility or confidence. "
                "Use qualitative prose only: do not emit digits, currency symbols, dates, measurements, or numeric words. "
                "A deterministic report displayed beside your narrative is the sole source of all numbers."
            ),
            "input": json.dumps(facts, sort_keys=True),
            "text": {"format": {"type": "json_schema", "name": "report_narrative", "strict": True, "schema": schema}},
        }
        try:
            response = requests.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            if not response.ok:
                return ReportingOutcome(None, f"deterministic fallback: {_http_error_status(response)}", self.model)
            body = response.json()
            data = json.loads(_extract_output_text(body))
            sections = [data[key].strip() for key in schema["required"]]
            narrative = "\n\n".join([
                "## AI-assisted evidence commentary",
                f"**Comparison summary.** {sections[0]}",
                f"**Evidence strengths.** {sections[1]}",
                f"**Evidence limitations.** {sections[2]}",
                f"**Interpretation.** {sections[3]}",
            ])
            if re.search(r"[\d$%]", narrative):
                raise ValueError("model narrative introduced prohibited numeric content")
            return ReportingOutcome(narrative, "AI narrative generated", self.model)
        except (requests.RequestException, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            detail = str(exc).strip()
            status = type(exc).__name__ + (f": {detail}" if detail else "")
            return ReportingOutcome(None, f"deterministic fallback: {status}", self.model)
