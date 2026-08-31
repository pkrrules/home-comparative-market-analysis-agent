import unittest
from dataclasses import replace

import _pathfix  # noqa: F401
from comparable_engine import MIN_QUALIFIED, SEARCH_EXPANSION_STEPS, evaluate_candidates
from data_agent import PropertyDataAgent
from demo_evaluation import DEMO_EVALUATION_CASES, DEMO_PRESET_EXPECTATIONS
from demo_subjects import DEMO_SUBJECTS
from repliers_fixture_provider import RepliersFixtureProvider
from repliers_mapping import map_repliers_listing
from report import ExpansionLogEntry, calculate_valuation, check_briefing, generate_briefing


class TestFrozenDemoEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = RepliersFixtureProvider()
        cls.agent = PropertyDataAgent(cls.provider, map_repliers_listing)
        cls.pool = cls.agent.load_closed_sales(property_type="Residential", limit=500).properties

    def test_ten_cases_match_full_traceable_contract(self):
        self.assertEqual(len(DEMO_EVALUATION_CASES), 10)
        coverage = set()
        for case in DEMO_EVALUATION_CASES:
            with self.subTest(subject=case["subject_id"]):
                coverage.update(case["coverage"])
                subject = self.agent.find_subject(case["subject_id"])
                if subject is None:
                    subject = next(p for p in self.pool if p.source_listing_id == case["subject_id"])
                path, approvals = [], []
                for index, step in enumerate(SEARCH_EXPANSION_STEPS):
                    result = evaluate_candidates(subject, self.pool, step, self.provider.analysis_date)
                    path.append(step.label)
                    if result.sufficient:
                        break
                    if index + 1 < len(SEARCH_EXPANSION_STEPS):
                        next_step = SEARCH_EXPANSION_STEPS[index + 1]
                        if next_step.max_age_days != step.max_age_days:
                            approvals.append(next_step.label)

                proposed_ids = [sc.candidate.source_listing_id for sc in result.selected]
                self.assertEqual(path, case["expected_path"])
                self.assertEqual(approvals, case["expected_approval_points"])
                self.assertEqual(proposed_ids, case["expected_proposed_ids"])

                approved = [sc for sc in result.selected if sc.candidate.source_listing_id in case["expected_approved_ids"]]
                result = replace(result, selected=approved, sufficient=len(approved) >= MIN_QUALIFIED)
                actual_inputs = [
                    (sc.candidate.source_listing_id, int(sc.candidate.transaction.close_price),
                     int(sc.candidate.characteristics.living_area_sqft), round(sc.similarity_score, 6), sc.confidence)
                    for sc in approved
                ]
                self.assertEqual(actual_inputs, case["expected_inputs"])

                valuation = calculate_valuation(subject, approved)
                actual_values = (valuation.weighted_price_per_sqft, valuation.median_price_per_sqft,
                                 valuation.low_estimate, valuation.high_estimate, valuation.point_estimate)
                for actual, expected in zip(actual_values, case["expected_valuation"]):
                    if expected is None:
                        self.assertIsNone(actual)
                    else:
                        self.assertAlmostEqual(actual, expected, places=5)
                self.assertEqual(valuation.confidence, case["expected_confidence"])

                log = [ExpansionLogEntry("step", label, 0, False) for label in path[:-1]]
                log.append(ExpansionLogEntry("step", path[-1], len(approved), result.sufficient))
                text, facts = generate_briefing(subject, self.provider.analysis_date, log, result)
                passed = all(item.startswith("PASS") for item in check_briefing(text, facts))
                self.assertEqual(passed, case["expected_briefing_checks_pass"])
                self.assertEqual(facts.selected_ids, case["expected_approved_ids"])
                self.assertIn(case["reviewer_status"], {"pending", "accepted", "rejected"})

        required = {"radius_expansion", "six_month_approval", "twelve_month_approval",
                    "insufficient_evidence", "missing_secondary_fields", "manual_rejection"}
        self.assertTrue(required <= coverage)

    def test_all_six_ui_presets_keep_expected_fixture_paths(self):
        self.assertEqual({item.mls_number for item in DEMO_SUBJECTS}, set(DEMO_PRESET_EXPECTATIONS))
        for preset in DEMO_SUBJECTS:
            with self.subTest(subject=preset.mls_number):
                subject = self.agent.find_subject(preset.mls_number)
                path, approvals = [], []
                for index, step in enumerate(SEARCH_EXPANSION_STEPS):
                    result = evaluate_candidates(subject, self.pool, step, self.provider.analysis_date)
                    path.append(step.label)
                    if result.sufficient:
                        break
                    if index + 1 < len(SEARCH_EXPANSION_STEPS):
                        next_step = SEARCH_EXPANSION_STEPS[index + 1]
                        if next_step.max_age_days != step.max_age_days:
                            approvals.append(next_step.label)
                expected_path, expected_approvals, expected_ids = DEMO_PRESET_EXPECTATIONS[preset.mls_number]
                self.assertEqual(path, expected_path)
                self.assertEqual(approvals, expected_approvals)
                self.assertEqual([sc.candidate.source_listing_id for sc in result.selected], expected_ids)


if __name__ == "__main__":
    unittest.main()
