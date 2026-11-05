import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.models import (  # noqa: E402
    Load,
    ProjectInput,
    RestrictedZone,
    RestrictedZoneKind,
    RouteEndpoint,
    RouteFailureCode,
    LiftRoute,
    RouteAlternative,
    RouteWaypoint,
    SiteInput,
)
from crane_plan.route_planner import OtherCraneConstraint, RoutePlannerSettings, plan_lift_route  # noqa: E402


def polar(radius, angle_deg):
    angle = math.radians(angle_deg)
    return radius * math.cos(angle), radius * math.sin(angle)


def project_with(zones=()):
    return ProjectInput(
        "Маршрут",
        "Москва",
        2026,
        "",
        "",
        0,
        30,
        SiteInput(
            boundary=[(-20, -20), (20, -20), (20, 20), (-20, 20)],
            building=[(15, 15), (16, 15), (16, 16), (15, 16)],
            restricted_zones=list(zones),
        ),
        [],
        [],
    )


def test_load():
    return Load("Груз", 1000, 100, 1, 1, 2, rigging_height_m=1.5)


def plan(source, destination, zones=(), *, settings=None, capacity=None, jib=8.0, other_cranes=()):
    return plan_lift_route(
        crane_point=(0, 0),
        jib_length_m=jib,
        jib_bottom_m=20.0,
        max_hook_height_m=30.0,
        load=test_load(),
        source=RouteEndpoint("source", source, 0.0, "unloading"),
        destination=RouteEndpoint("destination", destination, 0.0, "work"),
        project=project_with(zones),
        capacity_at_radius=capacity or (lambda _radius: 5000.0),
        settings=settings or RoutePlannerSettings(angle_step_deg=1.0, radius_step_m=0.5),
        other_cranes=other_cranes,
    )


def other_route(*points):
    return LiftRoute("OTHER",tuple(RouteWaypoint(x,y,22,"slew") for x,y in points),22,(RouteAlternative("direct",True,3,10),),"b"*64)


