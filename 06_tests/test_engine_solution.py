from __future__ import annotations

from dataclasses import replace
import unittest

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
    validate_solution_structure,
)


SOURCE = SourceLocator(SourceKind.PROJECT, "PLAN", "sheet 1")


def make_project() -> ProjectV3:
    load = LoadSpec("L", "Load", 1000, 100, 1, 1, 1, 1.5, (SOURCE,))
    stages = (
        ConstructionStage("S1", "One", 1, 10, 10, (SOURCE,)),
        ConstructionStage("S2", "Two", 11, 20, 20, (SOURCE,)),
    )
    operations = (
        LiftingOperation("OP1", "One", "S1", LiftEndpoint(0, 0, 0), LiftEndpoint(10, 0, 10), load, 1, (SOURCE,)),
        LiftingOperation("OP2", "Two", "S2", LiftEndpoint(0, 0, 0), LiftEndpoint(10, 0, 20), load, 1, (SOURCE,)),
    )
    site = SiteGeometry(
        ((-50, -50), (50, -50), (50, 50), (-50, 50)),
        ((10, -5), (20, -5), (20, 5), (10, 5)),
        (),
        1,
        30,
        (SOURCE,),
    )
    return ProjectV3("P", "Project", "Moscow", stages, site, operations, "RF", "test")


def make_solution() -> ProjectSolutionV3:
    return ProjectSolutionV3(
        "P",
        (
            StageSolutionV3("S1", (CranePlacementV3("C1", "S1", "CFG", 0, 0),), (OperationAssignment("OP1", "C1"),)),
            StageSolutionV3("S2", (CranePlacementV3("C2", "S2", "CFG", 0, 0),), (OperationAssignment("OP2", "C2"),)),
        ),
    )


class SolutionStructureTests(unittest.TestCase):
    def test_every_operation_is_assigned_exactly_once(self):
        project = make_project()
        solution = make_solution()
        self.assertEqual(validate_solution_structure(project, solution), ())

        missing = replace(solution, stages=(replace(solution.stages[0], assignments=()), solution.stages[1]))
        self.assertIn("ASSIGNMENT_MISSING", {issue.code for issue in validate_solution_structure(project, missing)})

        duplicate_assignment = replace(
            solution.stages[0],
            assignments=(OperationAssignment("OP1", "C1"), OperationAssignment("OP1", "C1")),
        )
        duplicate = replace(solution, stages=(duplicate_assignment, solution.stages[1]))
        self.assertIn("ASSIGNMENT_DUPLICATE", {issue.code for issue in validate_solution_structure(project, duplicate)})

    def test_assignments_reference_existing_operations_and_placements(self):
        solution = make_solution()
        broken_stage = replace(
            solution.stages[0],
            assignments=(OperationAssignment("MISSING", "NO-CRANE"),),
        )
        codes = {issue.code for issue in validate_solution_structure(make_project(), replace(solution, stages=(broken_stage, solution.stages[1])))}
        self.assertIn("UNKNOWN_OPERATION", codes)
        self.assertIn("UNKNOWN_PLACEMENT", codes)

    def test_duplicate_placement_ids_are_blocked(self):
        solution = make_solution()
        duplicate = replace(solution.stages[1].placements[0], id="C1")
        codes = {
            issue.code
            for issue in validate_solution_structure(
                make_project(), replace(solution, stages=(solution.stages[0], replace(solution.stages[1], placements=(duplicate,))))
            )
        }
        self.assertIn("DUPLICATE_ID", codes)

    def test_stage_solution_cannot_claim_a_different_stage(self):
        solution = make_solution()
        wrong = replace(solution.stages[0].placements[0], stage_id="S2")
        changed = replace(solution, stages=(replace(solution.stages[0], placements=(wrong,)), solution.stages[1]))
        self.assertIn("STAGE_MISMATCH", {issue.code for issue in validate_solution_structure(make_project(), changed)})

    def test_serialization_order_is_deterministic(self):
        solution = make_solution()
        reversed_solution = replace(solution, stages=tuple(reversed(solution.stages)))
        self.assertEqual(solution.to_dict(), reversed_solution.to_dict())
        self.assertEqual([stage["stage_id"] for stage in solution.to_dict()["stages"]], ["S1", "S2"])


if __name__ == "__main__":
    unittest.main()
