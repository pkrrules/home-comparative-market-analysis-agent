import unittest
from datetime import date

import _pathfix  # noqa: F401
from canonical_schema import Address, Attribution, CanonicalProperty, Characteristics, GeoLocation, Transaction
from comparable_engine import SEARCH_EXPANSION_STEPS
from data_agent import PropertyDataAgent
from orchestrator import build_expansion_question, build_graph, run_interactive
from provider import PropertyDataProvider
from validation import flag_fields

ANALYSIS_DATE = date(2026, 3, 1)
SUBJECT_LAT, SUBJECT_LNG = 35.0, -80.8
MILES_PER_DEG_LAT = 69.0


def make_property(listing_id, lat=SUBJECT_LAT, close_date="2026-02-20") -> CanonicalProperty:
    prop = CanonicalProperty(
        source="test", source_listing_id=listing_id,
        address=Address(full=f"{listing_id} St", city="Charlotte", state="NC", postal_code="28202"),
        geo=GeoLocation(lat=lat, lng=SUBJECT_LNG),
        characteristics=Characteristics(
            property_type="Residential", bedrooms=3, baths_full=2,
            living_area_sqft=2000, lot_size_area=6000, lot_size_units="sqft", year_built=2005,
        ),
        transaction=Transaction(status="Closed", list_price=294_000, close_price=300_000, close_date=close_date),
        attribution=Attribution(),
    )
    flag_fields(prop)
    return prop


def lat_for_miles(miles: float) -> float:
    return SUBJECT_LAT + miles / MILES_PER_DEG_LAT


class FakeProvider(PropertyDataProvider):
    """Ignores all server-side filter params (like RepliersFixtureProvider
    does for geo) — evaluate_candidates does the real filtering, which is
    exactly what these tests want to exercise."""

    def __init__(self, subject: CanonicalProperty, candidates: list[CanonicalProperty]):
        self._subject = subject
        self._candidates = candidates

    def find_subject(self, identifier):
        return self._subject if identifier == self._subject.source_listing_id else None

    def search_closed_sales(self, **kwargs):
        return self._candidates

    def get_feed_metadata(self):
        return {}


def identity_map(raw):
    return raw  # FakeProvider already returns CanonicalProperty objects


class TestSufficientAtFirstStep(unittest.TestCase):
    def test_no_interrupt_needed_when_first_step_is_sufficient(self):
        subject = make_property("SUBJ")
        candidates = [make_property(f"C{i}", lat=lat_for_miles(1)) for i in range(3)]
        agent = PropertyDataAgent(FakeProvider(subject, candidates), identity_map)
        graph = build_graph(agent, provider_limit=100)

        def fail_if_called(_payload):
            raise AssertionError("approval should not be requested when step 1 is sufficient")

        final = run_interactive(graph, "t-sufficient", "SUBJ", ANALYSIS_DATE, fail_if_called)
        self.assertEqual(final["status"], "done")
        self.assertEqual(len(final["last_result"].selected), 3)
        self.assertTrue(final["last_result"].sufficient)
        self.assertEqual(len(final["expansion_log"]), 1)


class TestExpansionApproved(unittest.TestCase):
    def test_radius_expansion_unlocks_enough_comparables(self):
        subject = make_property("SUBJ")
        # Outside 3mi (step 1) but inside 5mi (step 2)
        candidates = [make_property(f"C{i}", lat=lat_for_miles(4)) for i in range(3)]
        agent = PropertyDataAgent(FakeProvider(subject, candidates), identity_map)
        graph = build_graph(agent, provider_limit=100)

        questions = []

        def approve(payload):
            questions.append(payload["question"])
            return True

        final = run_interactive(graph, "t-radius", "SUBJ", ANALYSIS_DATE, approve)
        self.assertEqual(final["status"], "done")
        self.assertTrue(final["last_result"].sufficient)
        self.assertEqual(len(questions), 1)
        self.assertIn("5 miles", questions[0])
        self.assertIn("within 3 miles and 90 days", questions[0])

    def test_date_expansion_wording_mentions_months(self):
        subject = make_property("SUBJ")
        # Inside 5mi but only qualifies once the window reaches 6 months
        candidates = [make_property(f"C{i}", lat=lat_for_miles(1), close_date="2025-10-01") for i in range(3)]
        agent = PropertyDataAgent(FakeProvider(subject, candidates), identity_map)
        graph = build_graph(agent, provider_limit=100)

        questions = []

        def approve(payload):
            questions.append(payload["question"])
            return True

        final = run_interactive(graph, "t-date", "SUBJ", ANALYSIS_DATE, approve)
        self.assertTrue(final["last_result"].sufficient)
        self.assertTrue(any("six months" in q for q in questions))


