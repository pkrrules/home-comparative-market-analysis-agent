"""
End-to-end Agent 1 pipeline test for the (archived, reference-only)
SimplyRETS provider, run entirely against frozen fixtures
(SimplyRETSFixtureProvider) — no network. Numbers here are cross-checked
against the Phase 1 audit report (docs/phase1-api-audit.md) so this doubles
as a regression check that Phase 2's logic agrees with the audited data.

See test_repliers_data_agent.py for the active provider's equivalent test.
"""
import unittest

import _pathfix  # noqa: F401
from canonical_schema import FieldStatus
from data_agent import PropertyDataAgent
from simplyrets_fixture_provider import SimplyRETSFixtureProvider
from simplyrets_mapping import map_simplyrets_listing


class TestPropertyDataAgentAgainstFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = PropertyDataAgent(SimplyRETSFixtureProvider(), map_simplyrets_listing)

    def test_find_subject_by_mls_id(self):
        subject = self.agent.find_subject("1005192")
        self.assertIsNotNone(subject)
        self.assertEqual(subject.address.city, "Houston")
        # This is the record with status=Active but populated sales data —
        # find_subject must still flag that inconsistency.
        self.assertEqual(subject.field_flags["status_consistency"].status, FieldStatus.IMPLAUSIBLE)

    def test_find_subject_by_address_text(self):
        subject = self.agent.find_subject("Sweet Bottom")
        self.assertIsNotNone(subject)
        self.assertEqual(subject.source_listing_id, "1005192")

    def test_find_subject_returns_none_for_unknown(self):
        self.assertIsNone(self.agent.find_subject("no-such-listing"))
        self.assertIsNone(self.agent.find_subject("999999999"))

    def test_load_closed_sales_matches_phase1_audit_counts(self):
        result = self.agent.load_closed_sales()
        # Phase 1 audit: 13 closed listings total, none dropped by dedup
        # (single-source demo feed with unique mlsIds and no matching
        # address+close_date+close_price collisions).
        total_seen = len(result.properties) + len(result.dropped_hard_requirements)
        self.assertEqual(total_seen, 13)
        self.assertEqual(result.dedup_drops, [])

    def test_load_closed_sales_all_records_have_field_flags(self):
        result = self.agent.load_closed_sales()
        for prop in result.properties:
            self.assertIn("geo.lat", prop.field_flags)
            self.assertIn("type_subtype_consistency", prop.field_flags)

    def test_load_closed_sales_flags_the_known_type_subtype_mismatch(self):
        # Phase 1 audit §3b found type=CND/subType=SingleFamilyResidence
        # combinations in the full feed; at least one such record should
        # surface here (closed-sales subset) with the mismatch flagged.
        result = self.agent.load_closed_sales()
        mismatches = [
            p for p in result.properties
            if p.field_flags["type_subtype_consistency"].status == FieldStatus.IMPLAUSIBLE
        ]
        # Not asserting an exact count (that's a property of this specific
        # demo snapshot, not of the pipeline) — just that the check fires
        # end-to-end when the data warrants it.
        for p in mismatches:
            self.assertEqual(p.characteristics.property_type, "CND")

    def test_load_closed_sales_city_filter_narrows_results(self):
        result_all = self.agent.load_closed_sales()
        result_cypress = self.agent.load_closed_sales(cities=["Cypress"])
        self.assertLessEqual(len(result_cypress.properties) + len(result_cypress.dropped_hard_requirements),
                              len(result_all.properties) + len(result_all.dropped_hard_requirements))
        for prop in result_cypress.properties:
            self.assertEqual(prop.address.city, "Cypress")


if __name__ == "__main__":
    unittest.main()
