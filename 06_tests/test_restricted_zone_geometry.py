import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.geometry import (  # noqa: E402
    arc_intersects_polygon_exact,
    segment_circle_intersections,
    segment_intersects_polygon_exact,
)
from crane_plan.models import RestrictedZone, RestrictedZoneKind  # noqa: E402
from crane_plan.restricted_zones import (  # noqa: E402
    buffered_zone_polygon,
    jib_may_overfly,
    load_may_overfly,
    tower_is_allowed,
    validate_zone,
)


def zone(kind=RestrictedZoneKind.HEIGHT_OBSTACLE, **overrides):
    values = {
        "id": "zone-1",
        "name": "Препятствие",
        "kind": kind,
        "polygon": [(2, -1), (4, -1), (4, 1), (2, 1)],
        "height_m": 10.0,
    }
    values.update(overrides)
    return RestrictedZone(**values)


class RestrictedZoneRulesTests(unittest.TestCase):
    def test_unverified_migrated_zone_is_a_blocking_validation_issue(self):
        zone = RestrictedZone(
            "legacy", "Непроверенная зона", RestrictedZoneKind.FULL_EXCLUSION,
            [(0, 0), (4, 0), (4, 4), (0, 4)], 0.0, verified=False,
        )
        self.assertTrue(any("подтверд" in item.lower() for item in validate_zone(zone)))

    def test_height_threshold_is_inclusive_at_exactly_three_metres(self):
        obstacle = zone()
        for actual, allowed in ((12.999, False), (13.0, True), (13.001, True)):
            with self.subTest(actual=actual):
                self.assertEqual(load_may_overfly(obstacle, actual, 3.0), allowed)
                self.assertEqual(jib_may_overfly(obstacle, actual, 3.0), allowed)

    def test_zone_types_apply_distinct_load_and_jib_rules(self):
        load_prohibited = zone(RestrictedZoneKind.LOAD_PROHIBITED)
        full = zone(RestrictedZoneKind.FULL_EXCLUSION)

        self.assertFalse(load_may_overfly(load_prohibited, 100.0, 3.0))
        self.assertTrue(jib_may_overfly(load_prohibited, 13.0, 3.0))
        self.assertFalse(jib_may_overfly(load_prohibited, 12.999, 3.0))
        self.assertFalse(load_may_overfly(full, 100.0, 3.0))
        self.assertFalse(jib_may_overfly(full, 100.0, 3.0))

    def test_tower_boundary_contact_is_not_allowed(self):
        obstacle = zone(horizontal_clearance_m=1.0)
        self.assertFalse(tower_is_allowed(obstacle, (0.0, 0.0), 1.0))
        self.assertTrue(tower_is_allowed(obstacle, (-0.001, 0.0), 1.0))

    def test_validation_reports_concise_geometry_failures(self):
        concave = zone(polygon=[(0, 0), (4, 0), (4, 4), (2, 2), (0, 4)])
        self.assertEqual(validate_zone(concave), [])

        crossing = zone(polygon=[(0, 0), (4, 4), (0, 4), (4, 0)])
        issues = validate_zone(crossing)
        self.assertTrue(any("самопересечение" in issue for issue in issues))

        collinear = zone(polygon=[(0, 0), (2, 0), (4, 0)])
        issues = validate_zone(collinear)
        self.assertTrue(any("площадь" in issue for issue in issues))

    def test_horizontal_clearance_expands_zone_outward(self):
        obstacle = zone(horizontal_clearance_m=1.0)
        buffered = buffered_zone_polygon(obstacle)
        xs = [point[0] for point in buffered]
        ys = [point[1] for point in buffered]
        self.assertEqual((min(xs), max(xs), min(ys), max(ys)), (1.0, 5.0, -2.0, 2.0))


class ExactGeometryTests(unittest.TestCase):
    def test_segment_circle_intersections_are_analytic_and_ordered(self):
        points = segment_circle_intersections((-2, 0), (2, 0), (0, 0), 1.0)
        self.assertEqual(points, [(-1.0, 0.0), (1.0, 0.0)])
        self.assertEqual(segment_circle_intersections((-2, 1), (2, 1), (0, 0), 1.0), [(0.0, 1.0)])
        self.assertEqual(segment_circle_intersections((-2, 2), (2, 2), (0, 0), 1.0), [])

    def test_segment_boundary_contact_counts_as_collision(self):
        square = [(0, 0), (2, 0), (2, 2), (0, 2)]
        self.assertTrue(segment_intersects_polygon_exact((-1, 0), (3, 0), square))
        self.assertFalse(
            segment_intersects_polygon_exact(
                (-1, 0), (3, 0), square, boundary_is_collision=False
            )
        )

    def test_arc_detects_edge_crossing_between_safe_endpoints(self):
        thin_zone = [(-0.2, 4.8), (0.2, 4.8), (0.2, 5.2), (-0.2, 5.2)]
        self.assertTrue(
            arc_intersects_polygon_exact(
                (0, 0), 5.0, 45.0, 135.0, False, thin_zone
            )
        )
        self.assertFalse(
            arc_intersects_polygon_exact(
                (0, 0), 5.0, 225.0, 315.0, False, thin_zone
            )
        )

    def test_clockwise_arc_uses_requested_sweep(self):
        right_zone = [(4.8, -0.2), (5.2, -0.2), (5.2, 0.2), (4.8, 0.2)]
        self.assertTrue(
            arc_intersects_polygon_exact(
                (0, 0), 5.0, 90.0, 270.0, True, right_zone
            )
        )
        self.assertFalse(
            arc_intersects_polygon_exact(
                (0, 0), 5.0, 90.0, 270.0, False, right_zone
            )
        )


if __name__ == "__main__":
    unittest.main()
