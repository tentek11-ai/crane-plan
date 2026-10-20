from __future__ import annotations

from dataclasses import replace
import unittest

from crane_plan.engine.catalog import CapacityPoint, CraneConfigurationV3
from crane_plan.engine.domain import (
    ConstructionStage,
    CranePlacementV3,
    LiftEndpoint,
    LiftingOperation,
    LoadSpec,
    OperationAssignment,
    ProjectSolutionV3,
    ProjectV3,
    SiteGeometry,
    SourceKind,
    SourceLocator,
    StageSolutionV3,
)
from crane_plan.engine.service import EngineRequestV21, run_engine_v21
from crane_plan.engine.verification import VerificationStatus


PROJECT_SOURCE = SourceLocator(SourceKind.PROJECT, "PLAN", "sheet 1")
PASSPORT_SOURCE = SourceLocator(SourceKind.PASSPORT, "CRANE", "p. 2", sha256="a" * 64)


def make_case() -> tuple[ProjectV3, CraneConfigurationV3, ProjectSolutionV3]:
    load = LoadSpec("L", "Load", 5000, 200, 2, 1, 2, 1.5, (PROJECT_SOURCE,))
    operation = LiftingOperation("OP", "Lift", "S", LiftEndpoint(5, 0, 0), LiftEndpoint(30, 0, 20), load, 1, (PROJECT_SOURCE,))
    project = ProjectV3(
        "P",
        "Project",
        "Moscow",
        (ConstructionStage("S", "Stage", 1, 10, 20, (PROJECT_SOURCE,)),),
        SiteGeometry(((-50, -50), (50, -50), (50, 50), (-50, 50)), ((20, -5), (40, -5), (40, 5), (20, 5)), (), 1, 50, (PROJECT_SOURCE,)),
        (operation,),
        "RF-2026",
        "catalog-3",
    )
    config = CraneConfigurationV3("CFG", "Liebherr", "Test", 1, 30, 44.4, (CapacityPoint(25, 5900), CapacityPoint(30, 5200)), (25, 30), (5,), PASSPORT_SOURCE)
    solution = ProjectSolutionV3("P", (StageSolutionV3("S", (CranePlacementV3("C", "S", "CFG", 0, 0),), (OperationAssignment("OP", "C"),)),))
    return project, config, solution


def request_for(project: ProjectV3, config: CraneConfigurationV3, solution: ProjectSolutionV3) -> EngineRequestV21:
    return EngineRequestV21(
        project=project,
        catalog=(config,),
        candidate_coordinates=((0.0, 0.0),),
        proposed_solution=solution,
        run_id="RUN-1",
        created_at="2026-10-20T10:00:00+03:00",
    )


class EngineServiceTests(unittest.TestCase):
    def test_valid_one_crane_project_returns_evaluations_verification_and_protocol(self):
        project, config, solution = make_case()
        result = run_engine_v21(request_for(project, config, solution))
        self.assertTrue(result.placement_evaluations[0].passed)
        self.assertEqual(result.verification.status, VerificationStatus.VALID)
        self.assertEqual(result.accepted_solution, solution)
        self.assertIsNotNone(result.protocol)

    def test_insufficient_capacity_returns_no_solution_and_measured_values(self):
        project, config, solution = make_case()
        changed_load = replace(project.operations[0].load, load_kg=6000)
        project = replace(project, operations=(replace(project.operations[0], load=changed_load),))
        result = run_engine_v21(request_for(project, config, solution))
        self.assertIsNone(result.accepted_solution)
        checks = [check for check in result.verification.checks if check.code == "CAPACITY_INSUFFICIENT"]
        self.assertEqual((checks[0].measured_value, checks[0].limit), (6200, 5200))

    def test_incomplete_source_evidence_cannot_be_promoted_to_valid(self):
        project, config, solution = make_case()
        assumption = SourceLocator(SourceKind.ASSUMPTION, "", "", note="Needs confirmation")
        changed_load = replace(project.operations[0].load, sources=(assumption,))
        project = replace(project, operations=(replace(project.operations[0], load=changed_load),))
        result = run_engine_v21(request_for(project, config, solution))
        self.assertEqual(result.verification.status, VerificationStatus.EXPERT_REVIEW_REQUIRED)
        self.assertIsNone(result.accepted_solution)

    def test_candidate_and_configuration_order_are_deterministic(self):
        project, config, solution = make_case()
        second = replace(config, id="CFG-2", priority=2)
        first_request = replace(request_for(project, config, solution), catalog=(second, config), candidate_coordinates=((1, 0), (0, 0)))
        second_request = replace(first_request, catalog=(config, second), candidate_coordinates=((0, 0), (1, 0)))
        first = run_engine_v21(first_request)
        second_result = run_engine_v21(second_request)
        self.assertEqual(first.placement_evaluations, second_result.placement_evaluations)
        self.assertEqual(first.protocol.input_sha256, second_result.protocol.input_sha256)
        self.assertEqual(first.protocol.result_sha256, second_result.protocol.result_sha256)


if __name__ == "__main__":
    unittest.main()
