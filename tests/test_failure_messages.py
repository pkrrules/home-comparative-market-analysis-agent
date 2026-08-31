import unittest

import requests
import _pathfix  # noqa: F401
from failure_messages import classify_failure, invalid_subject_message
from repliers_client import RepliersError


class TestFailureMessages(unittest.TestCase):
    def test_expected_live_failures_are_distinct(self):
        cases = [
            (RepliersError("REPLIERS_API_KEY is not set"), "missing_api_key"),
            (RepliersError("unauthorized", 401), "authentication"),
            (RepliersError("limited", 429), "rate_limit"),
            (requests.Timeout("slow"), "timeout"),
            (requests.ConnectionError("DNS name resolution"), "network"),
        ]
        for error, code in cases:
            with self.subTest(code=code):
                self.assertEqual(classify_failure(error).code, code)

    def test_checkpoint_failure_requires_fresh_start(self):
        failure = classify_failure(RuntimeError("missing thread"), "checkpoint")
        self.assertEqual(failure.code, "checkpoint")
        self.assertFalse(failure.can_use_fixture)

    def test_invalid_mls_and_missing_subject_fields_are_distinct(self):
        self.assertEqual(invalid_subject_message("BAD").code, "invalid_mls")
        self.assertEqual(invalid_subject_message("ID", ["coordinates"]).code, "invalid_subject_data")


if __name__ == "__main__":
    unittest.main()
