import unittest

import _pathfix  # noqa: F401
from canonical_schema import (
    Address,
    Attribution,
    CanonicalProperty,
    Characteristics,
    FieldStatus,
    GeoLocation,
    Transaction,
)
from validation import HARD_REQUIRED_FIELDS, flag_fields, missing_hard_requirements


def make_property(**overrides) -> CanonicalProperty:
    """A fully-plausible baseline record; tests override one field at a time."""
    defaults = dict(
        source="simplyrets",
        source_listing_id="1",
        address=Address(full="1 Main St", city="Houston", state="Texas", postal_code="77001"),
        geo=GeoLocation(lat=29.76, lng=-95.36, county="Harris", market_area="Downtown"),
        characteristics=Characteristics(
            property_type="RES", property_subtype="SingleFamilyResidence",
            bedrooms=3, baths_full=2, baths_half=1,
            living_area_sqft=2000, lot_size_area=6000, lot_size_units="sqft",
            lot_size_text="6000 sqft", year_built=2005,
        ),
        transaction=Transaction(
            status="Closed", list_price=300_000, list_date="2013-06-01T00:00:00Z",
            close_price=295_000, close_date="2013-07-01T00:00:00Z", days_on_market=30,
        ),
        attribution=Attribution(disclaimer="ok"),
    )
    defaults.update(overrides)
    return CanonicalProperty(**defaults)


class TestPlausibleBaseline(unittest.TestCase):
    def test_fully_plausible_record_flags_everything_present(self):
        prop = make_property()
        flags = flag_fields(prop)
        for name, flag in flags.items():
            self.assertEqual(flag.status, FieldStatus.PRESENT, msg=f"{name}: {flag}")
        self.assertEqual(missing_hard_requirements(prop), [])


class TestMissingFields(unittest.TestCase):
    def test_missing_coordinates(self):
        prop = make_property(geo=GeoLocation(lat=None, lng=None))
        flags = flag_fields(prop)
        self.assertEqual(flags["geo.lat"].status, FieldStatus.MISSING)
        self.assertEqual(flags["geo.lng"].status, FieldStatus.MISSING)
        self.assertIn("geo.lat", missing_hard_requirements(prop))

    def test_missing_lot_size_falls_back_to_text_note(self):
        prop = make_property()
        prop.characteristics.lot_size_area = None
        prop.characteristics.lot_size_text = "irregular"
        flags = flag_fields(prop)
        self.assertEqual(flags["lot_size"].status, FieldStatus.MISSING)
        self.assertIn("fallback", flags["lot_size"].reason)

    def test_missing_lot_size_entirely(self):
        prop = make_property()
        prop.characteristics.lot_size_area = None
        prop.characteristics.lot_size_text = None
        flags = flag_fields(prop)
        self.assertEqual(flags["lot_size"].status, FieldStatus.MISSING)


class TestImplausibleFields(unittest.TestCase):
    def test_null_island_coordinates_are_implausible(self):
        prop = make_property(geo=GeoLocation(lat=0, lng=0))
        flags = flag_fields(prop)
        self.assertEqual(flags["geo.lat"].status, FieldStatus.IMPLAUSIBLE)

    def test_coordinates_outside_us_band_are_implausible(self):
        prop = make_property(geo=GeoLocation(lat=51.5, lng=-0.12))  # London
        flags = flag_fields(prop)
        self.assertEqual(flags["geo.lat"].status, FieldStatus.IMPLAUSIBLE)

    def test_negative_living_area_is_implausible(self):
        prop = make_property()
        prop.characteristics.living_area_sqft = -100
        flags = flag_fields(prop)
        self.assertEqual(flags["living_area_sqft"].status, FieldStatus.IMPLAUSIBLE)

    def test_year_built_in_the_future_is_implausible(self):
        prop = make_property()
        prop.characteristics.year_built = 3000
        flags = flag_fields(prop)
        self.assertEqual(flags["year_built"].status, FieldStatus.IMPLAUSIBLE)

    def test_close_price_wildly_above_list_price_is_implausible(self):
        prop = make_property()
        prop.transaction.list_price = 100_000
        prop.transaction.close_price = 900_000  # 9x
        flags = flag_fields(prop)
        self.assertEqual(flags["close_price"].status, FieldStatus.IMPLAUSIBLE)

    def test_close_price_moderately_above_list_price_is_plausible(self):
        # Phase 1 audit: mean close/list diff on the real trial feed was +81%.
        prop = make_property()
        prop.transaction.list_price = 100_000
        prop.transaction.close_price = 181_000
        flags = flag_fields(prop)
        self.assertEqual(flags["close_price"].status, FieldStatus.PRESENT)

    def test_type_subtype_mismatch_is_implausible(self):
        # Phase 1 audit §3b: CND + SingleFamilyResidence occurs in the real feed.
        prop = make_property()
        prop.characteristics.property_type = "CND"
        prop.characteristics.property_subtype = "SingleFamilyResidence"
        flags = flag_fields(prop)
        self.assertEqual(flags["type_subtype_consistency"].status, FieldStatus.IMPLAUSIBLE)

    def test_type_subtype_condominium_pair_is_plausible(self):
        prop = make_property()
        prop.characteristics.property_type = "CND"
        prop.characteristics.property_subtype = "Condominium"
        flags = flag_fields(prop)
        self.assertEqual(flags["type_subtype_consistency"].status, FieldStatus.PRESENT)

    def test_repliers_land_condoproperty_mismatch_is_implausible(self):
        # A "Land" listing (Repliers details.propertyType) tagged as a condo
        # unit (class=CondoProperty) is not a plausible combination.
        prop = make_property()
        prop.characteristics.property_type = "Land"
        prop.characteristics.property_subtype = "CondoProperty"
        flags = flag_fields(prop)
        self.assertEqual(flags["type_subtype_consistency"].status, FieldStatus.IMPLAUSIBLE)

    def test_repliers_land_residentialproperty_pair_is_plausible(self):
        prop = make_property()
        prop.characteristics.property_type = "Land"
        prop.characteristics.property_subtype = "ResidentialProperty"
        flags = flag_fields(prop)
        self.assertEqual(flags["type_subtype_consistency"].status, FieldStatus.PRESENT)

    def test_repliers_residential_type_has_no_subtype_constraint(self):
        prop = make_property()
        prop.characteristics.property_type = "Residential"
        prop.characteristics.property_subtype = "CondoProperty"
        flags = flag_fields(prop)
        self.assertEqual(flags["type_subtype_consistency"].status, FieldStatus.PRESENT)

    def test_active_status_with_populated_sales_data_is_implausible(self):
        # Phase 1 audit: fixtures/single_property_sample.json is exactly this case.
        prop = make_property()
        prop.transaction.status = "Active"
        flags = flag_fields(prop)
        self.assertEqual(flags["status_consistency"].status, FieldStatus.IMPLAUSIBLE)


class TestHardRequirements(unittest.TestCase):
    def test_all_hard_required_fields_are_tracked(self):
        prop = make_property()
        flag_fields(prop)
        for name in HARD_REQUIRED_FIELDS:
            self.assertIn(name, prop.field_flags)

    def test_missing_close_price_and_date_both_reported(self):
        prop = make_property()
        prop.transaction.close_price = None
        prop.transaction.close_date = None
        flag_fields(prop)
        problems = missing_hard_requirements(prop)
        self.assertIn("close_price", problems)
        self.assertIn("close_date", problems)


if __name__ == "__main__":
    unittest.main()
