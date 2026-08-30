import unittest

import _pathfix  # noqa: F401
from comparable_engine import SEARCH_EXPANSION_STEPS, evaluate_candidates
from data_agent import PropertyDataAgent
from demo_evaluation import DEMO_EVALUATION_CASES
from repliers_fixture_provider import RepliersFixtureProvider
from repliers_mapping import map_repliers_listing


class TestFrozenDemoEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = RepliersFixtureProvider()
        cls.agent = PropertyDataAgent(cls.provider, map_repliers_listing)
        cls.pool = cls.agent.load_closed_sales(property_type="Residential", limit=500).properties

    def test_ten_cases_keep_their_expected_paths_and_ids(self):
        self.assertEqual(len(DEMO_EVALUATION_CASES), 10)
        for case in DEMO_EVALUATION_CASES:
            with self.subTest(subject=case["subject_id"]):
                subject = self.agent.find_subject(case["subject_id"])
                if subject is None:
                    subject = next(p for p in self.pool if p.source_listing_id == case["subject_id"])
                reached_step = None
                selected_ids = []
                for index, step in enumerate(SEARCH_EXPANSION_STEPS):
                    result = evaluate_candidates(subject, self.pool, step, self.provider.analysis_date)
                    if result.sufficient:
                        reached_step = index
                        selected_ids = [sc.candidate.source_listing_id for sc in result.selected]
                        break
                self.assertEqual(reached_step, case["expected_step"])
                self.assertEqual(selected_ids, case["expected_ids"])


if __name__ == "__main__":
    unittest.main()
