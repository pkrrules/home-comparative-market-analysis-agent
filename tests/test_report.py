import unittest
from datetime import date, timedelta

import _pathfix  # noqa: F401
from canonical_schema import Address, Attribution, CanonicalProperty, Characteristics, GeoLocation, Transaction
from comparable_engine import SearchStep, evaluate_candidates
from report import ExpansionLogEntry, build_evidence_banner, calculate_valuation, check_briefing, generate_briefing
from validation import flag_fields

ANALYSIS_DATE = date(2026, 3, 1)
STEP = SearchStep(radius_miles=5, max_age_days=180, label="5 miles, 6 months")


def make_property(listing_id, lat=35.0, lng=-80.8, living_area=2000, close_price=300_000,
                   close_date="2026-02-01", disclaimer=None) -> CanonicalProperty:
    prop = CanonicalProperty(
        source="test",
        source_listing_id=listing_id,
        address=Address(full=f"{listing_id} Test St", city="Charlotte", state="NC", postal_code="28202"),
        geo=GeoLocation(lat=lat, lng=lng),
        characteristics=Characteristics(
            property_type="Residential", bedrooms=3, baths_full=2,
            living_area_sqft=living_area, lot_size_area=6000, lot_size_units="sqft", year_built=2005,
        ),
        transaction=Transaction(
            status="Closed", list_price=close_price * 0.98, close_price=close_price,
            close_date=close_date, list_date="2025-01-01",
        ),
        attribution=Attribution(disclaimer=disclaimer),
    )
    flag_fields(prop)
    return prop


class TestGenerateAndCheckBriefing(unittest.TestCase):
    def test_full_pipeline_all_checks_pass(self):
        subject = make_property("SUBJ", living_area=2000)
        candidates = [make_property(f"C{i}", close_price=250_000 + i * 10_000) for i in range(4)]
        result = evaluate_candidates(subject, candidates, STEP, ANALYSIS_DATE)
        log = [ExpansionLogEntry(kind="step", step_label=STEP.label, found=len(result.selected), sufficient=result.sufficient)]

        text, facts = generate_briefing(subject, ANALYSIS_DATE, log, result)
        checks = check_briefing(text, facts)

        self.assertTrue(all(c.startswith("PASS") for c in checks), checks)
        self.assertIn("SUBJ", text)
        self.assertEqual(len(facts.selected_ids), 4)

    def test_no_comparables_fallback_text(self):
        subject = make_property("SUBJ")
        result = evaluate_candidates(subject, [], STEP, ANALYSIS_DATE)
        log = [ExpansionLogEntry(kind="step", step_label=STEP.label, found=0, sufficient=False)]

        text, facts = generate_briefing(subject, ANALYSIS_DATE, log, result)
        checks = check_briefing(text, facts)

        self.assertTrue(all(c.startswith("PASS") for c in checks), checks)
        self.assertIn("No qualified comparables", text)
        self.assertIsNone(facts.point_estimate)

    def test_disclaimer_included_when_present(self):
        subject = make_property("SUBJ")
        c = make_property("C1", disclaimer="Sample disclaimer text.")
        result = evaluate_candidates(subject, [c], STEP, ANALYSIS_DATE)
        log = [ExpansionLogEntry(kind="step", step_label=STEP.label, found=1, sufficient=False)]
        text, _ = generate_briefing(subject, ANALYSIS_DATE, log, result)
        self.assertIn("Sample disclaimer text.", text)

    def test_expansion_log_approval_entries_rendered(self):
        subject = make_property("SUBJ")
        candidates = [make_property(f"C{i}") for i in range(3)]
        result = evaluate_candidates(subject, candidates, STEP, ANALYSIS_DATE)
        log = [
            ExpansionLogEntry(kind="step", step_label="3 miles, 90 days", found=0, sufficient=False),
            ExpansionLogEntry(kind="approval", step_label=STEP.label, decision="granted"),
            ExpansionLogEntry(kind="step", step_label=STEP.label, found=3, sufficient=True),
        ]
        text, _ = generate_briefing(subject, ANALYSIS_DATE, log, result)
        self.assertIn("approved by user", text)

    def test_exclusion_categories_summarized(self):
        subject = make_property("SUBJ")
        far = make_property("FAR", lat=36.5)  # far outside 5mi radius
        result = evaluate_candidates(subject, [far], STEP, ANALYSIS_DATE)
        log = [ExpansionLogEntry(kind="step", step_label=STEP.label, found=0, sufficient=False)]
        text, _ = generate_briefing(subject, ANALYSIS_DATE, log, result)
        self.assertIn("outside search radius", text)


class TestRobustValuation(unittest.TestCase):
    def test_obvious_ppsf_outlier_is_flagged_and_excluded(self):
        subject = make_property("SUBJ", living_area=2000)
        candidates = [
            make_property("C100", living_area=2000, close_price=200_000),
            make_property("C105", living_area=2000, close_price=210_000),
            make_property("C110", living_area=2000, close_price=220_000),
            make_property("OUTLIER", living_area=2000, close_price=2_000_000),
        ]
        result = evaluate_candidates(subject, candidates, STEP, ANALYSIS_DATE)
        valuation = calculate_valuation(subject, result.selected)

        self.assertEqual(valuation.outlier_ids, ["OUTLIER"])
        self.assertAlmostEqual(valuation.weighted_price_per_sqft, 105.0)
        self.assertAlmostEqual(valuation.point_estimate, 210_000.0)
        self.assertEqual(valuation.confidence, "medium")

    def test_evidence_banner_tracks_valuation_confidence(self):
        subject = make_property("SUBJ")
        high_candidates = [make_property(f"H{i}") for i in range(3)]
        for candidate in high_candidates:
            candidate.characteristics.baths_half = 0
            flag_fields(candidate)
        high_result = evaluate_candidates(subject, high_candidates, STEP, ANALYSIS_DATE)
        low_result = evaluate_candidates(subject, [make_property("ONLY")], STEP, ANALYSIS_DATE)
        self.assertEqual(build_evidence_banner(subject, high_result.selected).level, "high")
        self.assertEqual(build_evidence_banner(subject, low_result.selected).level, "low")


if __name__ == "__main__":
    unittest.main()
