import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.models import (  # noqa: E402
    CraneConfiguration,
    Load,
    Placement,
    ProjectInput,
    RestrictedZone,
    RestrictedZoneKind,
    SiteInput,
    WorkPoint,
)
from crane_plan.optimizer import (  # noqa: E402
    build_logistics_chains,
    evaluate_logistics_chain,
    optimize,
)
from crane_plan.route_planner import RoutePlannerSettings  # noqa: E402


CONFIG = CraneConfiguration(
    "TEST-CRANE",
    "130 EC-B 6",
    1,
    20.0,
    6000.0,
    44.4,
    ((0.0, 6000.0), (20.0, 2000.0)),
    "test",
)


def make_project(*, stores=True, zones=()):
    storage = [
        [(-5, -5), (-3, -5), (-3, -3), (-5, -3)],
        [(-5, 3), (-3, 3), (-3, 5), (-5, 5)],
    ] if stores else []
    return ProjectInput(
        "Логистика",
        "Москва",
        2026,
        "",
        "",
        0,
        20,
        SiteInput(
            boundary=[(-15, -15), (15, -15), (15, 15), (-15, 15)],
            building=[(6, -2), (10, -2), (10, 2), (6, 2)],
            restricted_zones=list(zones),
            unloading_zone=[(-10, -1), (-8, -1), (-8, 1), (-10, 1)],
            storage_zones=storage,
        ),
        [Load("Бадья", 1000, 100, 1, 1, 2, rigging_height_m=1.5)],
        [WorkPoint(8, 0, 10, 0, "Точка подачи 1")],
        route_angle_step_deg=2.0,
    )


def placement():
    return Placement(
        "TEST-CRANE",
        "130 EC-B 6",
        0,
        0,
        [0],
        9,
        14,
        jib_length_m=20,
        jib_level_m=42.4,
        accepted_crane_height_m=44.4,
    )


class LogisticsChainTests(unittest.TestCase):
    def test_multiple_stores_create_one_complete_chain_per_store(self):
        project = make_project()
        chains = build_logistics_chains(project.site, project.work_points[0], work_index=0)

        self.assertEqual(len(chains), 2)
        self.assertEqual(
            [(leg.source_id, leg.destination_id) for leg in chains[0]],
            [("unloading", "storage-1"), ("storage-1", "work-1")],
        )
        self.assertEqual(
            [(leg.source_id, leg.destination_id) for leg in chains[1]],
            [("unloading", "storage-2"), ("storage-2", "work-1")],
        )

    def test_without_storage_direct_chain_runs_from_unloading_to_work_point(self):
        project = make_project(stores=False)
        chains = build_logistics_chains(project.site, project.work_points[0], work_index=0)
        self.assertEqual(len(chains), 1)
        self.assertEqual(len(chains[0]), 1)
        self.assertEqual((chains[0][0].source_id, chains[0][0].destination_id), ("unloading", "work-1"))

    def test_chain_evaluation_returns_routes_for_every_leg(self):
        project = make_project(stores=False)
        chain = build_logistics_chains(project.site, project.work_points[0], work_index=0)[0]
        result = evaluate_logistics_chain(
            placement(),
            chain,
            project,
            RoutePlannerSettings(angle_step_deg=2.0, radius_step_m=0.5),
            CONFIG,
        )
        self.assertTrue(result.safe)
        self.assertEqual(len(result.routes), 1)
        self.assertEqual(result.routes[0].operation_id, "WP1:unloading->work-1")

    def test_chain_reports_source_on_zone_boundary_with_specific_failure(self):
        zone = RestrictedZone(
            "source-zone",
            "Запрет у разгрузки",
            RestrictedZoneKind.FULL_EXCLUSION,
            [(-10, -1), (-8, -1), (-8, 1), (-10, 1)],
            2.0,
        )
        project = make_project(stores=False, zones=[zone])
        chain = build_logistics_chains(project.site, project.work_points[0], work_index=0)[0]
        result = evaluate_logistics_chain(
            placement(), chain, project, RoutePlannerSettings(angle_step_deg=2.0), CONFIG
        )
        self.assertFalse(result.safe)
        self.assertEqual(result.failed_leg.source_id, "unloading")
        self.assertTrue(any(failure.zone_id == "source-zone" for failure in result.failures))

    def test_optimizer_chooses_safe_store_when_another_store_is_blocked(self):
        blocked_store = RestrictedZone(
            "blocked-store-1",
            "Запрет у склада 1",
            RestrictedZoneKind.FULL_EXCLUSION,
            [(-5, -5), (-3, -5), (-3, -3), (-5, -3)],
            3.0,
        )
        project = make_project(zones=[blocked_store])
        project.protective_screen_possible = True
        scenarios = optimize(project, [CONFIG], max_variants=1, step_m=2.0)

        self.assertIn(scenarios[0].status, {"PASS", "PASS_WITH_CONDITIONS"})
        self.assertTrue(scenarios[0].routes)
        self.assertTrue(any("storage-2" in route.operation_id for route in scenarios[0].routes))
        self.assertFalse(any("storage-1->work" in route.operation_id for route in scenarios[0].routes))
        self.assertIsNotNone(scenarios[0].placements[0].sozr_plan)
        self.assertEqual(
            scenarios[0].placements[0].sozr_plan.critical_routes,
            tuple(scenarios[0].routes),
        )

    def test_optimizer_reports_each_store_when_no_complete_chain_is_safe(self):
        zones = [
            RestrictedZone(
                f"blocked-store-{index}",
                f"Запрет у склада {index}",
                RestrictedZoneKind.FULL_EXCLUSION,
                polygon,
                3.0,
            )
            for index, polygon in enumerate(
                [
                    [(-5, -5), (-3, -5), (-3, -3), (-5, -3)],
                    [(-5, 3), (-3, 3), (-3, 5), (-5, 5)],
                ],
                start=1,
            )
        ]
        project = make_project(zones=zones)
        project.protective_screen_possible = True
        scenarios = optimize(project, [CONFIG], max_variants=1, step_m=2.0)

        self.assertEqual(scenarios[0].status, "BLOCKED")
        message = "\n".join(scenarios[0].reasons)
        self.assertIn("storage-1", message)
        self.assertIn("storage-2", message)
        self.assertIn("blocked-store-1", message)
        self.assertIn("blocked-store-2", message)


if __name__ == "__main__":
    unittest.main()
