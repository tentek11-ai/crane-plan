import sys
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.models import (  # noqa: E402
    ProjectInput,
    RestrictedZone,
    RestrictedZoneKind,
    SOZRRestrictionClass,
    SiteInput,
)
from crane_plan.sozr import bearing_from_north_clockwise, build_sozr_plan  # noqa: E402


def project(zones):
    return ProjectInput(
        "СОЗР",
        "Москва",
        2026,
        "",
        "",
        0,
        20,
        SiteInput(
            boundary=[(-20, -20), (20, -20), (20, 20), (-20, 20)],
            building=[(-2, -2), (2, -2), (2, 2), (-2, 2)],
            restricted_zones=zones,
        ),
        [],
        [],
    )


class SOZRGeometryTests(unittest.TestCase):
    def test_full_turn_sector_keeps_the_whole_admissible_field(self):
        plan = build_sozr_plan("K1", (0, 0), 5.0, [], [], project([]), (0.0, 360.0))

        self.assertTrue(plan.admissible_contours)
        centers = [
            (sum(point[0] for point in cell) / len(cell), sum(point[1] for point in cell) / len(cell))
            for cell in plan.admissible_contours
        ]
        self.assertTrue(any(x < 0 for x, _ in centers))
        self.assertTrue(any(x > 0 for x, _ in centers))

    def test_wrapped_sector_keeps_cells_on_both_sides_of_zero_degrees(self):
        plan = build_sozr_plan("K1", (0, 0), 5.0, [], [], project([]), (350.0, 10.0))

        centers = [
            (sum(point[0] for point in cell) / len(cell), sum(point[1] for point in cell) / len(cell))
            for cell in plan.admissible_contours
        ]
        angles = [math.degrees(math.atan2(y, x)) % 360.0 for x, y in centers]
        self.assertTrue(any(angle >= 350.0 for angle in angles))
        self.assertTrue(any(angle <= 10.0 for angle in angles))
        self.assertTrue(all(angle >= 350.0 or angle <= 10.0 for angle in angles))

    def test_bearing_is_clockwise_from_plan_north(self):
        self.assertEqual(bearing_from_north_clockwise((0, 0), (0, 5)), 0.0)
        self.assertEqual(bearing_from_north_clockwise((0, 0), (5, 0)), 90.0)
        self.assertEqual(bearing_from_north_clockwise((0, 0), (0, -5)), 180.0)
        self.assertEqual(bearing_from_north_clockwise((0, 0), (-5, 0)), 270.0)

    def test_plan_contains_vertices_and_circle_intersections(self):
        inside = RestrictedZone(
            "full",
            "Полный запрет",
            RestrictedZoneKind.FULL_EXCLUSION,
            [(-1, 2), (1, 2), (1, 4), (-1, 4)],
            8.0,
        )
        crossing = RestrictedZone(
            "height",
            "Высотное препятствие",
            RestrictedZoneKind.HEIGHT_OBSTACLE,
            [(4, -1), (7, -1), (7, 1), (4, 1)],
            5.0,
        )
        plan = build_sozr_plan("K1", (0, 0), 5.0, [inside, crossing], [], project([inside, crossing]))

        full_points = [point for point in plan.points if point.zone_id == "full"]
        height_points = [point for point in plan.points if point.zone_id == "height"]
        self.assertEqual(len(full_points), 4)
        self.assertEqual(len(height_points), 4)
        self.assertEqual({point.restriction_class for point in full_points}, {SOZRRestrictionClass.PERMANENT})
        self.assertEqual({point.restriction_class for point in height_points}, {SOZRRestrictionClass.CONDITIONAL})
        self.assertTrue(any(abs(point.radius_m - 5.0) < 1e-6 for point in height_points))
        self.assertTrue(plan.admissible_contours)
        self.assertTrue(all((x * x + y * y) ** 0.5 <= 5.0 + 1e-9 for cell in plan.admissible_contours for x, y in cell))
        self.assertFalse(any(0 <= x <= 1 and 2 <= y <= 4 for cell in plan.admissible_contours for x, y in cell))

    def test_points_are_numbered_clockwise_with_stable_radius_tie_break(self):
        zone = RestrictedZone(
            "north",
            "Северная зона",
            RestrictedZoneKind.FULL_EXCLUSION,
            [(0, 2), (0, 4), (2, 4), (2, 2)],
            4.0,
        )
        plan = build_sozr_plan("K1", (0, 0), 10.0, [zone], [], project([zone]))

        self.assertEqual([point.label for point in plan.points], ["К1-1", "К1-2", "К1-3", "К1-4"])
        self.assertEqual([(point.bearing_deg, point.radius_m) for point in plan.points[:2]], [(0.0, 2.0), (0.0, 4.0)])
        self.assertEqual([point.bearing_deg for point in plan.points], sorted(point.bearing_deg for point in plan.points))

    def test_each_crane_has_independent_label_sequence(self):
        zone = RestrictedZone(
            "z",
            "Зона",
            RestrictedZoneKind.LOAD_PROHIBITED,
            [(1, 1), (2, 1), (2, 2), (1, 2)],
            3.0,
        )
        first = build_sozr_plan("K1", (0, 0), 10.0, [zone], [], project([zone]))
        second = build_sozr_plan("K2", (0, 0), 10.0, [zone], [], project([zone]))
        self.assertEqual(first.points[0].label, "К1-1")
        self.assertEqual(second.points[0].label, "К2-1")

    def test_overlap_adds_permanent_to_conditional_transition_point(self):
        permanent = RestrictedZone(
            "p",
            "Постоянная",
            RestrictedZoneKind.FULL_EXCLUSION,
            [(0, -2), (2, -2), (2, 2), (0, 2)],
            6.0,
        )
        conditional = RestrictedZone(
            "c",
            "Условная",
            RestrictedZoneKind.HEIGHT_OBSTACLE,
            [(-2, 0), (3, 0), (3, 1), (-2, 1)],
            4.0,
        )
        plan = build_sozr_plan("K1", (0, 0), 10.0, [permanent, conditional], [], project([permanent, conditional]))
        transitions = [point for point in plan.points if "переход" in point.condition.lower()]
        self.assertEqual({(round(point.x, 6), round(point.y, 6)) for point in transitions}, {(0.0, 0.0), (2.0, 0.0), (0.0, 1.0), (2.0, 1.0)})


if __name__ == "__main__":
    unittest.main()
