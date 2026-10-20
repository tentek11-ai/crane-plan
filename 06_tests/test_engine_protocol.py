from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest

from crane_plan.engine.catalog import CapacityPoint, CraneConfigurationV3
from crane_plan.engine.constraints import ConstraintCode, OperationEvaluation, PlacementEvaluation
from crane_plan.engine.domain import (
    ConstructionStage,
    LiftEndpoint,
    LiftingOperation,
    LoadSpec,
    ProjectSolutionV3,
    ProjectV3,
    SiteGeometry,
    SourceKind,
    SourceLocator,
)
from crane_plan.engine.protocol import build_protocol, canonical_json, save_protocol, sha256_hex
from crane_plan.engine.verification import VerificationReport, VerificationStatus


SOURCE = SourceLocator(SourceKind.PROJECT, "PLAN", "sheet 1")
PASSPORT = SourceLocator(SourceKind.PASSPORT, "CRANE", "p. 2", sha256="a" * 64)


def make_inputs() -> tuple[ProjectV3, tuple[CraneConfigurationV3, ...], tuple[PlacementEvaluation, ...]]:
    load = LoadSpec("L", "Load", 1000, 100, 1, 1, 1, 1.5, (SOURCE,))
    operation = LiftingOperation("OP", "Lift", "S", LiftEndpoint(0, 0, 0), LiftEndpoint(10, 0, 10), load, 1, (SOURCE,))
    project = ProjectV3(
        "P",
        "Project",
        "Moscow",
        (ConstructionStage("S", "Stage", 1, 10, 10, (SOURCE,)),),
        SiteGeometry(((-20, -20), (20, -20), (20, 20), (-20, 20)), ((9, -1), (11, -1), (11, 1), (9, 1)), (), 1, 20, (SOURCE,)),
        (operation,),
        "RF-2026",
        "catalog-3",
    )
    config = CraneConfigurationV3("CFG", "Liebherr", "Test", 1, 30, 44.4, (CapacityPoint(30, 5200),), (30,), (5,), PASSPORT)
    operation_evaluation = OperationEvaluation("OP", False, 31, 5200, 4100, 1100 / 5200, 13, 31.4, (ConstraintCode.REACH_EXCEEDED,))
    placement = PlacementEvaluation("S", (0, 0), "CFG", False, (operation_evaluation,), (ConstraintCode.REACH_EXCEEDED,), "OP", "OP")
    return project, (config,), (placement,)


def make_protocol(project: ProjectV3 | None = None):
    default_project, catalog, evaluations = make_inputs()
    return build_protocol(
        project or default_project,
        catalog,
        evaluations,
        ProjectSolutionV3(default_project.project_id, ()),
        VerificationReport(VerificationStatus.INVALID, ()),
        run_id="RUN-1",
        created_at="2026-10-20T10:00:00+03:00",
        duration_seconds=1.25,
        algorithm_version="2.1.0",
    )


class ProtocolTests(unittest.TestCase):
    def test_identical_hashes_across_dictionary_ordering(self):
        self.assertEqual(sha256_hex({"a": 1, "b": 2}), sha256_hex({"b": 2, "a": 1}))

    def test_repeated_runs_with_fixed_identity_have_identical_hashes(self):
        first = make_protocol()
        second = make_protocol()
        self.assertEqual(first.input_sha256, second.input_sha256)
        self.assertEqual(first.result_sha256, second.result_sha256)

    def test_changed_load_mass_changes_input_hash(self):
        project, _, _ = make_inputs()
        changed_load = replace(project.operations[0].load, load_kg=1001)
        changed_project = replace(project, operations=(replace(project.operations[0], load=changed_load),))
        self.assertNotEqual(make_protocol().input_sha256, make_protocol(changed_project).input_sha256)

    def test_algorithm_normative_and_catalog_versions_are_mandatory(self):
        project, catalog, evaluations = make_inputs()
        for changed_project, algorithm in (
            (project, ""),
            (replace(project, normative_profile_id=""), "2.1"),
            (replace(project, catalog_version=""), "2.1"),
        ):
            with self.subTest(algorithm=algorithm, project=changed_project):
                with self.assertRaises(ValueError):
                    build_protocol(
                        changed_project,
                        catalog,
                        evaluations,
                        None,
                        None,
                        run_id="R",
                        created_at="2026-10-20T10:00:00+03:00",
                        duration_seconds=0,
                        algorithm_version=algorithm,
                    )

    def test_sources_and_rejected_reason_counts_are_serialized(self):
        protocol = make_protocol()
        rendered = canonical_json(protocol)
        self.assertIn('"document_id":"PLAN"', rendered)
        self.assertEqual(protocol.rejected_reason_counts, (("REACH_EXCEEDED", 1),))
        with tempfile.TemporaryDirectory() as directory:
            path = save_protocol(Path(directory) / "protocol.json", protocol)
            self.assertEqual(path.read_text(encoding="utf-8").strip(), rendered)

    def test_nan_and_infinity_are_rejected_before_serialization(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value):
                with self.assertRaises(ValueError):
                    canonical_json({"value": value})


if __name__ == "__main__":
    unittest.main()
