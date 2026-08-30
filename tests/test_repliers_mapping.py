import json
import unittest

import _pathfix  # noqa: F401
from repliers_mapping import map_repliers_listing


class TestRepliersMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads((_pathfix.FIXTURES / "repliers_single_listing_sample.json").read_text())

    def test_maps_identity_and_address(self):
        prop = map_repliers_listing(self.raw)
        self.assertEqual(prop.source, "repliers")
        self.assertEqual(prop.source_listing_id, self.raw["mlsNumber"])
        addr = self.raw["address"]
        self.assertIn(str(addr["streetNumber"]), prop.address.full)
        self.assertIn(addr["streetName"], prop.address.full)
        self.assertEqual(prop.address.city, addr["city"])
        self.assertEqual(prop.address.state, addr["state"])
        self.assertEqual(prop.address.postal_code, addr["zip"])

    def test_maps_geo(self):
        prop = map_repliers_listing(self.raw)
        self.assertAlmostEqual(prop.geo.lat, self.raw["map"]["latitude"])
        self.assertAlmostEqual(prop.geo.lng, self.raw["map"]["longitude"])
        self.assertEqual(prop.geo.county, self.raw["address"].get("area"))

    def test_maps_characteristics_casts_string_numerics(self):
        prop = map_repliers_listing(self.raw)
        details = self.raw["details"]
        # sqft/yearBuilt arrive as strings on the wire; mapping must cast them.
        if details.get("sqft"):
            self.assertIsInstance(prop.characteristics.living_area_sqft, float)
            self.assertEqual(prop.characteristics.living_area_sqft, float(details["sqft"]))
        if details.get("yearBuilt"):
            self.assertIsInstance(prop.characteristics.year_built, int)
            self.assertEqual(prop.characteristics.year_built, int(details["yearBuilt"]))
        self.assertEqual(prop.characteristics.property_type, details.get("propertyType"))
        self.assertEqual(prop.characteristics.property_subtype, self.raw.get("class"))

    def test_maps_lot_size_numeric(self):
        prop = map_repliers_listing(self.raw)
        lot = self.raw.get("lot", {})
        if lot.get("squareFeet") is not None:
            self.assertEqual(prop.characteristics.lot_size_area, float(lot["squareFeet"]))
            self.assertEqual(prop.characteristics.lot_size_units, "sqft")

    def test_maps_transaction(self):
        prop = map_repliers_listing(self.raw)
        self.assertEqual(prop.transaction.status, self.raw.get("standardStatus"))
        self.assertEqual(prop.transaction.list_price, float(self.raw["listPrice"]))
        self.assertEqual(prop.transaction.close_price, float(self.raw["soldPrice"]))
        self.assertEqual(prop.transaction.close_date, self.raw.get("soldDate"))

    def test_maps_attribution_yn_to_bool(self):
        prop = map_repliers_listing(self.raw)
        perms = self.raw.get("permissions", {})
        expected = perms.get("displayAddressOnInternet") == "Y"
        self.assertEqual(prop.attribution.internet_address_display, expected)

    def test_mapping_never_raises_on_missing_nested_keys(self):
        sparse = {"mlsNumber": "X1"}
        prop = map_repliers_listing(sparse)
        self.assertEqual(prop.source_listing_id, "X1")
        self.assertIsNone(prop.address.full)
        self.assertIsNone(prop.geo.lat)
        self.assertIsNone(prop.characteristics.bedrooms)
        self.assertIsNone(prop.transaction.close_price)

    def test_non_numeric_string_fields_do_not_raise(self):
        raw = {
            "mlsNumber": "X2",
            "details": {"sqft": "", "yearBuilt": None},
            "listPrice": None,
        }
        prop = map_repliers_listing(raw)
        self.assertIsNone(prop.characteristics.living_area_sqft)
        self.assertIsNone(prop.characteristics.year_built)


if __name__ == "__main__":
    unittest.main()
