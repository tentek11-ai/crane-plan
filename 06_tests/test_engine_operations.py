from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from crane_plan.engine.domain import (
    ConstructionStage,
    LiftEndpoint,
    ProjectV3,
    SiteGeometry,
    SourceKind,
    SourceLocator,
)
from crane_plan.engine.operations import (
    OperationBuildError,
    OperationRequest,
    build_operations,
    load_standard_loads,
    validate_operations,
)


ROOT = Path(__file__).resolve().parents[1]
LOADS_PATH = ROOT / "02_processed_data" / "loads" / "standard_monolithic_loads.json"
PROJECT_SOURCE = SourceLocator(SourceKind.PROJECT, "PLAN-1", "sheet 1")


def make_request(**changes: object) -> OperationRequest:
    values: dict[str, object] = {
        "request_id": "REQ-1",
        "stage_id": "STAGE-1",
        "load_template_id": "concrete_bucket_1",
        "source": LiftEndpoint(5.0, 5.0, 0.0),
        "destination": LiftEndpoint(25.0, 20.0, 18.0),
        "count": 10,
        "source_locator": PROJECT_SOURCE,
    }
    values.update(changes)
    return OperationRequest(**values)  # type: ignore[arg-type]


class EngineOperationTests(unittest.TestCase):
    def setUp(self):
        self.library = load_standard_loads(LOADS_PATH)

    def test_standard_load_values_and_sources_are_preserved(self):
        load = self.library["concrete_bucket_1"]
        self.assertEqual((load.load_kg, load.rigging_kg, load.rigging_height_m), (2500.0, 300.0, 1.5))
        self.assertEqual(load.sources[0].kind, SourceKind.ASSUMPTION)
        self.assertTrue(load.sources[0].note)

    def test_user_overrides_create_project_source_without_mutating_library(self):
        request = make_request(load_overrides={"load_kg": 2700.0})
        operation = build_operations((request,), self.library)[0]
        self.assertEqual(operation.load.load_kg, 2700.0)
        self.assertEqual(self.library["concrete_bucket_1"].load_kg, 2500.0)
        self.assertEqual(operation.load.sources[-1].kind, SourceKind.PROJECT)

    def test_unknown_load_id_returns_unknown_load_template(self):
        with self.assertRaises(OperationBuildError) as caught:
            build_operations((make_request(load_template_id="missing"),), self.library)
        self.assertEqual(caught.exception.code, "UNKNOWN_LOAD_TEMPLATE")

    def test_unknown_stage_returns_unknown_stage(self):
        operation = build_operations((make_request(stage_id="MISSING"),), self.library)[0]
        stage = ConstructionStage("STAGE-1", "Stage", 1, 10, 18.0, (PROJECT_SOURCE,))
        site = SiteGeometry(
            ((0, 0), (40, 0), (40, 40), (0, 40)),
            ((10, 10), (30, 10), (30, 30), (10, 30)),
            (),
            2.0,
            20.0,
            (PROJECT_SOURCE,),
        )
        project = ProjectV3("P", "P", "Moscow", (stage,), site, (operation,), "RF", "test")
        self.assertIn("UNKNOWN_STAGE", {issue.code for issue in validate_operations(project)})

    def test_zero_or_negative_lift_count_returns_invalid_lift_count(self):
        for count in (0, -1):
            with self.subTest(count):
                with self.assertRaises(OperationBuildError) as caught:
                    build_operations((make_request(count=count),), self.library)
                self.assertEqual(caught.exception.code, "INVALID_LIFT_COUNT")

    def test_operation_identifiers_are_deterministic_for_identical_requests(self):
        first = build_operations((make_request(),), self.library)[0]
        second = build_operations((make_request(),), self.library)[0]
        self.assertEqual(first.id, second.id)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
