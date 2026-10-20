from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch
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
from crane_plan.engine.verification import VerificationStatus, verify_solution


PROJECT_SOURCE = SourceLocator(SourceKind.PROJECT, "PLAN", "sheet 1")
PASSPORT_SOURCE = SourceLocator(SourceKind.PASSPORT, "CRANE", "p. 2", sha256="a" * 64)


def make_case() -> tuple[ProjectV3, dict[str, CraneConfigurationV3], ProjectSolutionV3]:
    load = LoadSpec("L", "Load", 5000, 200, 2, 1, 2, 1.5, (PROJECT_SOURCE,))
    operation = LiftingOperation(
        "OP1",
        "Lift",
        "S1",
        LiftEndpoint(5, 0, 0),
        LiftEndpoint(30, 0, 20),
        load,
        1,
        (PROJECT_SOURCE,),
    )
    project = ProjectV3(
        "P",
        "Project",
        "Moscow",
        (ConstructionStage("S1", "Stage", 1, 20, 20, (PROJECT_SOURCE,)),),
        SiteGeometry(
            ((-50, -50), (50, -50), (50, 50), (-50, 50)),
            ((20, -5), (40, -5), (40, 5), (20, 5)),
            (),
            1,
            50,
            (PROJECT_SOURCE,),
        ),
        (operation,),
        "RF",
        "test",
    )
    config = CraneConfigurationV3(
        "CFG",
        "Liebherr",
        "Test",
        1,
        30,
        44.4,
        (CapacityPoint(25, 5900), CapacityPoint(30, 5200)),
        (25, 30),
        (5,),
        PASSPORT_SOURCE,
    )
    solution = ProjectSolutionV3(
        "P",
        (StageSolutionV3("S1", (CranePlacementV3("C1", "S1", "CFG", 0, 0),), (OperationAssignment("OP1", "C1"),)),),
    )
    return project, {config.id: config}, solution


class IndependentVerifierTests(unittest.TestCase):
    def test_valid_solution_returns_valid(self):
        project, catalog, solution = make_case()
        report = verify_solution(project, catalog, solution)
        self.assertEqual(report.status, VerificationStatus.VALID)
        self.assertTrue(report.checks)
        self.assertTrue(all(check.passed for check in report.checks))

    def test_missing_source_evidence_requires_expert_review(self):
        project, catalog, solution = make_case()
        assumption = SourceLocator(SourceKind.ASSUMPTION, "", "", note="Unconfirmed project mass")
        changed_load = replace(project.operations[0].load, sources=(assumption,))
        changed_operation = replace(project.operations[0], load=changed_load)
        report = verify_solution(replace(project, operations=(changed_operation,)), catalog, solution)
        self.assertEqual(report.status, VerificationStatus.EXPERT_REVIEW_REQUIRED)

    def test_explicit_permitted_protective_measure_returns_valid_with_conditions(self):
        project, catalog, solution = make_case()
        project = replace(project, site=replace(project.site, boundary=((-40, -40), (32, -40), (32, 40), (-40, 40))))
        placement = replace(solution.stages[0].placements[0], protective_measures=("PROTECTIVE_SCREEN",))
        solution = replace(solution, stages=(replace(solution.stages[0], placements=(placement,)),))
        report = verify_solution(project, catalog, solution)
        self.assertEqual(report.status, VerificationStatus.VALID_WITH_CONDITIONS)
        self.assertIn("DANGER_ZONE_PROTECTED", {check.code for check in report.checks})

    def test_corrupted_coordinate_or_configuration_is_invalid(self):
        project, catalog, solution = make_case()
        outside = replace(solution.stages[0].placements[0], x_m=100)
        outside_solution = replace(solution, stages=(replace(solution.stages[0], placements=(outside,)),))
        self.assertEqual(verify_solution(project, catalog, outside_solution).status, VerificationStatus.INVALID)

        unknown = replace(solution.stages[0].placements[0], configuration_id="MISSING")
        unknown_solution = replace(solution, stages=(replace(solution.stages[0], placements=(unknown,)),))
        self.assertEqual(verify_solution(project, catalog, unknown_solution).status, VerificationStatus.INVALID)

    def test_verifier_catches_load_changed_after_candidate_generation(self):
        project, catalog, solution = make_case()
        changed_load = replace(project.operations[0].load, load_kg=6000)
        changed_project = replace(project, operations=(replace(project.operations[0], load=changed_load),))
        report = verify_solution(changed_project, catalog, solution)
        self.assertEqual(report.status, VerificationStatus.INVALID)
        self.assertIn("CAPACITY_INSUFFICIENT", {check.code for check in report.checks if not check.passed})

    def test_verifier_does_not_call_candidate_evaluator(self):
        project, catalog, solution = make_case()
        changed_load = replace(project.operations[0].load, load_kg=6000)
        changed_project = replace(project, operations=(replace(project.operations[0], load=changed_load),))
        with patch("crane_plan.engine.constraints.evaluate_placement", return_value=object()):
            report = verify_solution(changed_project, catalog, solution)
        self.assertEqual(report.status, VerificationStatus.INVALID)

    def test_normative_range_error_is_reported_instead_of_raised(self):
        project, catalog, solution = make_case()
        operation = replace(project.operations[0], destination=LiftEndpoint(30, 0, 451.0))
        report = verify_solution(replace(project, operations=(operation,)), catalog, solution)
        self.assertEqual(report.status, VerificationStatus.INVALID)
        self.assertIn("NORMATIVE_INPUT_ERROR", {check.code for check in report.checks if not check.passed})


if __name__ == "__main__":
    unittest.main()
