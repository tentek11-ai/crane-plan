from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.engine import SourceKind, adapt_scenario_v21, load_catalog_v3, verify_scenario_v21  # noqa: E402
from crane_plan.engine.domain import RestrictedZoneTypeV3  # noqa: E402
from crane_plan.models import LiftRoute, Load, Placement, ProjectInput, RouteWaypoint, ScenarioResult, SiteInput, WorkPoint  # noqa: E402


CATALOG = load_catalog_v3(ROOT / "02_processed_data/cranes/crane_configurations_v3.json")


def make_project(*, verified: bool = True) -> ProjectInput:
    return ProjectInput(
        name="Дом",
        city="Москва",
        year=2026,
        author="",
        email="",
        pit_bottom_m=-3,
        parapet_m=27,
        site=SiteInput(
            boundary=[(-80, -80), (80, -80), (80, 80), (-80, 80)],
            building=[(20, -10), (40, -10), (40, 10), (20, 10)],
            restricted_zones=[[(-60, 30), (-50, 30), (-50, 40), (-60, 40)]],
            unloading_zone=[(-20, -5), (-10, -5), (-10, 5), (-20, 5)],
            storage_zones=[[(-10, -5), (0, -5), (0, 5), (-10, 5)]],
            min_crane_to_building_m=1,
            max_crane_to_building_m=25,
        ),
        loads=[Load("Бадья", 1200, 100, 1.8, 1.8, 2.4, lifts=12)],
        work_points=[WorkPoint(25, 0, 20, 0, "Подача 1")],
        loads_verified=verified,
    )


def make_scenario(*, jib: float = 60, crane_id: str = "LIEBHERR-130-ECB-6-60") -> ScenarioResult:
    placement = Placement(
        crane_id=crane_id,
        model="130 EC-B 6",
        x=0,
        y=0,
        assigned_work_points=[0],
        max_radius_m=25,
        required_hook_height_m=25,
        jib_length_m=jib,
        max_free_standing_height_m=44.4,
        accepted_crane_height_m=44.4,
    )
    return ScenarioResult("PASS", [placement], [], [])


