"""
Curated "Try an example" subject properties for the Streamlit demo UI.

Per the project plan's own recommendation: let users pick from known demo
properties rather than free-text address search — reinforced by Phase 2b's
finding that Repliers' address/text search is unreliable in practice.
These specific MLS numbers were live-validated (a real GET
/listings/{mlsNumber} call succeeded, not just search-result presence —
see Phase 2b's note that the two don't always agree) at the time of the
Phase 1 (Repliers) migration audit; see docs/phase1-repliers-audit.md §10.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoSubject:
    mls_number: str
    label: str


DEMO_SUBJECTS: list[DemoSubject] = [
    DemoSubject("CAR3638662", "8107 Hudson Forest Drive Unit 45, Charlotte, NC — closed 2025-08-19, $244,640"),
    DemoSubject("CAR3006094", "447 Wonderwood Drive, Charlotte, NC — closed 2024-05-18, $756,500"),
    DemoSubject("CAR3638442", "15131 Cimarron Hills Lane Unit PME146, Charlotte, NC — closed 2025-07-29, $533,699"),
    DemoSubject("CAR4177999", "3619 Maple Glenn Lane, Charlotte, NC — closed 2024-09-21, $299,900"),
    DemoSubject("CAR4197739", "1417 Collier Walk Alley Unit CSW0207, Charlotte, NC — closed 2025-07-13, $569,950"),
    DemoSubject("CAR4214421", "9500 Big Cone Place, Charlotte, NC — closed 2025-07-06, $275,000"),
]
