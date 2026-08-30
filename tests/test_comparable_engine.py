import unittest
from datetime import date, timedelta

import _pathfix  # noqa: F401
from canonical_schema import (
    Address,
    CanonicalProperty,
    Characteristics,
    GeoLocation,
    Transaction,
)
from comparable_engine import SearchStep, evaluate_candidates, _confidence
from validation import flag_fields

ANALYSIS_DATE = date(2026, 3, 1)
STEP = SearchStep(radius_miles=3, max_age_days=90, label="test step")

SUBJECT_LAT, SUBJECT_LNG = 35.0, -80.8
MILES_PER_DEG_LAT = 69.0


def make_property(
    listing_id="SUBJ1",
    lat=SUBJECT_LAT, lng=SUBJECT_LNG,
    status="Closed", property_type="Residential",
    living_area=2000, bedrooms=3, baths_full=2, baths_half=0, year_built=2005,
    list_price=300_000, close_price=295_000, close_date=None,
    lot_size_area=6000,
) -> CanonicalProperty:
    prop = CanonicalProperty(
        source="test",
        source_listing_id=listing_id,
        address=Address(full=f"{listing_id} Test St", city="Charlotte", state="NC", postal_code="28202"),
        geo=GeoLocation(lat=lat, lng=lng, county="Mecklenburg", market_area="Uptown"),
        characteristics=Characteristics(
            property_type=property_type, property_subtype="ResidentialProperty",
            bedrooms=bedrooms, baths_full=baths_full, baths_half=baths_half,
            living_area_sqft=living_area, lot_size_area=lot_size_area, lot_size_units="sqft",
            lot_size_text=f"{lot_size_area} sqft", year_built=year_built,
        ),
        transaction=Transaction(
            status=status, list_price=list_price, list_date="2025-01-01",
            close_price=close_price, close_date=close_date, days_on_market=30,
        ),
    )
    flag_fields(prop)
    return prop


def lat_for_miles(miles: float) -> float:
    return SUBJECT_LAT + miles / MILES_PER_DEG_LAT


def days_ago(n: int) -> str:
    return (ANALYSIS_DATE - timedelta(days=n)).isoformat()


