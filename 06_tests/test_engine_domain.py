from __future__ import annotations

from dataclasses import replace
import math
import unittest

from crane_plan.engine.domain import (
    ConstructionStage,
    LiftEndpoint,
    LiftingOperation,
    LoadSpec,
    ProjectV3,
    SiteGeometry,
    SourceKind,
    SourceLocator,
    validate_project,
)


PROJECT_SOURCE = SourceLocator(
    kind=SourceKind.PROJECT,
    document_id="plan-01",
    locator="sheet 1",
)
ASSUMPTION_SOURCE = SourceLocator(
    kind=SourceKind.ASSUMPTION,
    document_id="",
    locator="",
    note="Temporary value confirmed by the engineer",
)


def make_project() -> ProjectV3:
    load = LoadSpec(
        id="LOAD-1",
        name="Concrete bucket",
        load_kg=2000.0,
        rigging_kg=150.0,
        length_m=2.0,
        width_m=1.5,
        height_m=2.5,
        rigging_height_m=1.0,
        sources=(PROJECT_SOURCE,),
    )
    stage = ConstructionStage(
        id="STAGE-1",
        name="Monolithic frame",
        start_day=1,
        end_day=30,
        mounting_level_m=24.0,
        sources=(PROJECT_SOURCE,),
    )
    operation = LiftingOperation(
        id="OP-1",
        name="Supply concrete",
        stage_id=stage.id,
        source=LiftEndpoint(5.0, 5.0, 0.0),
        destination=LiftEndpoint(20.0, 10.0, 24.0),
        load=load,
        count=20,
        sources=(PROJECT_SOURCE,),
    )
    site = SiteGeometry(
        boundary=((0.0, 0.0), (50.0, 0.0), (50.0, 40.0), (0.0, 40.0)),
        building=((15.0, 10.0), (35.0, 10.0), (35.0, 30.0), (15.0, 30.0)),
        restricted_zones=(),
        min_crane_to_building_m=2.0,
        max_crane_to_building_m=20.0,
        sources=(PROJECT_SOURCE,),
    )
    return ProjectV3(
        project_id="PROJECT-1",
        name="Test project",
        city="Moscow",
        stages=(stage,),
        site=site,
        operations=(operation,),
        normative_profile_id="RF-2026",
        catalog_version="3.0-test",
    )


class DomainValidationTests(unittest.TestCase):
    def test_valid_project_has_no_input_issues(self):
        self.assertEqual(validate_project(make_project()), ())

    def test_nan_infinity_and_negative_mass_are_blocked(self):
        project = make_project()
        bad_load = replace(project.operations[0].load, load_kg=-1.0, rigging_kg=math.inf)
        bad_operation = replace(
            project.operations[0],
            load=bad_load,
            destination=LiftEndpoint(math.nan, 10.0, 24.0),
        )
        issues = validate_project(replace(project, operations=(bad_operation,)))
        self.assertIn("NON_FINITE_VALUE", {issue.code for issue in issues})
        self.assertIn("NEGATIVE_MASS", {issue.code for issue in issues})

    def test_non_positive_load_dimension_is_blocked(self):
        project = make_project()
        bad_load = replace(project.operations[0].load, width_m=0.0)
        issues = validate_project(
            replace(project, operations=(replace(project.operations[0], load=bad_load),))
        )
        self.assertIn("NON_POSITIVE_DIMENSION", {issue.code for issue in issues})

    def test_duplicate_operation_and_stage_ids_are_blocked(self):
        project = make_project()
        issues = validate_project(
            replace(
                project,
                stages=project.stages + (replace(project.stages[0], name="Duplicate"),),
                operations=project.operations
                + (replace(project.operations[0], name="Duplicate"),),
            )
        )
        duplicate_paths = [issue.path for issue in issues if issue.code == "DUPLICATE_ID"]
        self.assertEqual(duplicate_paths, ["stages[1].id", "operations[1].id"])

    def test_missing_source_locator_is_blocked_unless_assumption(self):
        project = make_project()
        missing = SourceLocator(kind=SourceKind.PROJECT, document_id="", locator="")
        bad_load = replace(project.operations[0].load, sources=(missing, ASSUMPTION_SOURCE))
        issues = validate_project(
            replace(project, operations=(replace(project.operations[0], load=bad_load),))
        )
        source_issues = [issue for issue in issues if issue.code == "SOURCE_REQUIRED"]
        self.assertEqual(len(source_issues), 1)
        self.assertEqual(source_issues[0].path, "operations[0].load.sources[0]")


if __name__ == "__main__":
    unittest.main()
