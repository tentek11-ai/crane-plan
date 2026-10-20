"""Independent verification of a proposed crane solution.

This module deliberately does not import the candidate constraint evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import hypot
from typing import Mapping

from crane_plan.geometry import (
    circle_inside_polygon,
    distance_to_polygon,
    point_in_polygon,
    segment_intersects_polygon,
)
from crane_plan.normative import (
    NormativeInputError,
    danger_zone_offset_from_outer_edge,
    required_hook_height,
)

from .catalog import EPS, CraneConfigurationV3, conservative_capacity_kg, validate_capacity_curve
from .domain import (
    ProjectSolutionV3,
    ProjectV3,
    SourceKind,
    SourceLocator,
    validate_project,
    validate_solution_structure,
)
from .operations import validate_operations


class VerificationStatus(StrEnum):
    VALID = "VALID"
    VALID_WITH_CONDITIONS = "VALID_WITH_CONDITIONS"
    EXPERT_REVIEW_REQUIRED = "EXPERT_REVIEW_REQUIRED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class VerificationCheck:
    code: str
    passed: bool
    measured_value: float | str | None
    limit: float | str | None
    units: str
    operation_id: str | None
    crane_id: str | None
    sources: tuple[SourceLocator, ...]
    conditional: bool = False
    review_required: bool = False


@dataclass(frozen=True)
class VerificationReport:
    status: VerificationStatus
    checks: tuple[VerificationCheck, ...]


def _source_evidence(project: ProjectV3, configurations: Mapping[str, CraneConfigurationV3]) -> tuple[SourceLocator, ...]:
    sources: list[SourceLocator] = list(project.site.sources)
    for stage in project.stages:
        sources.extend(stage.sources)
    for operation in project.operations:
        sources.extend(operation.sources)
        sources.extend(operation.load.sources)
    for config in configurations.values():
        sources.append(config.source)
    return tuple(sources)


def verify_solution(
    project: ProjectV3,
    configurations: Mapping[str, CraneConfigurationV3],
    solution: ProjectSolutionV3,
) -> VerificationReport:
    checks: list[VerificationCheck] = []

    def record(
        code: str,
        passed: bool,
        measured: float | str | None,
        limit: float | str | None,
        units: str,
        operation_id: str | None,
        crane_id: str | None,
        sources: tuple[SourceLocator, ...],
        *,
        conditional: bool = False,
        review_required: bool = False,
    ) -> None:
        checks.append(
            VerificationCheck(
                code,
                passed,
                measured,
                limit,
                units,
                operation_id,
                crane_id,
                sources,
                conditional,
                review_required,
            )
        )

    input_issues = validate_project(project) + validate_operations(project)
    for issue in input_issues:
        record(issue.code, False, issue.path, "valid input", "", None, None, ())
    structure_issues = validate_solution_structure(project, solution)
    for issue in structure_issues:
        record(issue.code, False, issue.path, "valid solution structure", "", None, None, ())

    all_sources = _source_evidence(project, configurations)
    assumptions = tuple(source for source in all_sources if source.kind == SourceKind.ASSUMPTION)
    record(
        "SOURCE_EVIDENCE",
        not assumptions,
        len(assumptions),
        0,
        "assumption sources",
        None,
        None,
        all_sources,
        review_required=bool(assumptions),
    )

    operations = {operation.id: operation for operation in project.operations}
    for stage_solution in sorted(solution.stages, key=lambda item: item.stage_id):
        placements = {placement.id: placement for placement in stage_solution.placements}
        assignments_by_placement: dict[str, list[str]] = {identifier: [] for identifier in placements}
        for assignment in stage_solution.assignments:
            if assignment.placement_id in assignments_by_placement and assignment.operation_id in operations:
                assignments_by_placement[assignment.placement_id].append(assignment.operation_id)

        for placement_id in sorted(placements):
            placement = placements[placement_id]
            point = (placement.x_m, placement.y_m)
            config = configurations.get(placement.configuration_id)
            if config is None:
                record(
                    "CONFIGURATION_UNKNOWN",
                    False,
                    placement.configuration_id,
                    "known configuration",
                    "",
                    None,
                    placement.id,
                    (),
                )
                continue
            config_sources = (config.source,)
            supported = (
                not validate_capacity_curve(config)
                and any(abs(config.jib_length_m - value) <= EPS for value in config.allowed_jib_lengths_m)
            )
            record(
                "CONFIGURATION_SUPPORTED",
                supported,
                config.jib_length_m,
                ", ".join(str(value) for value in config.allowed_jib_lengths_m),
                "m",
                None,
                placement.id,
                config_sources,
            )
            record(
                "BASE_INSIDE_SITE",
                point_in_polygon(point, list(project.site.boundary)),
                str(point),
                "site boundary",
                "m",
                None,
                placement.id,
                project.site.sources,
            )
            record(
                "BASE_OUTSIDE_BUILDING",
                not point_in_polygon(point, list(project.site.building)),
                str(point),
                "outside building",
                "m",
                None,
                placement.id,
                project.site.sources,
            )
            zone_conflict = any(point_in_polygon(point, list(zone)) for zone in project.site.restricted_zones)
            record(
                "RESTRICTED_ZONE_CLEAR",
                not zone_conflict,
                str(point),
                "outside restricted zones",
                "m",
                None,
                placement.id,
                project.site.sources,
            )
            distance_m = distance_to_polygon(point, list(project.site.building))
            clearance_ok = (
                distance_m + EPS >= project.site.min_crane_to_building_m
                and distance_m <= project.site.max_crane_to_building_m + EPS
            )
            record(
                "BASE_CLEARANCE",
                clearance_ok,
                distance_m,
                f"{project.site.min_crane_to_building_m}..{project.site.max_crane_to_building_m}",
                "m",
                None,
                placement.id,
                project.site.sources,
            )

            permitted_screen = "PROTECTIVE_SCREEN" in placement.protective_measures
            unsupported_measures = sorted(set(placement.protective_measures) - {"PROTECTIVE_SCREEN"})
            if unsupported_measures:
                record(
                    "PROTECTIVE_MEASURE_UNSUPPORTED",
                    False,
                    ", ".join(unsupported_measures),
                    "PROTECTIVE_SCREEN",
                    "",
                    None,
                    placement.id,
                    project.site.sources,
                )

            for operation_id in sorted(assignments_by_placement[placement_id]):
                operation = operations[operation_id]
                operation_sources = operation.sources + operation.load.sources + config_sources
                source_point = (operation.source.x_m, operation.source.y_m)
                destination_point = (operation.destination.x_m, operation.destination.y_m)
                radius_m = max(hypot(source_point[0] - point[0], source_point[1] - point[1]), hypot(destination_point[0] - point[0], destination_point[1] - point[1]))
                record(
                    "REACH",
                    radius_m <= config.jib_length_m + EPS,
                    radius_m,
                    config.jib_length_m,
                    "m",
                    operation.id,
                    placement.id,
                    operation_sources,
                )
                capacity_kg = conservative_capacity_kg(config, radius_m)
                record(
                    "CAPACITY_INSUFFICIENT",
                    capacity_kg + EPS >= operation.load.total_kg,
                    operation.load.total_kg,
                    capacity_kg,
                    "kg",
                    operation.id,
                    placement.id,
                    operation_sources,
                )
                try:
                    required_height_m = required_hook_height(
                        operation.destination.z_m,
                        operation.load.height_m,
                        operation.load.rigging_height_m,
                        people_may_be_below=False,
                    )
                except NormativeInputError as exc:
                    record(
                        "NORMATIVE_INPUT_ERROR",
                        False,
                        str(exc),
                        "valid normative input",
                        "",
                        operation.id,
                        placement.id,
                        operation_sources,
                    )
                else:
                    record(
                        "HEIGHT",
                        required_height_m <= config.max_free_standing_hook_height_m + EPS,
                        required_height_m,
                        config.max_free_standing_hook_height_m,
                        "m",
                        operation.id,
                        placement.id,
                        operation_sources,
                    )
                route_conflict = any(
                    segment_intersects_polygon(source_point, destination_point, list(zone))
                    for zone in project.site.restricted_zones
                )
                record(
                    "ROUTE_CLEAR",
                    not route_conflict,
                    str((source_point, destination_point)),
                    "outside restricted zones",
                    "m",
                    operation.id,
                    placement.id,
                    operation_sources + project.site.sources,
                )
                try:
                    danger_offset_m = danger_zone_offset_from_outer_edge(
                        max(operation.source.z_m, operation.destination.z_m, EPS),
                        operation.load.largest_dimension_m,
                    )
                except NormativeInputError as exc:
                    record(
                        "NORMATIVE_INPUT_ERROR",
                        False,
                        str(exc),
                        "height within normative table",
                        "m",
                        operation.id,
                        placement.id,
                        operation_sources + project.site.sources,
                    )
                    continue
                danger_inside = circle_inside_polygon(
                    destination_point,
                    danger_offset_m,
                    list(project.site.boundary),
                )
                if danger_inside:
                    record(
                        "DANGER_ZONE_INSIDE_SITE",
                        True,
                        danger_offset_m,
                        "inside site boundary",
                        "m",
                        operation.id,
                        placement.id,
                        operation_sources + project.site.sources,
                    )
                elif permitted_screen:
                    record(
                        "DANGER_ZONE_PROTECTED",
                        True,
                        danger_offset_m,
                        "PROTECTIVE_SCREEN",
                        "m",
                        operation.id,
                        placement.id,
                        operation_sources + project.site.sources,
                        conditional=True,
                    )
                else:
                    record(
                        "DANGER_ZONE_CONFLICT",
                        False,
                        danger_offset_m,
                        "inside site boundary",
                        "m",
                        operation.id,
                        placement.id,
                        operation_sources + project.site.sources,
                    )

    hard_failure = any(not check.passed and not check.review_required for check in checks)
    if hard_failure:
        status = VerificationStatus.INVALID
    elif any(check.review_required for check in checks):
        status = VerificationStatus.EXPERT_REVIEW_REQUIRED
    elif any(check.conditional for check in checks):
        status = VerificationStatus.VALID_WITH_CONDITIONS
    else:
        status = VerificationStatus.VALID
    return VerificationReport(status, tuple(checks))
