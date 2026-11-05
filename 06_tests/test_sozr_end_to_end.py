import math
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from pypdf import PdfReader  # noqa: E402
from crane_plan.engine import IntegrationStatus, load_catalog_v3, verify_scenario_v21  # noqa: E402
from crane_plan.geometry import arc_intersects_polygon_exact, segment_intersects_polygon_exact  # noqa: E402
from crane_plan.models import (  # noqa: E402
    Load, Placement, ProjectInput, RestrictedZone, RestrictedZoneKind,
    RouteEndpoint, RouteFailureCode, ScenarioResult, SiteInput, WorkPoint,
)
from crane_plan.report import generate_report  # noqa: E402
from crane_plan.route_planner import RoutePlannerSettings, plan_lift_route  # noqa: E402
from crane_plan.sozr import build_sozr_plan  # noqa: E402

CATALOG_V3 = load_catalog_v3(ROOT / "02_processed_data/cranes/crane_configurations_v3.json")


def project_and_zones():
    blocked_store = RestrictedZone(
        "Z-BLOCKED-STORE", "Склад 1 недоступен", RestrictedZoneKind.FULL_EXCLUSION,
        [(-6,-2),(-2,-2),(-2,2),(-6,2)], 0,
    )
    height_zone = RestrictedZone(
        "Z-HEIGHT", "Низкое препятствие", RestrictedZoneKind.HEIGHT_OBSTACLE,
        [(2,-12),(3,-12),(3,12),(2,12)], 10,
    )
    project = ProjectInput(
        "Сквозная проверка", "Москва", 2026, "", "", 0, 20,
        SiteInput(
            [(-80,-80),(80,-80),(80,80),(-80,80)],
            [(6,-3),(10,-3),(10,3),(6,3)],
            [blocked_store,height_zone],
            unloading_zone=[(-12,-2),(-10,-2),(-10,2),(-12,2)],
            storage_zones=[blocked_store.polygon,[(-6,3),(-2,3),(-2,7),(-6,7)]],
            min_crane_to_building_m=1,max_crane_to_building_m=25,
        ),
        [Load("Бадья",1000,100,1,1,2,10,rigging_height_m=1.5)],
        [WorkPoint(8,0,10,0,"Точка подачи 1")],
        loads_verified=True,restricted_zones_confirmed=True,route_angle_step_deg=2,
    )
    return project,blocked_store,height_zone


def planned(project, source, max_hook=44.4):
    return plan_lift_route(
        (0,0),60,42.4,max_hook,project.loads[0],
        RouteEndpoint("storage",source,0,"storage"),
        RouteEndpoint("work-1",(8,0),10,"work"),
        project,lambda _radius:6000,RoutePlannerSettings(2,0.5,3),
    )


class SOZREndToEndTests(unittest.TestCase):
    def test_original_no_route_case_finds_alternative_store_and_preserves_ids(self):
        project,blocked_store,_height_zone=project_and_zones()
        blocked=planned(project,(-4,0))
        self.assertIsNone(blocked.route)
        self.assertTrue(any(item.zone_id==blocked_store.id or item.code is RouteFailureCode.SOURCE_BLOCKED for item in blocked.failures))

        safe=planned(project,(-4,5))
        self.assertIsNotNone(safe.route)
        route=replace(safe.route,operation_id="OP-W1-L1")
        sozr=build_sozr_plan("K1",(0,0),60,project.site.restricted_zones,[route],project)
        placement=Placement(
            "LIEBHERR-130-ECB-6-60","130 EC-B 6",0,0,[0],8,14,60,
            jib_level_m=42.4,max_free_standing_height_m=44.4,accepted_crane_height_m=44.4,sozr_plan=sozr,
        )
        scenario=ScenarioResult("PASS",[placement],[],[],routes=[route],total_active_lifts=10,accounted_lifts=10)
        verified=verify_scenario_v21(project,scenario,CATALOG_V3,scenario_index=0,run_id="E2E",created_at="2026-10-22T12:00:00+03:00")
        self.assertIn(verified.status,{IntegrationStatus.VERIFIED,IntegrationStatus.VERIFIED_WITH_CONDITIONS})
        self.assertIsNotNone(verified.protocol)
        self.assertEqual(sozr.critical_routes[0].operation_id,"OP-W1-L1")
        engine_routes=verified.engine_result.accepted_solution.operation_routes
        self.assertEqual(engine_routes[0].operation_id,"OP-W1-L1")
        protocol_ids={check.operation_id for check in verified.engine_result.verification.checks if check.operation_id}
        self.assertIn("OP-W1-L1",protocol_ids)

        with tempfile.TemporaryDirectory() as tmp:
            report=generate_report(Path(tmp)/"pprk.pdf",project,[scenario])
            text="\n".join(page.extract_text() or "" for page in PdfReader(str(report)).pages)
        self.assertIn("OP-W1-L1",text)
        self.assertIn(sozr.points[0].label,text)

    def test_proven_no_route_has_numeric_height_diagnostic(self):
        project,_blocked,_height=project_and_zones()
        result=planned(project,(-4,5),max_hook=5)
        self.assertIsNone(result.route)
        height=[item for item in result.failures if item.code is RouteFailureCode.HEIGHT_EXCEEDED]
        self.assertTrue(height)
        self.assertIsNotNone(height[0].required_m)
        self.assertEqual(height[0].actual_m,5)

    def test_accepted_edges_pass_independent_exact_geometry_for_angle_set(self):
        project,blocked_store,_height=project_and_zones()
        for y in (5.0,5.5,6.0,6.5,7.0):
            with self.subTest(y=y):
                result=planned(project,(-4,y))
                self.assertIsNotNone(result.route)
                for start,end in zip(result.route.waypoints,result.route.waypoints[1:]):
                    if end.movement=="slew":
                        radius=math.hypot(start.x,start.y)
                        a=math.degrees(math.atan2(start.y,start.x))%360
                        b=math.degrees(math.atan2(end.y,end.x))%360
                        clockwise=((a-b)%360)<((b-a)%360)
                        self.assertFalse(arc_intersects_polygon_exact((0,0),radius,a,b,clockwise,blocked_store.polygon))
                    else:
                        self.assertFalse(segment_intersects_polygon_exact(start.point,end.point,blocked_store.polygon))


if __name__ == "__main__":
    unittest.main()
