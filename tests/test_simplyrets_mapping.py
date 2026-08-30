import json
import unittest

import _pathfix  # noqa: F401  (sets sys.path)
from simplyrets_mapping import map_simplyrets_listing


class TestMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads((_pathfix.FIXTURES / "single_property_sample.json").read_text())

    def test_maps_identity_and_address(self):
        prop = map_simplyrets_listing(self.raw)
        self.assertEqual(prop.source, "simplyrets")
        self.assertEqual(prop.source_listing_id, "1005192")
        self.assertEqual(prop.address.full, "74434 East Sweet Bottom Br #18393")
        self.assertEqual(prop.address.city, "Houston")
        self.assertEqual(prop.address.state, "Texas")
        self.assertEqual(prop.address.postal_code, "77096")

    def test_maps_geo(self):
        prop = map_simplyrets_listing(self.raw)
        self.assertAlmostEqual(prop.geo.lat, 29.689418)
        self.assertAlmostEqual(prop.geo.lng, -95.474464)
        self.assertEqual(prop.geo.county, "North")

    def test_maps_characteristics_including_lot_size_fallback(self):
        prop = map_simplyrets_listing(self.raw)
        self.assertEqual(prop.characteristics.property_type, "RES")
        self.assertIsNone(prop.characteristics.property_subtype)
        self.assertEqual(prop.characteristics.bedrooms, 2)
        self.assertEqual(prop.characteristics.baths_full, 5)
        self.assertEqual(prop.characteristics.baths_half, 6)
        self.assertEqual(prop.characteristics.living_area_sqft, 1043)
        self.assertEqual(prop.characteristics.year_built, 1998)
        # numeric lot size is absent on this record; text fallback is present
        self.assertIsNone(prop.characteristics.lot_size_area)
        self.assertEqual(prop.characteristics.lot_size_text, "127X146")

    def test_maps_transaction(self):
        prop = map_simplyrets_listing(self.raw)
        self.assertEqual(prop.transaction.status, "Active")
        self.assertEqual(prop.transaction.list_price, 20714261)
        self.assertEqual(prop.transaction.close_price, 17946033)
        self.assertEqual(prop.transaction.close_date, "1996-10-21T15:15:54.171139Z")

    def test_maps_attribution_and_retains_raw(self):
        prop = map_simplyrets_listing(self.raw)
        self.assertEqual(prop.attribution.disclaimer, self.raw["disclaimer"])
        self.assertIsNone(prop.attribution.internet_address_display)
        self.assertIs(prop.raw, self.raw)

    def test_mapping_never_raises_on_missing_nested_keys(self):
        sparse = {"mlsId": 42}
        prop = map_simplyrets_listing(sparse)
        self.assertEqual(prop.source_listing_id, "42")
        self.assertIsNone(prop.address.full)
        self.assertIsNone(prop.geo.lat)
        self.assertIsNone(prop.characteristics.bedrooms)
        self.assertIsNone(prop.transaction.close_price)


if __name__ == "__main__":
    unittest.main()
