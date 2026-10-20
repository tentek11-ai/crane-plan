from __future__ import annotations

from dataclasses import replace
import unittest

from crane_plan.engine.catalog import CapacityPoint, CraneConfigurationV3
from crane_plan.engine.constraints import ConstraintCode, evaluate_operation, evaluate_placement
from crane_plan.engine.domain import (
    ConstructionStage,
    LiftEndpoint,
    LiftingOperation,
    LoadSpec,
    ProjectV3,
    SiteGeometry,
    SourceKind,
    SourceLocator,
)


SOURCE = SourceLocator(SourceKind.PROJECT, "PLAN", "sheet 1")
PASSPORT = SourceLocator(SourceKind.PASSPORT, "CRANE", "p. 2", sha256="a" * 64)


def make_config(**changes: object) -> CraneConfigurationV3:
    config = CraneConfigurationV3(
        "CFG",
        "Liebherr",
        "Test",
        1,
        30.0,
        44.4,
        (CapacityPoint(25.0, 5900.0), CapacityPoint(30.0, 5200.0)),
        (25.0, 30.0),
        (5.0,),
        PASSPORT,
    )
    return replace(config, **changes)


def make_project(**changes: object) -> ProjectV3:
    load = LoadSpec("LOAD", "Load", 5000.0, 200.0, 2.0, 1.0, 2.0, 1.5, (SOURCE,))
    operation = LiftingOperation(
        "OP-1",
        "Lift",
        "STAGE-1",
        LiftEndpoint(5.0, 0.0, 0.0),
        LiftEndpoint(30.0, 0.0, 20.0),
        load,
        1,
        (SOURCE,),
    )
    site = SiteGeometry(
        ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0)),
        ((20.0, -5.0), (40.0, -5.0), (40.0, 5.0), (20.0, 5.0)),
        (),
        1.0,
        50.0,
        (SOURCE,),
    )
    project = ProjectV3(
        "P",
        "Project",
        "Moscow",
        (ConstructionStage("STAGE-1", "Stage", 1, 30, 20.0, (SOURCE,)),),
        site,
        (operation,),
        "RF",
        "test",
    )
    return replace(project, **changes)


class EngineConstraintTests(unittest.TestCase):
    def test_exact_reach_and_capacity_boundaries_pass(self):
        result = evaluate_operation(make_project().operations[0], (0.0, 0.0), make_config(), make_project())
        self.assertTrue(result.passed)
        self.assertEqual(result.reason_codes, ())
        self.assertEqual(result.radius_m, 30.0)
        self.assertEqual(result.capacity_margin_kg, 0.0)

    def test_all_required_rejection_codes_are_reported(self):
        project = make_project()
        operation = project.operations[0]

        negative = replace(operation.load, load_kg=-1.0)
        blocked = evaluate_operation(replace(operation, load=negative), (0.0, 0.0), make_config(), project)
        self.assertEqual(blocked.reason_codes, (ConstraintCode.INPUT_BLOCKED,))

        self.assertIn(
            ConstraintCode.REACH_EXCEEDED,
            evaluate_operation(replace(operation, destination=LiftEndpoint(30.01, 0, 20)), (0, 0), make_config(), project).reason_codes,
        )
        heavy = replace(operation.load, load_kg=5001.0)
        self.assertIn(
            ConstraintCode.CAPACITY_INSUFFICIENT,
            evaluate_operation(replace(operation, load=heavy), (0, 0), make_config(), project).reason_codes,
        )
        high = replace(operation, destination=LiftEndpoint(30, 0, 42.0))
        self.assertIn(
            ConstraintCode.HEIGHT_INSUFFICIENT,
            evaluate_operation(high, (0, 0), make_config(), project).reason_codes,
        )

        route_site = replace(project.site, restricted_zones=(((10, -1), (11, -1), (11, 1), (10, 1)),))
        route_project = replace(project, site=route_site)
        self.assertIn(
            ConstraintCode.ROUTE_CONFLICT,
            evaluate_operation(operation, (0, 0), make_config(), route_project).reason_codes,
        )

        tight_site = replace(
            project.site,
            boundary=((-40, -40), (32, -40), (32, 40), (-40, 40)),
        )
        self.assertIn(
            ConstraintCode.DANGER_ZONE_CONFLICT,
            evaluate_operation(operation, (0, 0), make_config(), replace(project, site=tight_site)).reason_codes,
        )

        unsupported = make_config(jib_length_m=27.5)
        self.assertIn(
            ConstraintCode.CONFIGURATION_UNSUPPORTED,
            evaluate_operation(operation, (0, 0), unsupported, project).reason_codes,
        )

    def test_placement_level_rejection_codes_and_critical_operations(self):
        project = make_project()
        config = make_config()
        cases = (
            ((60.0, 0.0), ConstraintCode.BASE_OUTSIDE_SITE),
            ((25.0, 0.0), ConstraintCode.BASE_INSIDE_BUILDING),
            ((19.5, 0.0), ConstraintCode.BASE_CLEARANCE_CONFLICT),
        )
        for point, code in cases:
            with self.subTest(code):
                self.assertIn(code, evaluate_placement(project, "STAGE-1", point, config).reason_codes)

        restricted_site = replace(
            project.site,
            restricted_zones=(((-1, -1), (1, -1), (1, 1), (-1, 1)),),
        )
        result = evaluate_placement(replace(project, site=restricted_site), "STAGE-1", (0, 0), config)
        self.assertIn(ConstraintCode.RESTRICTED_ZONE_CONFLICT, result.reason_codes)

        passing = evaluate_placement(project, "STAGE-1", (0, 0), config)
        self.assertTrue(passing.passed)
        self.assertEqual(passing.critical_capacity_operation_id, "OP-1")
        self.assertEqual(passing.critical_height_operation_id, "OP-1")

    def test_height_outside_normative_table_is_blocked_without_exception(self):
        project = make_project()
        operation = replace(project.operations[0], destination=LiftEndpoint(30, 0, 451.0))
        result = evaluate_operation(operation, (0, 0), make_config(), project)
        self.assertEqual(result.reason_codes, (ConstraintCode.INPUT_BLOCKED,))


if __name__ == "__main__":
    unittest.main()