class TestEligibilityExclusions(unittest.TestCase):
    def setUp(self):
        self.subject = make_property(close_date=None)  # subject's own close_date is irrelevant

    def test_subject_itself_is_excluded(self):
        result = evaluate_candidates(self.subject, [self.subject], STEP, ANALYSIS_DATE)
        self.assertEqual(len(result.selected), 0)
        self.assertEqual(len(result.excluded), 1)
        self.assertIn("subject property itself", result.excluded[0].reason)

    def test_non_closed_status_excluded(self):
        c = make_property(listing_id="C1", status="Active", close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertEqual(len(result.selected), 0)
        self.assertIn("Not a closed sale", result.excluded[0].reason)

    def test_missing_coordinates_excluded(self):
        c = make_property(listing_id="C2", lat=None, lng=None, close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertIn("Missing coordinates", result.excluded[0].reason)

    def test_out_of_radius_excluded_with_distance_reported(self):
        c = make_property(listing_id="C3", lat=lat_for_miles(10), close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertEqual(len(result.selected), 0)
        self.assertIn("exceeds the 3 mi search radius", result.excluded[0].reason)

    def test_outside_date_window_excluded(self):
        c = make_property(listing_id="C4", close_date=days_ago(200))
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertIn("outside the 90-day window", result.excluded[0].reason)

    def test_closed_after_analysis_date_excluded(self):
        c = make_property(listing_id="C5", close_date=(ANALYSIS_DATE + timedelta(days=5)).isoformat())
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertIn("after the analysis date", result.excluded[0].reason)

    def test_property_type_mismatch_excluded(self):
        c = make_property(listing_id="C6", property_type="Land", close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertIn("Property type mismatch", result.excluded[0].reason)

    def test_implausible_close_price_excluded(self):
        c = make_property(listing_id="C7", list_price=100_000, close_price=999_999, close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertIn("Sale price fails plausibility check", result.excluded[0].reason)

    def test_implausible_living_area_excluded(self):
        c = make_property(listing_id="C8", living_area=-100, close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertIn("Living area fails plausibility check", result.excluded[0].reason)

    def test_subject_missing_coordinates_raises(self):
        subject_no_geo = make_property(lat=None, lng=None)
        with self.assertRaises(ValueError):
            evaluate_candidates(subject_no_geo, [], STEP, ANALYSIS_DATE)


class TestScoringAndRanking(unittest.TestCase):
    def setUp(self):
        self.subject = make_property()

    def test_closer_and_more_similar_ranks_first(self):
        close_match = make_property(
            listing_id="CLOSE", lat=lat_for_miles(0.5), close_date=days_ago(10),
            living_area=2000, bedrooms=3, baths_full=2,
        )
        farther_less_similar = make_property(
            listing_id="FAR", lat=lat_for_miles(2.5), close_date=days_ago(80),
            living_area=2500, bedrooms=4, baths_full=3,
        )
        result = evaluate_candidates(self.subject, [farther_less_similar, close_match], STEP, ANALYSIS_DATE)
        self.assertEqual(len(result.selected), 2)
        self.assertEqual(result.selected[0].candidate.source_listing_id, "CLOSE")
        self.assertGreater(result.selected[0].similarity_score, result.selected[1].similarity_score)

    def test_differences_are_reported_in_human_readable_form(self):
        bigger = make_property(listing_id="BIG", living_area=2600, bedrooms=4, close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [bigger], STEP, ANALYSIS_DATE)
        sc = result.selected[0]
        self.assertTrue(any("sqft larger" in d for d in sc.differences))
        self.assertTrue(any("more bedroom" in d for d in sc.differences))

    def test_identical_twin_scores_near_perfect(self):
        twin = make_property(listing_id="TWIN", close_date=days_ago(1))
        result = evaluate_candidates(self.subject, [twin], STEP, ANALYSIS_DATE)
        self.assertGreater(result.selected[0].similarity_score, 0.9)

    def test_price_per_sqft_computed(self):
        c = make_property(listing_id="PPS", close_price=300_000, living_area=1500, close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertAlmostEqual(result.selected[0].price_per_sqft, 200.0)


class TestConfidence(unittest.TestCase):
    def setUp(self):
        self.subject = make_property()

    def test_fully_plausible_candidate_is_high_confidence(self):
        c = make_property(listing_id="HI", close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertEqual(result.selected[0].confidence, "high")

    def test_missing_secondary_field_is_medium_confidence(self):
        c = make_property(listing_id="MED", close_date=days_ago(10))
        c.characteristics.bedrooms = None
        flag_fields(c)
        result = evaluate_candidates(self.subject, [c], STEP, ANALYSIS_DATE)
        self.assertEqual(result.selected[0].confidence, "medium")
        self.assertTrue(any("bedrooms" in r for r in result.selected[0].confidence_reasons))

    def test_confidence_function_low_branch_directly(self):
        # Documents the "low" branch's meaning even though evaluate_candidates
        # never reaches it in practice (see comparable_engine.py docstring):
        # eligibility excludes implausible close_price/living_area outright.
        c = make_property(listing_id="LOW", living_area=-1)
        confidence, reasons = _confidence(c)
        self.assertEqual(confidence, "low")
        self.assertTrue(any("living_area_sqft" in r for r in reasons))


class TestSelectionLimits(unittest.TestCase):
    def setUp(self):
        self.subject = make_property()

    def test_insufficient_results_flagged_not_sufficient(self):
        c1 = make_property(listing_id="ONLY1", close_date=days_ago(10))
        result = evaluate_candidates(self.subject, [c1], STEP, ANALYSIS_DATE)
        self.assertFalse(result.sufficient)
        self.assertEqual(len(result.selected), 1)

    def test_three_eligible_is_sufficient(self):
        candidates = [make_property(listing_id=f"C{i}", close_date=days_ago(10)) for i in range(3)]
        result = evaluate_candidates(self.subject, candidates, STEP, ANALYSIS_DATE)
        self.assertTrue(result.sufficient)
        self.assertEqual(len(result.selected), 3)

    def test_selection_capped_at_ten(self):
        candidates = [make_property(listing_id=f"C{i}", close_date=days_ago(10)) for i in range(15)]
        result = evaluate_candidates(self.subject, candidates, STEP, ANALYSIS_DATE)
        self.assertEqual(len(result.selected), 10)
        self.assertEqual(len(result.excluded), 0)  # none were ineligible, just not selected
        self.assertEqual(result.candidates_considered, 15)


if __name__ == "__main__":
    unittest.main()