class GuiAdapterTests(unittest.TestCase):
    def test_adapts_verified_single_crane_scenario(self):
        adapted = adapt_scenario_v21(make_project(), make_scenario(), CATALOG, scenario_index=0)

        self.assertEqual(adapted.issues, ())
        self.assertEqual(adapted.project.stages[0].id, "MAIN_STAGE")
        self.assertEqual(adapted.project.stages[0].mounting_level_m, 20)
        self.assertEqual(adapted.project.site.boundary, ((-80, -80), (80, -80), (80, 80), (-80, 80)))
        self.assertEqual(adapted.project.site.building, ((20, -10), (40, -10), (40, 10), (20, 10)))
        self.assertEqual(adapted.project.site.restricted_zones[0][0], (-60, 30))
        self.assertEqual(adapted.project.site.restricted_zones[0].kind, RestrictedZoneTypeV3.FULL_EXCLUSION)
        self.assertEqual((adapted.project.site.min_crane_to_building_m, adapted.project.site.max_crane_to_building_m), (1, 25))
        operation = adapted.project.operations[0]
        self.assertEqual(operation.id, "OP-W1-L1")
        self.assertEqual((operation.source.x_m, operation.source.y_m), (-5, 0))
        self.assertEqual((operation.destination.x_m, operation.destination.y_m, operation.destination.z_m), (25, 0, 20))
        self.assertEqual((operation.load.load_kg, operation.load.rigging_kg, operation.count), (1200, 100, 12))
        self.assertEqual((operation.load.length_m, operation.load.width_m, operation.load.height_m), (1.8, 1.8, 2.4))
        self.assertEqual(operation.load.rigging_height_m, 1.5)
        self.assertEqual(operation.load.sources[0].kind, SourceKind.PROJECT)
        placement = adapted.solution.stages[0].placements[0]
        self.assertEqual((placement.id, placement.configuration_id), ("SCENARIO-1-CRANE-1", "LIEBHERR-130-ECB-6-60-V3"))

    def test_unconfirmed_load_uses_explicit_assumption_source(self):
        adapted = adapt_scenario_v21(make_project(verified=False), make_scenario(), CATALOG, scenario_index=0)
        self.assertEqual(adapted.project.operations[0].load.sources[0].kind, SourceKind.ASSUMPTION)

    def test_unloading_zone_is_used_when_storage_is_absent(self):
        project = make_project()
        project.site.storage_zones = []
        adapted = adapt_scenario_v21(project, make_scenario(), CATALOG, scenario_index=0)
        source = adapted.project.operations[0].source
        self.assertEqual((source.x_m, source.y_m), (-15, 0))

    def test_multiple_storage_zones_use_store_selected_by_planned_route(self):
        project = make_project()
        project.site.storage_zones.append([(1, 1), (2, 1), (2, 2), (1, 2)])
        scenario = make_scenario()
        scenario.routes = [
            LiftRoute(
                "WP1:storage-2->work-1",
                (RouteWaypoint(1.5, 1.5, 25.0, "hoist"), RouteWaypoint(25, 0, 25.0, "slew")),
                25.0,
                (),
                "a" * 64,
            )
        ]
        adapted = adapt_scenario_v21(project, scenario, CATALOG, scenario_index=0)
        self.assertNotIn("LOGISTICS_SOURCE_AMBIGUOUS", [issue.code for issue in adapted.issues])
        source = adapted.project.operations[0].source
        self.assertEqual((source.x_m, source.y_m), (1.5, 1.5))
        self.assertEqual(len(adapted.solution.operation_routes), 1)
        self.assertEqual(adapted.solution.operation_routes[0].operation_id, "OP-W1-L1")
        self.assertEqual(adapted.solution.operation_routes[0].source_id, "storage-2")

    def test_multiple_storage_zones_without_planned_route_require_selection(self):
        project = make_project()
        project.site.storage_zones.append([(1, 1), (2, 1), (2, 2), (1, 2)])
        adapted = adapt_scenario_v21(project, make_scenario(), CATALOG, scenario_index=0)
        self.assertIn("LOGISTICS_ROUTE_NOT_SELECTED", [issue.code for issue in adapted.issues])

    def test_missing_logistics_zone_is_required(self):
        project = make_project()
        project.site.storage_zones = []
        project.site.unloading_zone = []
        adapted = adapt_scenario_v21(project, make_scenario(), CATALOG, scenario_index=0)
        self.assertIn("LOGISTICS_SOURCE_REQUIRED", [issue.code for issue in adapted.issues])

    def test_active_load_without_own_point_is_checked_at_every_work_point(self):
        project = make_project()
        project.loads.append(Load("Газоблок", 900, 100, 1.2, 1.0, 1.0, lifts=4))
        project.work_points.append(WorkPoint(30, 5, 22, 0, "Подача 2"))
        adapted = adapt_scenario_v21(project, make_scenario(), CATALOG, scenario_index=0)
        ids = [operation.id for operation in adapted.project.operations]
        self.assertEqual(ids, ["OP-W1-L1", "OP-W1-L2", "OP-W2-L1", "OP-W2-L2"])

    def test_inactive_load_does_not_create_operations(self):
        project = make_project()
        project.loads.append(Load("Исключён", 900, 100, 1, 1, 1, active=False))
        adapted = adapt_scenario_v21(project, make_scenario(), CATALOG, scenario_index=0)
        self.assertEqual([operation.id for operation in adapted.project.operations], ["OP-W1-L1"])

    def test_short_jib_uses_conservative_base_curve_and_condition(self):
        adapted = adapt_scenario_v21(make_project(), make_scenario(jib=50), CATALOG, scenario_index=0)
        derived = adapted.catalog[0]
        self.assertEqual(derived.id, "LIEBHERR-130-ECB-6-60-V3@JIB-50M")
        self.assertEqual(derived.jib_length_m, 50)
        self.assertEqual(derived.capacity_curve, CATALOG[0].capacity_curve)
        self.assertTrue(any("60" in message and "50" in message for message in adapted.conditional_messages))

    def test_unknown_crane_is_not_mapped_to_supported_configuration(self):
        adapted = adapt_scenario_v21(make_project(), make_scenario(crane_id="OTHER"), CATALOG, scenario_index=0)
        self.assertIn("CONFIGURATION_NOT_IN_V3_CATALOG", [issue.code for issue in adapted.issues])

    def test_two_cranes_are_adapted_with_distinct_assignments(self):
        project = make_project()
        project.work_points.append(WorkPoint(35, 5, 20, 0, "Подача 2"))
        scenario = make_scenario()
        scenario.placements[0].assigned_work_points = [0]
        second = make_scenario().placements[0]
        second.x = 10
        second.y = 20
        second.assigned_work_points = [1]
        scenario.placements.append(second)
        adapted = adapt_scenario_v21(project, scenario, CATALOG, scenario_index=0)
        self.assertNotIn("MULTI_CRANE_NOT_SUPPORTED", [issue.code for issue in adapted.issues])
        self.assertEqual(len(adapted.solution.stages[0].placements), 2)
        assignments = {item.operation_id: item.placement_id for item in adapted.solution.stages[0].assignments}
        self.assertEqual(assignments["OP-W1-L1"], "SCENARIO-1-CRANE-1")
        self.assertEqual(assignments["OP-W2-L1"], "SCENARIO-1-CRANE-2")

    def test_safe_two_crane_scenario_passes_release_adapter(self):
        project = make_project()
        project.work_points.append(WorkPoint(35, 5, 20, 0, "Подача 2"))
        scenario = make_scenario()
        scenario.placements[0].assigned_work_points = [0]
        second = make_scenario().placements[0]
        second.x = 10
        second.y = 20
        second.assigned_work_points = [1]
        scenario.placements.append(second)
        result = verify_scenario_v21(
            project, scenario, CATALOG, scenario_index=0,
            run_id="TWO-CRANE", created_at="2026-10-22T00:00:00+03:00",
        )
        self.assertTrue(result.release_allowed, result.messages)

    def test_tie_ins_are_marked_for_expert_review(self):
        scenario = make_scenario()
        scenario.placements[0].tie_in_levels_m = [38.4]
        adapted = adapt_scenario_v21(make_project(), scenario, CATALOG, scenario_index=0)
        self.assertIn("TIE_INS_NOT_VERIFIED", [issue.code for issue in adapted.issues])

    def test_protective_screen_is_transferred_to_solution(self):
        project = make_project()
        project.protective_screen_possible = True
        adapted = adapt_scenario_v21(project, make_scenario(), CATALOG, scenario_index=0)
        self.assertEqual(adapted.solution.stages[0].placements[0].protective_measures, ("PROTECTIVE_SCREEN",))


if __name__ == "__main__":
    unittest.main()