class PolarRoutePlannerTests(unittest.TestCase):
    def test_non_grid_bearing_near_360_is_inserted_into_cyclic_axis(self):
        result = plan(polar(5, 359.5), polar(5, 0.5))
        self.assertIsNotNone(result.route)

    def test_normative_danger_envelope_must_remain_inside_site_along_route(self):
        result = plan((-5, 19), (5, 19), jib=20.0)
        self.assertIsNone(result.route)
        self.assertIn(RouteFailureCode.SITE_BOUNDARY, {item.code for item in result.failures})

    def test_other_tower_between_safe_angular_nodes_is_rejected_continuously(self):
        other = OtherCraneConstraint("K2", polar(4, 0.5), 0.01, 30, 2, (), ())
        opposite = OtherCraneConstraint("K3", polar(4, 180.5), 0.01, 30, 2, (), ())
        result = plan(
            polar(5, 0), polar(5, 1), jib=5.0, other_cranes=(other, opposite),
            settings=RoutePlannerSettings(angle_step_deg=1.0, radius_step_m=0.5, minimum_radius_m=5.0),
        )
        self.assertIsNone(result.route)
        self.assertIn(RouteFailureCode.SECOND_CRANE_CONFLICT, {item.code for item in result.failures})

    def test_tower_jib_conflict_is_reported_with_other_crane_id(self):
        other=OtherCraneConstraint("K2",(1,0),2,30,2,(),())
        result=plan((5,0),(0,5),other_cranes=(other,))
        self.assertIsNone(result.route)
        conflicts=[item for item in result.failures if item.code is RouteFailureCode.SECOND_CRANE_CONFLICT]
        self.assertTrue(conflicts)
        self.assertEqual(conflicts[0].zone_id,"K2")
        self.assertIn("башн",conflicts[0].message.lower())

    def test_vertically_separated_jibs_allow_crossing_plan_routes(self):
        route=other_route((10,0),(0,0))
        other=OtherCraneConstraint("K2",(10,0),2,30,2,(route,),((0,360),))
        result=plan((-5,0),(0,5),other_cranes=(other,))
        self.assertIsNotNone(result.route)

    def test_insufficient_vertical_gap_blocks_jib_jib_intersection(self):
        route=other_route((10,0),(0,0))
        other=OtherCraneConstraint("K2",(10,0),2,20.5,2,(route,),((0,360),))
        result=plan((-5,0),(0,5),other_cranes=(other,))
        self.assertIsNone(result.route)
        self.assertTrue(any("K2" in item.message and "стрел" in item.message.lower() for item in result.failures))

    def test_other_crane_collision_uses_full_mounted_jib_beyond_trolley_radius(self):
        upper = OtherCraneConstraint(
            "K2", (10, 5), 0.01, 20.5, 2, (other_route((9, 5)),), ((170, 190),), 10.0
        )
        lower = OtherCraneConstraint(
            "K3", (10, -5), 0.01, 20.5, 2, (other_route((9, -5)),), ((170, 190),), 10.0
        )

        result = plan(
            polar(5, 89),
            polar(5, 91),
            jib=5.0,
            other_cranes=(upper, lower),
            settings=RoutePlannerSettings(angle_step_deg=1.0, radius_step_m=0.5, minimum_radius_m=5.0),
        )

        self.assertIsNone(result.route)
        self.assertIn(RouteFailureCode.SECOND_CRANE_CONFLICT, {item.code for item in result.failures})

    def test_restricting_other_crane_sector_can_release_route(self):
        route=other_route((10,0),(0,0))
        blocked=OtherCraneConstraint("K2",(10,0),2,20.5,2,(route,),((170,190),))
        released=OtherCraneConstraint("K2",(10,0),2,20.5,2,(route,),((300,330),))
        self.assertIsNone(plan((-5,0),(0,5),other_cranes=(blocked,)).route)
        self.assertIsNotNone(plan((-5,0),(0,5),other_cranes=(released,)).route)

    def test_load_jib_conflict_is_classified_separately(self):
        route=other_route((10,0),(-10,0))
        other=OtherCraneConstraint("K2",(10,0),2,1.0,2,(route,),((170,190),))
        result=plan((-5,0),(0,5),other_cranes=(other,))
        self.assertIsNone(result.route)
        self.assertTrue(any("груз" in item.message.lower() and item.zone_id=="K2" for item in result.failures))
    def test_direct_route_is_returned_for_open_site(self):
        result = plan((5, 0), (0, 5))
        self.assertIsNotNone(result.route)
        self.assertEqual(result.failures, [])
        self.assertEqual(result.route.waypoints[0].point, (5, 0))
        self.assertEqual(result.route.waypoints[-1].point, (0, 5))

    def test_height_obstacle_is_crossed_only_at_required_transport_height(self):
        obstacle = RestrictedZone(
            "height-1",
            "Низкое здание",
            RestrictedZoneKind.HEIGHT_OBSTACLE,
            [(-20.0, 2.0), (20.0, 2.0), (20.0, 3.0), (-20.0, 3.0)],
            10.0,
        )
        result = plan((5, 0), (0, 5), [obstacle])
        self.assertIsNotNone(result.route)
        self.assertEqual(result.route.transport_hook_height_m, 16.5)
        self.assertTrue(any(item.kind == "over" and item.accepted for item in result.route.alternatives))
        self.assertTrue(any(not item.accepted and item.failures for item in result.route.alternatives))

    def test_load_prohibited_zone_can_be_bypassed_at_smaller_radius(self):
        obstacle = RestrictedZone(
            "load-1",
            "Запрет проноса",
            RestrictedZoneKind.LOAD_PROHIBITED,
            [(3.5, -0.5), (5.5, -0.5), (5.5, 0.5), (3.5, 0.5)],
            5.0,
        )
        result = plan(polar(5, -30), polar(5, 30), [obstacle])
        self.assertIsNotNone(result.route)
        radii = [math.hypot(*waypoint.point) for waypoint in result.route.waypoints]
        self.assertLess(min(radii), 3.5)
        self.assertTrue(any(item.kind == "inner" and item.accepted for item in result.route.alternatives))

    def test_outer_bypass_is_used_when_minimum_trolley_radius_blocks_inner_route(self):
        obstacle = RestrictedZone(
            "load-2",
            "Радиальный запрет",
            RestrictedZoneKind.LOAD_PROHIBITED,
            [(-3.0, -0.6), (3.0, -0.6), (3.0, 0.6), (-3.0, 0.6)],
            5.0,
        )
        settings = RoutePlannerSettings(
            angle_step_deg=2.0,
            radius_step_m=0.5,
            minimum_radius_m=1.0,
        )
        result = plan(polar(2.5, -60), polar(2.5, 60), [obstacle], settings=settings)
        self.assertIsNotNone(result.route)
        radii = [math.hypot(*waypoint.point) for waypoint in result.route.waypoints]
        self.assertGreater(max(radii), 3.0)
        self.assertTrue(any(item.kind == "outer" and item.accepted for item in result.route.alternatives))

    def test_capacity_limit_explains_why_required_outer_bypass_failed(self):
        obstacle = RestrictedZone(
            "load-3",
            "Радиальный запрет",
            RestrictedZoneKind.LOAD_PROHIBITED,
            [(-3.0, -0.6), (3.0, -0.6), (3.0, 0.6), (-3.0, 0.6)],
            5.0,
        )
        settings = RoutePlannerSettings(angle_step_deg=2.0, radius_step_m=0.5, minimum_radius_m=1.0)
        result = plan(
            polar(2.5, -60),
            polar(2.5, 60),
            [obstacle],
            settings=settings,
            capacity=lambda radius: 5000.0 if radius <= 3.0 else 1000.0,
        )
        self.assertIsNone(result.route)
        self.assertIn(RouteFailureCode.CAPACITY_EXCEEDED, {item.code for item in result.failures})
        self.assertIn(RouteFailureCode.NO_PATH, {item.code for item in result.failures})

    def test_exact_arc_check_rejects_thin_zone_between_grid_angles(self):
        obstacle = RestrictedZone(
            "thin",
            "Тонкая зона",
            RestrictedZoneKind.FULL_EXCLUSION,
            [(4.99, 0.02), (5.01, 0.02), (5.01, 0.07), (4.99, 0.07)],
            20.0,
        )
        opposite = RestrictedZone(
            "thin-opposite",
            "Тонкая зона с обратной стороны",
            RestrictedZoneKind.FULL_EXCLUSION,
            [(-5.01, -0.07), (-4.99, -0.07), (-4.99, -0.02), (-5.01, -0.02)],
            20.0,
        )
        settings = RoutePlannerSettings(angle_step_deg=1.0, radius_step_m=0.5, minimum_radius_m=5.0)
        result = plan(polar(5, 0), polar(5, 1), [obstacle, opposite], settings=settings, jib=5.0)
        self.assertIsNone(result.route)
        self.assertIn(RouteFailureCode.EXACT_RECHECK_FAILED, {item.code for item in result.failures})

    def test_route_maximizes_minimum_clearance_before_shortest_length(self):
        obstacle = RestrictedZone(
            "clearance",
            "Асимметричный вырез",
            RestrictedZoneKind.LOAD_PROHIBITED,
            [(2.5, -0.4), (4.3, -0.4), (4.3, 0.4), (2.5, 0.4)],
            5.0,
        )
        settings = RoutePlannerSettings(angle_step_deg=2.0, radius_step_m=0.5, minimum_radius_m=1.0)
        result = plan(polar(4, -25), polar(4, 25), [obstacle], settings=settings)
        self.assertIsNotNone(result.route)
        radii = [math.hypot(*waypoint.point) for waypoint in result.route.waypoints]
        self.assertGreater(max(radii), 4.3)
        self.assertGreater(result.route.alternatives[0].min_clearance_m, 0.0)

    def test_combined_route_can_raise_then_change_radius(self):
        height_obstacle = RestrictedZone(
            "height-combined",
            "Низкое здание",
            RestrictedZoneKind.HEIGHT_OBSTACLE,
            [(-20.0, 2.0), (20.0, 2.0), (20.0, 3.0), (-20.0, 3.0)],
            10.0,
        )
        load_prohibited = RestrictedZone(
            "load-combined",
            "Запрет проноса",
            RestrictedZoneKind.LOAD_PROHIBITED,
            [(3.5, -0.5), (5.0, -0.5), (5.0, 0.5), (3.5, 0.5)],
            5.0,
        )
        result = plan(polar(5, -30), polar(5, 45), [height_obstacle, load_prohibited])
        self.assertIsNotNone(result.route)
        self.assertGreaterEqual(result.route.transport_hook_height_m, 16.5)
        kinds = {item.kind for item in result.route.alternatives if item.accepted}
        self.assertIn("over", kinds)
        self.assertTrue({"inner", "outer"} & kinds)


if __name__ == "__main__":
    unittest.main()
