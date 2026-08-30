import unittest

import _pathfix  # noqa: F401
from canonical_schema import Address, CanonicalProperty, FieldFlag, FieldStatus, Transaction
from dedup import deduplicate


def make(listing_id, address_full, close_date, close_price, n_present_flags=5):
    prop = CanonicalProperty(
        source="simplyrets",
        source_listing_id=listing_id,
        address=Address(full=address_full),
        transaction=Transaction(close_date=close_date, close_price=close_price),
    )
    prop.field_flags = {f"f{i}": FieldFlag(FieldStatus.PRESENT) for i in range(n_present_flags)}
    return prop


class TestExactIdDuplicates(unittest.TestCase):
    def test_exact_duplicate_ids_collapse_to_one(self):
        a = make("1", "1 Main St", "2013-01-01", 100_000)
        b = make("1", "1 Main St", "2013-01-01", 100_000)
        result, drops = deduplicate([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(drops), 1)
        self.assertIn("exact duplicate", drops[0].reason)


class TestAddressTransactionDuplicates(unittest.TestCase):
    def test_same_address_and_sale_under_different_ids_collapses(self):
        a = make("1", "123 Oak Lane", "2013-05-01", 250_000)
        b = make("2", "123   OAK   lane", "2013-05-01", 250_000)  # normalized-equal address
        result, drops = deduplicate([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(drops), 1)

    def test_keeps_the_more_complete_record(self):
        weak = make("1", "5 Elm St", "2013-05-01", 250_000, n_present_flags=2)
        strong = make("2", "5 Elm St", "2013-05-01", 250_000, n_present_flags=8)
        result, drops = deduplicate([weak, strong])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_listing_id, "2")
        self.assertEqual(drops[0].dropped_id, "1")
        self.assertEqual(drops[0].kept_id, "2")

    def test_different_close_price_is_not_treated_as_duplicate(self):
        a = make("1", "9 Pine Rd", "2013-05-01", 250_000)
        b = make("2", "9 Pine Rd", "2013-05-01", 260_000)  # different sale
        result, drops = deduplicate([a, b])
        self.assertEqual(len(result), 2)
        self.assertEqual(len(drops), 0)

    def test_missing_signal_fields_never_falsely_collapsed(self):
        a = make("1", None, None, None)
        b = make("2", None, None, None)
        result, drops = deduplicate([a, b])
        self.assertEqual(len(result), 2)
        self.assertEqual(len(drops), 0)

    def test_no_duplicates_returns_all_records_unchanged(self):
        a = make("1", "1 A St", "2013-01-01", 100_000)
        b = make("2", "2 B St", "2013-02-01", 200_000)
        c = make("3", "3 C St", "2013-03-01", 300_000)
        result, drops = deduplicate([a, b, c])
        self.assertEqual(len(result), 3)
        self.assertEqual(len(drops), 0)


if __name__ == "__main__":
    unittest.main()
