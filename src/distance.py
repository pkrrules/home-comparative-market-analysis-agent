"""
Great-circle distance, in miles. Deterministic, provider-agnostic — this is
the exact-distance calculation the project plan insists on doing in the
app itself, never trusting a provider's own "radius" semantics (see
provider.py / docs/phase2b-repliers-migration.md: Repliers' radius search
genuinely filters, but the app still enforces the final cutoff itself).
"""
from __future__ import annotations

import math

EARTH_RADIUS_MILES = 3958.8
MILES_PER_KM = 0.621371


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_MILES * c


def miles_to_km(miles: float) -> float:
    return miles / MILES_PER_KM
