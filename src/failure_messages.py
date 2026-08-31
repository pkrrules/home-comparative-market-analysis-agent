"""User-facing, provider-aware failure classification for the demo UI."""
from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class FailurePresentation:
    code: str
    title: str
    message: str
    can_retry: bool = True
    can_use_fixture: bool = True


def classify_failure(error: BaseException | str, context: str = "analysis") -> FailurePresentation:
    text = str(error)
    lowered = text.lower()
    status = getattr(error, "status_code", None)
    if "repliers_api_key" in lowered:
        return FailurePresentation("missing_api_key", "Live API key missing", "Add REPLIERS_API_KEY to .env, restart the app, or switch to the frozen demonstration dataset.", False)
    if status in {401, 403} or any(token in lowered for token in ("-> 401", "-> 403", "authentication failed")):
        return FailurePresentation("authentication", "Repliers authentication failed", "Check that REPLIERS_API_KEY is active and belongs to the expected Repliers account, then retry or use fixture mode.", False)
    if status == 429 or "429" in lowered or "rate limit" in lowered:
        return FailurePresentation("rate_limit", "Repliers rate limit reached", "Wait for the quota window to reset, then retry, or continue immediately with the frozen demonstration dataset.")
    if isinstance(error, requests.Timeout) or "timed out" in lowered or "timeout" in lowered:
        return FailurePresentation("timeout", "Live request timed out", "Retry the request. If the provider remains slow, switch to the frozen demonstration dataset.")
    if isinstance(error, requests.ConnectionError) or any(token in lowered for token in ("connection", "name resolution", "dns", "network")):
        return FailurePresentation("network", "Could not reach Repliers", "Check the network connection and retry, or switch to the frozen demonstration dataset.")
    if "checkpoint" in lowered or "resume" in lowered or context == "checkpoint":
        return FailurePresentation("checkpoint", "Saved workflow could not be resumed", "Start over to create a fresh workflow checkpoint. No property data was changed.", False, False)
    return FailurePresentation("unexpected", "Analysis could not be completed", f"Start over and retry. Technical detail: {text}")


def invalid_subject_message(identifier: str, missing: list[str] | None = None) -> FailurePresentation:
    if missing:
        fields = ", ".join(missing)
        return FailurePresentation("invalid_subject_data", "Subject data is incomplete", f"The subject is missing {fields}, so distance-based valuation cannot run. Choose another fixture subject or correct the live record.", False)
    return FailurePresentation("invalid_mls", "MLS number was not found", f"No Repliers sample record matched {identifier!r}. Check the exact MLS number or choose a preset subject.", False)