class TestDeclined(unittest.TestCase):
    def test_declining_expansion_stops_with_insufficient_result(self):
        subject = make_property("SUBJ")
        candidates = [make_property(f"C{i}", lat=lat_for_miles(4)) for i in range(3)]
        agent = PropertyDataAgent(FakeProvider(subject, candidates), identity_map)
        graph = build_graph(agent, provider_limit=100)

        final = run_interactive(graph, "t-decline", "SUBJ", ANALYSIS_DATE, lambda payload: False)
        # "status" tracks overall graph completion (ends "done" once a
        # briefing is generated, regardless of why); the decline itself is
        # recorded faithfully in expansion_log, checked below.
        self.assertEqual(final["status"], "done")
        self.assertFalse(final["last_result"].sufficient)
        self.assertEqual(len(final["last_result"].selected), 0)
        self.assertEqual(final["expansion_log"][-1].decision, "declined")


class TestExhausted(unittest.TestCase):
    def test_all_steps_tried_and_still_insufficient_terminates(self):
        subject = make_property("SUBJ")
        agent = PropertyDataAgent(FakeProvider(subject, []), identity_map)  # no candidates at all
        graph = build_graph(agent, provider_limit=100)

        approvals = []

        def approve(payload):
            approvals.append(payload)
            return True

        final = run_interactive(graph, "t-exhausted", "SUBJ", ANALYSIS_DATE, approve)
        self.assertEqual(final["status"], "done")
        self.assertFalse(final["last_result"].sufficient)
        # One approval request between each of the 4 steps -> 3 approvals total
        self.assertEqual(len(approvals), len(SEARCH_EXPANSION_STEPS) - 1)
        step_entries = [e for e in final["expansion_log"] if e.kind == "step"]
        self.assertEqual(len(step_entries), len(SEARCH_EXPANSION_STEPS))
        self.assertIn("No qualified comparables", final["briefing"])


class TestUnknownSubject(unittest.TestCase):
    def test_unknown_subject_short_circuits_to_briefing(self):
        subject = make_property("SUBJ")
        agent = PropertyDataAgent(FakeProvider(subject, []), identity_map)
        graph = build_graph(agent)

        final = run_interactive(graph, "t-unknown", "NOT-SUBJ", ANALYSIS_DATE, lambda p: True)
        self.assertEqual(final["status"], "no_subject")
        self.assertIsNone(final["briefing_facts"])
        self.assertIn("No subject property could be resolved", final["briefing"])
        self.assertEqual(final["briefing_checks"], [])


class TestExpansionQuestionWording(unittest.TestCase):
    def test_radius_step_question(self):
        from comparable_engine import ComparableSearchResult, SearchStep
        result = ComparableSearchResult(
            step=SearchStep(3, 90, "3 miles, 90 days"), analysis_date=ANALYSIS_DATE,
            candidates_considered=5, selected=[], excluded=[], sufficient=False,
        )
        q = build_expansion_question(result, SearchStep(5, 90, "5 miles, 90 days"))
        self.assertEqual(
            q,
            "Only 0 qualified comparables were found within 3 miles and 90 days of the "
            "demonstration analysis date. May the search expand to 5 miles?",
        )

    def test_singular_comparable_wording(self):
        from comparable_engine import ComparableSearchResult, ScoredComparable, SearchStep
        fake_selected = [object()]  # only len() is used
        result = ComparableSearchResult(
            step=SearchStep(3, 90, "3 miles, 90 days"), analysis_date=ANALYSIS_DATE,
            candidates_considered=5, selected=fake_selected, excluded=[], sufficient=False,
        )
        q = build_expansion_question(result, SearchStep(5, 90, "5 miles, 90 days"))
        self.assertIn("1 qualified comparable was found", q)


if __name__ == "__main__":
    unittest.main()
