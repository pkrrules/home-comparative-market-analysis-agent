import unittest

import _pathfix  # noqa: F401
from distance import haversine_miles, miles_to_km


class TestHaversineMiles(unittest.TestCase):
    def test_same_point_is_zero(self):
        self.assertAlmostEqual(haversine_miles(29.76, -95.36, 29.76, -95.36), 0.0, places=6)

    def test_known_long_distance_nyc_to_la(self):
        # NYC (40.7128, -74.0060) to LA (34.0522, -118.2437): real-world
        # great-circle distance is ~2,451 miles.
        d = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)
        self.assertAlmostEqual(d, 2451, delta=15)

    def test_one_degree_latitude_is_about_69_miles(self):
        d = haversine_miles(30.0, -95.0, 31.0, -95.0)
        self.assertAlmostEqual(d, 69, delta=1)

    def test_symmetric(self):
        d1 = haversine_miles(29.76, -95.36, 30.10, -95.10)
        d2 = haversine_miles(30.10, -95.10, 29.76, -95.36)
        self.assertAlmostEqual(d1, d2, places=9)

    def test_tiny_distance_is_small_but_nonzero(self):
        # ~0.01 degree lng at this latitude is roughly 0.6 miles
        d = haversine_miles(35.0, -80.0, 35.0, -80.01)
        self.assertGreater(d, 0)
        self.assertLess(d, 1)


class TestMilesToKm(unittest.TestCase):
    def test_conversion(self):
        self.assertAlmostEqual(miles_to_km(1.0), 1.60934, places=4)
        self.assertAlmostEqual(miles_to_km(0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
