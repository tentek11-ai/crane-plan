import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "05_src"))

from crane_plan.normative import (  # noqa: E402
    NormativeInputError,
    danger_zone_offset_from_outer_edge,
    fall_distance,
    required_hook_height,
    validate_joint_crane_clearances,
    validate_joint_crane_parking_clearances,
)


class FallDistanceTests(unittest.TestCase):
    def test_first_interval_uses_first_table_value(self):
        self.assertEqual(fall_distance(5, "moved_load"), 4.0)

    def test_exact_table_point(self):
        self.assertEqual(fall_distance(70, "moved_load"), 10.0)

    def test_linear_interpolation(self):
        self.assertAlmostEqual(fall_distance(45, "moved_load"), 8.5)

    def test_building_object_scenario(self):
        self.assertAlmostEqual(fall_distance(45, "object_from_building"), 6.0)

    def test_height_above_table_is_blocked(self):
        with self.assertRaises(NormativeInputError):
            fall_distance(451, "moved_load")

    def test_danger_zone_offset_adds_largest_dimension(self):
        self.assertAlmostEqual(danger_zone_offset_from_outer_edge(20, 6), 13.0)


class ClearanceTests(unittest.TestCase):
    def test_hook_height_over_people(self):
        self.assertAlmostEqual(required_hook_height(60, 3, 2, True), 67.3)

    def test_hook_height_over_building_part(self):
        self.assertAlmostEqual(required_hook_height(60, 3, 2, False), 65.5)

    def test_two_cranes_at_limits(self):
        result = validate_joint_crane_clearances(5, 1)
        self.assertTrue(result.passed)
        self.assertEqual(result.status, "PASS_WITH_CONDITIONS")

    def test_two_cranes_below_horizontal_limit(self):
        result = validate_joint_crane_clearances(4.99, 1)
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "BLOCKED")

    def test_zero_vertical_difference_is_blocked(self):
        result = validate_joint_crane_clearances(5, 0)
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "BLOCKED")

    def test_parking_clearances(self):
        self.assertTrue(validate_joint_crane_parking_clearances(2,1).passed)
        self.assertFalse(validate_joint_crane_parking_clearances(1.99,1).passed)


if __name__ == "__main__":
    unittest.main()
