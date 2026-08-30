"""
End-to-end Agent 1 pipeline test for the active provider (Repliers), run
entirely against frozen fixtures (RepliersFixtureProvider) — no network.
Cross-checked against docs/phase1-repliers-audit.md.
"""
import unittest

import _pathfix  # noqa: F401
from canonical_schema import FieldStatus
from data_agent import PropertyDataAgent
from repliers_fixture_provider import RepliersFixtureProvider
from repliers_mapping import map_repliers_listing


class TestPropertyDataAgentAgainstRepliersFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = PropertyDataAgent(RepliersFixtureProvider(), map_repliers_listing)

    def test_find_subject_by_mls_number(self):
        # The picker shortlist in docs/phase1-repliers-audit.md §10 — live-validated at audit time.
        subject = self.agent.find_subject("CAR3006094")
        self.assertIsNotNone(subject)
        self.assertEqual(subject.address.city, "Charlotte")
        self.assertEqual(subject.address.state, "NC")

    def test_find_subject_returns_none_for_unknown(self):
        self.assertIsNone(self.agent.find_subject("no-such-listing"))

    def test_load_closed_sales_returns_records_with_flags(self):
        result = self.agent.load_closed_sales(property_type="Residential", limit=500)
        self.assertGreater(len(result.properties), 0)
        for prop in result.properties:
            self.assertIn("geo.lat", prop.field_flags)
            self.assertIn("type_subtype_consistency", prop.field_flags)
            self.assertEqual(prop.source, "repliers")

    def test_load_closed_sales_dedupes_broad_and_city_sample_overlap(self):
        # RepliersFixtureProvider's own two frozen samples overlap on
        # top-of-index Charlotte records (see its docstring / the audit
        # script's finding) — confirm no duplicate listing ids survive.
        result = self.agent.load_closed_sales(property_type="Residential", limit=500)
        ids = [p.source_listing_id for p in result.properties]
        self.assertEqual(len(ids), len(set(ids)))

    def test_load_closed_sales_city_filter_narrows_results(self):
        result_all = self.agent.load_closed_sales(property_type="Residential", limit=500)
        result_charlotte = self.agent.load_closed_sales(
            cities=["Charlotte"], property_type="Residential", limit=500
        )
        self.assertLess(len(result_charlotte.properties), len(result_all.properties))
        for prop in result_charlotte.properties:
            self.assertEqual(prop.address.city, "Charlotte")

    def test_load_closed_sales_property_type_filter(self):
        result = self.agent.load_closed_sales(property_type="Residential", limit=500)
        for prop in result.properties:
            self.assertEqual(prop.characteristics.property_type, "Residential")

    def test_hard_required_fields_present_on_most_records(self):
        # Phase 1 (Repliers) audit §4: close_date/close_price/coordinates are
        # 100% populated in the sampled data, so almost nothing should be
        # dropped for missing hard requirements.
        result = self.agent.load_closed_sales(property_type="Residential", limit=500)
        total = len(result.properties) + len(result.dropped_hard_requirements)
        self.assertGreater(total, 0)
        drop_rate = len(result.dropped_hard_requirements) / total
        self.assertLess(drop_rate, 0.1)


if __name__ == "__main__":
    unittest.main()
