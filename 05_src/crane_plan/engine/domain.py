"""Immutable input model and validation for calculation schema version 3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import TypeAlias


Point2D: TypeAlias = tuple[float, float]


class SourceKind(str, Enum):
    PASSPORT = "PASSPORT"
    NORMATIVE = "NORMATIVE"
    PROJECT = "PROJECT"
    ASSUMPTION = "ASSUMPTION"
    MEASURED = "MEASURED"


@dataclass(frozen=True)
class SourceLocator:
    kind: SourceKind
    document_id: str
    locator: str
    note: str = ""
    sha256: str = ""


@dataclass(frozen=True)
class LiftEndpoint:
    x_m: float
    y_m: float
    z_m: float


@dataclass(frozen=True)
class LoadSpec:
    id: str
    name: str
    load_kg: float
    rigging_kg: float
    length_m: float
    width_m: float
    height_m: float
    rigging_height_m: float
    sources: tuple[SourceLocator, ...]

    @property
    def total_kg(self) -> float:
        return self.load_kg + self.rigging_kg

    @property
    def largest_dimension_m(self) -> float:
        return max(self.length_m, self.width_m, self.height_m)


@dataclass(frozen=True)
class ConstructionStage:
    id: str
    name: str
    start_day: int
    end_day: int
    mounting_level_m: float
    sources: tuple[SourceLocator, ...]


@dataclass(frozen=True)
class LiftingOperation:
    id: str
    name: str
    stage_id: str
    source: LiftEndpoint
    destination: LiftEndpoint
    load: LoadSpec
    count: int
    sources: tuple[SourceLocator, ...]


@dataclass(frozen=True)
class SiteGeometry:
    boundary: tuple[Point2D, ...]
    building: tuple[Point2D, ...]
    restricted_zones: tuple[tuple[Point2D, ...], ...]
    min_crane_to_building_m: float
    max_crane_to_building_m: float
    sources: tuple[SourceLocator, ...]


@dataclass(frozen=True)
class ProjectV3:
    project_id: str
    name: str
    city: str
    stages: tuple[ConstructionStage, ...]
    site: SiteGeometry
    operations: tuple[LiftingOperation, ...]
    normative_profile_id: str
    catalog_version: str
    schema_version: int = 3


@dataclass(frozen=True)
class InputIssue:
    code: str
    path: str
    message: str
    blocking: bool = True


@dataclass(frozen=True)
class CranePlacementV3:
    id: str
    stage_id: str
    configuration_id: str
    x_m: float
    y_m: float
    protective_measures: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationAssignment:
    operation_id: str
    placement_id: str


@dataclass(frozen=True)
class StageSolutionV3:
    stage_id: str
    placements: tuple[CranePlacementV3, ...]
    assignments: tuple[OperationAssignment, ...]


@dataclass(frozen=True)
class ProjectSolutionV3:
    project_id: str
    stages: tuple[StageSolutionV3, ...]
    schema_version: int = 3
    engine_version: str = "2.1"

    def to_dict(self) -> dict[str, object]:
        """Return a canonical representation suitable for hashing and JSON."""

        stage_rows: list[dict[str, object]] = []
        for stage in sorted(self.stages, key=lambda item: item.stage_id):
            placements = [
                {
                    "id": placement.id,
                    "stage_id": placement.stage_id,
                    "configuration_id": placement.configuration_id,
                    "x_m": placement.x_m,
                    "y_m": placement.y_m,
                    "protective_measures": sorted(placement.protective_measures),
                }
                for placement in sorted(stage.placements, key=lambda item: item.id)
            ]
            assignments = [
                {"operation_id": assignment.operation_id, "placement_id": assignment.placement_id}
                for assignment in sorted(
                    stage.assignments,
                    key=lambda item: (item.operation_id, item.placement_id),
                )
            ]
            stage_rows.append(
                {
                    "stage_id": stage.stage_id,
                    "placements": placements,
                    "assignments": assignments,
                }
            )
        return {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "project_id": self.project_id,
            "stages": stage_rows,
        }


def _is_finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _source_issues(sources: tuple[SourceLocator, ...], path: str) -> list[InputIssue]:
    issues: list[InputIssue] = []
    if not sources:
        return [InputIssue("SOURCE_REQUIRED", path, "At least one source locator is required.")]
    for index, source in enumerate(sources):
        valid = bool(source.note.strip()) if source.kind == SourceKind.ASSUMPTION else bool(
            source.document_id.strip() and source.locator.strip()
        )
        if not valid:
            issues.append(
                InputIssue(
                    "SOURCE_REQUIRED",
                    f"{path}[{index}]",
                    "A document and locator are required; an assumption requires an explanatory note.",
                )
            )
    return issues


def _finite_issue(value: object, path: str) -> InputIssue | None:
    if _is_finite(value):
        return None
    return InputIssue("NON_FINITE_VALUE", path, "Value must be a finite number.")


def _validate_unique_ids(items: tuple[object, ...], path: str) -> list[InputIssue]:
    issues: list[InputIssue] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        identifier = str(getattr(item, "id", ""))
        if identifier in seen:
            issues.append(InputIssue("DUPLICATE_ID", f"{path}[{index}].id", f"Duplicate id: {identifier}"))
        seen.add(identifier)
    return issues


def validate_project(project: ProjectV3) -> tuple[InputIssue, ...]:
    """Return every blocking input defect in stable traversal order."""

    issues: list[InputIssue] = []
    issues.extend(_validate_unique_ids(project.stages, "stages"))
    issues.extend(_validate_unique_ids(project.operations, "operations"))

    for index, stage in enumerate(project.stages):
        issue = _finite_issue(stage.mounting_level_m, f"stages[{index}].mounting_level_m")
        if issue:
            issues.append(issue)
        issues.extend(_source_issues(stage.sources, f"stages[{index}].sources"))

    for index, operation in enumerate(project.operations):
        prefix = f"operations[{index}]"
        for endpoint_name, endpoint in (("source", operation.source), ("destination", operation.destination)):
            for axis in ("x_m", "y_m", "z_m"):
                issue = _finite_issue(getattr(endpoint, axis), f"{prefix}.{endpoint_name}.{axis}")
                if issue:
                    issues.append(issue)

        load = operation.load
        for name in ("load_kg", "rigging_kg"):
            value = getattr(load, name)
            issue = _finite_issue(value, f"{prefix}.load.{name}")
            if issue:
                issues.append(issue)
            elif value < 0:
                issues.append(InputIssue("NEGATIVE_MASS", f"{prefix}.load.{name}", "Mass cannot be negative."))
        for name in ("length_m", "width_m", "height_m", "rigging_height_m"):
            value = getattr(load, name)
            issue = _finite_issue(value, f"{prefix}.load.{name}")
            if issue:
                issues.append(issue)
            elif value <= 0:
                issues.append(
                    InputIssue("NON_POSITIVE_DIMENSION", f"{prefix}.load.{name}", "Dimension must be positive.")
                )
        issues.extend(_source_issues(load.sources, f"{prefix}.load.sources"))
        issues.extend(_source_issues(operation.sources, f"{prefix}.sources"))

    site = project.site
    for name in ("min_crane_to_building_m", "max_crane_to_building_m"):
        issue = _finite_issue(getattr(site, name), f"site.{name}")
        if issue:
            issues.append(issue)
    for polygon_name, polygons in (
        ("boundary", (site.boundary,)),
        ("building", (site.building,)),
        ("restricted_zones", site.restricted_zones),
    ):
        for polygon_index, polygon in enumerate(polygons):
            base = f"site.{polygon_name}" if polygon_name != "restricted_zones" else f"site.{polygon_name}[{polygon_index}]"
            for point_index, point in enumerate(polygon):
                for axis_index, axis in enumerate(("x_m", "y_m")):
                    issue = _finite_issue(point[axis_index], f"{base}[{point_index}].{axis}")
                    if issue:
                        issues.append(issue)
    issues.extend(_source_issues(site.sources, "site.sources"))
    return tuple(issues)


def validate_solution_structure(
    project: ProjectV3,
    solution: ProjectSolutionV3,
) -> tuple[InputIssue, ...]:
    """Check referential integrity without evaluating engineering constraints."""

    issues: list[InputIssue] = []
    if solution.project_id != project.project_id:
        issues.append(InputIssue("PROJECT_MISMATCH", "project_id", "Solution belongs to a different project."))

    operations = {operation.id: operation for operation in project.operations}
    stage_ids = {stage.id for stage in project.stages}
    placement_ids: set[str] = set()
    assignment_counts = {operation_id: 0 for operation_id in operations}

    seen_solution_stages: set[str] = set()
    for stage_index, stage_solution in enumerate(solution.stages):
        stage_path = f"stages[{stage_index}]"
        if stage_solution.stage_id in seen_solution_stages:
            issues.append(InputIssue("DUPLICATE_ID", f"{stage_path}.stage_id", f"Duplicate stage solution: {stage_solution.stage_id}"))
        seen_solution_stages.add(stage_solution.stage_id)
        if stage_solution.stage_id not in stage_ids:
            issues.append(InputIssue("UNKNOWN_STAGE", f"{stage_path}.stage_id", f"Unknown stage: {stage_solution.stage_id}"))

        local_placement_ids: set[str] = set()
        for placement_index, placement in enumerate(stage_solution.placements):
            placement_path = f"{stage_path}.placements[{placement_index}]"
            if placement.id in placement_ids:
                issues.append(InputIssue("DUPLICATE_ID", f"{placement_path}.id", f"Duplicate placement id: {placement.id}"))
            placement_ids.add(placement.id)
            local_placement_ids.add(placement.id)
            if placement.stage_id != stage_solution.stage_id:
                issues.append(
                    InputIssue(
                        "STAGE_MISMATCH",
                        f"{placement_path}.stage_id",
                        "Placement stage differs from its stage solution.",
                    )
                )

        for assignment_index, assignment in enumerate(stage_solution.assignments):
            assignment_path = f"{stage_path}.assignments[{assignment_index}]"
            operation = operations.get(assignment.operation_id)
            if operation is None:
                issues.append(
                    InputIssue(
                        "UNKNOWN_OPERATION",
                        f"{assignment_path}.operation_id",
                        f"Unknown operation: {assignment.operation_id}",
                    )
                )
            else:
                assignment_counts[operation.id] += 1
                if operation.stage_id != stage_solution.stage_id:
                    issues.append(
                        InputIssue(
                            "STAGE_MISMATCH",
                            f"{assignment_path}.operation_id",
                            "Operation is assigned in a different stage.",
                        )
                    )
            if assignment.placement_id not in local_placement_ids:
                issues.append(
                    InputIssue(
                        "UNKNOWN_PLACEMENT",
                        f"{assignment_path}.placement_id",
                        f"Unknown placement in this stage: {assignment.placement_id}",
                    )
                )

    for operation_id in sorted(assignment_counts):
        count = assignment_counts[operation_id]
        if count == 0:
            issues.append(InputIssue("ASSIGNMENT_MISSING", f"operations[{operation_id}]", "Operation is not assigned."))
        elif count > 1:
            issues.append(
                InputIssue("ASSIGNMENT_DUPLICATE", f"operations[{operation_id}]", "Operation is assigned more than once.")
            )
    return tuple(issues)
