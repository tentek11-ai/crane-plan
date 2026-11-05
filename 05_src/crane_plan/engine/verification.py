"""Independent verification of a proposed crane solution.

This module deliberately does not import the candidate constraint evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import atan2, cos, degrees, hypot, pi, sin
from typing import Mapping

from crane_plan.geometry import (
    circle_inside_polygon,
    distance_to_polygon,
    distance_point_to_segment,
    distance_arc_to_segment,
    distance_segment_to_segment,
    arc_intersects_polygon_exact,
    arc_inside_polygon_with_clearance,
    point_in_polygon,
    sector_intersects_polygon_exact,
    segment_intersects_polygon_exact,
    segment_inside_polygon_with_clearance,
    segment_intersects_polygon,
    segments_intersect,
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
    RestrictedZoneTypeV3,
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


def _circle_polygon(center, radius: float, sides: int = 48):
    return tuple(
        (center[0] + radius * cos(2 * pi * index / sides), center[1] + radius * sin(2 * pi * index / sides))
        for index in range(sides)
    )


def _segment_buffer_polygon(start, end, radius: float = 1e-6):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = hypot(dx, dy)
    if length <= EPS:
        return ((start[0] - radius, start[1] - radius), (start[0] + radius, start[1] - radius),
                (start[0] + radius, start[1] + radius), (start[0] - radius, start[1] + radius))
    nx, ny = -dy / length * radius, dx / length * radius
    return ((start[0] + nx, start[1] + ny), (end[0] + nx, end[1] + ny),
            (end[0] - nx, end[1] - ny), (start[0] - nx, start[1] - ny))


def _vertical_conflict(bottom_a: float, height_a: float, bottom_b: float, height_b: float, clearance: float = 1.0) -> bool:
    return not (bottom_a + height_a + clearance <= bottom_b + EPS or bottom_b + height_b + clearance <= bottom_a + EPS)


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
    operation_routes = {
        (route.operation_id, route.placement_id): route for route in solution.operation_routes
    }
    for stage_solution in sorted(solution.stages, key=lambda item: item.stage_id):
        placements = {placement.id: placement for placement in stage_solution.placements}
        assignments_by_placement: dict[str, list[str]] = {identifier: [] for identifier in placements}
        for assignment in stage_solution.assignments:
            if assignment.placement_id in assignments_by_placement and assignment.operation_id in operations:
                assignments_by_placement[assignment.placement_id].append(assignment.operation_id)

        def jib_segments(placement):
            config=configurations.get(placement.configuration_id)
            if config is None:return []
            result=[]; center=(placement.x_m,placement.y_m)
            for route in solution.operation_routes:
                if route.placement_id!=placement.id:continue
                for waypoint in route.waypoints:
                    dx=waypoint.x_m-center[0]; dy=waypoint.y_m-center[1]; radius=hypot(dx,dy)
                    if radius<=EPS:continue
                    result.append((center,(center[0]+dx/radius*config.jib_length_m,center[1]+dy/radius*config.jib_length_m)))
            return result

        def continuous_pair_conflict(moving, fixed) -> str:
            moving_config = configurations.get(moving.configuration_id)
            if moving_config is None:
                return ""
            center = (moving.x_m, moving.y_m)
            fixed_segments = jib_segments(fixed)
            for route in solution.operation_routes:
                if route.placement_id != moving.id:
                    continue
                operation = operations.get(route.operation_id)
                for start, end in zip(route.waypoints, route.waypoints[1:]):
                    start_point = (start.x_m, start.y_m); end_point = (end.x_m, end.y_m)
                    start_angle = degrees(atan2(start.y_m-center[1], start.x_m-center[0])) % 360.0
                    end_angle = degrees(atan2(end.y_m-center[1], end.x_m-center[0])) % 360.0
                    clockwise = ((start_angle-end_angle)%360.0) < ((end_angle-start_angle)%360.0)
                    if end.movement == "slew" and sector_intersects_polygon_exact(
                        center, moving_config.jib_length_m, start_angle, end_angle, clockwise,
                        list(_circle_polygon((fixed.x_m, fixed.y_m), 2.0)),
                    ):
                        return f"башня {fixed.id}–стрела {moving.id} на секторе поворота"
                    if moving.jib_bottom_m is not None and fixed.jib_bottom_m is not None and _vertical_conflict(
                        moving.jib_bottom_m, 2.0, fixed.jib_bottom_m, 2.0
                    ):
                        for fixed_start, fixed_end in fixed_segments:
                            if end.movement == "slew" and sector_intersects_polygon_exact(
                                center, moving_config.jib_length_m, start_angle, end_angle, clockwise,
                                list(_segment_buffer_polygon(fixed_start, fixed_end)),
                            ):
                                return f"стрела {moving.id}–стрела {fixed.id} на секторе поворота"
                    if operation is None or fixed.jib_bottom_m is None:
                        continue
                    load_bottom = min(start.hook_height_m, end.hook_height_m) - operation.load.rigging_height_m - operation.load.height_m
                    if not _vertical_conflict(load_bottom, operation.load.height_m, fixed.jib_bottom_m, 2.0):
                        continue
                    load_radius = max(operation.load.length_m, operation.load.width_m) / 2.0
                    for fixed_start, fixed_end in fixed_segments:
                        separation = (
                            distance_arc_to_segment(center, hypot(start.x_m-center[0], start.y_m-center[1]), start_angle, end_angle, clockwise, fixed_start, fixed_end)
                            if end.movement == "slew" else
                            distance_segment_to_segment(start_point, end_point, fixed_start, fixed_end)
                        )
                        if separation <= load_radius + EPS:
                            return f"груз {moving.id}–стрела {fixed.id} на участке маршрута"
            return ""

        placement_list=[placements[key] for key in sorted(placements)]
        for first_index,first in enumerate(placement_list):
            for second in placement_list[first_index+1:]:
                first_segments=jib_segments(first); second_segments=jib_segments(second)
                first_center=(first.x_m,first.y_m); second_center=(second.x_m,second.y_m)
                conflict=""
                if any(distance_point_to_segment(second_center,*segment)<=2.0+EPS for segment in first_segments):
                    conflict=f"башня {second.id}–стрела {first.id}"
                elif any(distance_point_to_segment(first_center,*segment)<=2.0+EPS for segment in second_segments):
                    conflict=f"башня {first.id}–стрела {second.id}"
                elif first.jib_bottom_m is not None and second.jib_bottom_m is not None:
                    first_top=first.jib_bottom_m+2.0; second_top=second.jib_bottom_m+2.0
                    vertical_clear=first_top+1.0<=second.jib_bottom_m+EPS or second_top+1.0<=first.jib_bottom_m+EPS
                    if not vertical_clear and any(segments_intersect(*a,*b) for a in first_segments for b in second_segments):
                        conflict=f"стрела {first.id}–стрела {second.id}"
                if not conflict:
                    conflict = continuous_pair_conflict(first, second) or continuous_pair_conflict(second, first)
                record(
                    "SECOND_CRANE_CONFLICT",
                    not conflict,
                    conflict or "clear",
                    "башня вне сектора стрелы; между стрелами не менее 1 м",
                    "",
                    None,
                    f"{first.id}/{second.id}",
                    project.site.sources,
                )

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
            zone_conflict = any(point_in_polygon(point, list(zone.buffered_polygon)) for zone in project.site.restricted_zones)
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
                route = operation_routes.get((operation.id, placement.id))
                if route is None:
                    route_conflict = any(
                        segment_intersects_polygon(source_point, destination_point, list(zone.buffered_polygon))
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
                else:
                    route_clear = True
                    measured = "verified"
                    first = route.waypoints[0]
                    last = route.waypoints[-1]
                    endpoint_tolerance = max(project.route_settings.radius_step_m, 0.05) + EPS
                    if hypot(first.x_m - source_point[0], first.y_m - source_point[1]) > endpoint_tolerance or hypot(
                        last.x_m - destination_point[0], last.y_m - destination_point[1]
                    ) > endpoint_tolerance:
                        route_clear = False
                        measured = "route endpoints differ from operation"
                    for waypoint in route.waypoints:
                        waypoint_radius = hypot(waypoint.x_m - point[0], waypoint.y_m - point[1])
                        if (
                            waypoint_radius > config.jib_length_m + EPS
                            or conservative_capacity_kg(config, waypoint_radius) + EPS < operation.load.total_kg
                            or waypoint.hook_height_m > config.max_free_standing_hook_height_m + EPS
                            or not point_in_polygon((waypoint.x_m, waypoint.y_m), list(project.site.boundary))
                        ):
                            route_clear = False
                            measured = "waypoint violates reach, capacity, height, or site boundary"
                            break
                    load_below_hook = operation.load.rigging_height_m + operation.load.height_m
                    for start, end in zip(route.waypoints, route.waypoints[1:]):
                        if not route_clear:
                            break
                        load_bottom = min(start.hook_height_m, end.hook_height_m) - load_below_hook
                        start_point = (start.x_m, start.y_m)
                        end_point = (end.x_m, end.y_m)
                        start_angle = degrees(atan2(start.y_m - point[1], start.x_m - point[0])) % 360.0
                        end_angle = degrees(atan2(end.y_m - point[1], end.x_m - point[0])) % 360.0
                        clockwise = ((start_angle - end_angle) % 360.0) < ((end_angle - start_angle) % 360.0)
                        for zone in project.site.restricted_zones:
                            polygon = list(zone.buffered_polygon)
                            load_active = zone.kind in {
                                RestrictedZoneTypeV3.LOAD_PROHIBITED,
                                RestrictedZoneTypeV3.FULL_EXCLUSION,
                            } or load_bottom + EPS < zone.height_m + project.route_settings.vertical_clearance_m
                            jib_active = zone.kind is RestrictedZoneTypeV3.FULL_EXCLUSION or (
                                placement.jib_bottom_m is not None
                                and placement.jib_bottom_m + EPS
                                < zone.height_m + project.route_settings.vertical_clearance_m
                            )
                            if end.movement == "slew":
                                load_collision = load_active and arc_intersects_polygon_exact(
                                    point,
                                    hypot(start.x_m - point[0], start.y_m - point[1]),
                                    start_angle,
                                    end_angle,
                                    clockwise,
                                    polygon,
                                )
                                jib_collision = jib_active and sector_intersects_polygon_exact(
                                    point,
                                    config.jib_length_m,
                                    start_angle,
                                    end_angle,
                                    clockwise,
                                    polygon,
                                )
                            else:
                                load_collision = load_active and segment_intersects_polygon_exact(
                                    start_point, end_point, polygon
                                )
                                jib_collision = False
                            if load_collision or jib_collision:
                                route_clear = False
                                measured = f"conflict with zone {zone.id}"
                                break
                    record(
                        "ROUTE_EXACT_CLEAR",
                        route_clear,
                        measured,
                        "all route edges exactly verified",
                        "",
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
                if route is not None:
                    route_danger_inside = True
                    boundary = list(project.site.boundary)
                    for start, end in zip(route.waypoints, route.waypoints[1:]):
                        start_point = (start.x_m, start.y_m)
                        end_point = (end.x_m, end.y_m)
                        if end.movement == "slew":
                            start_angle = degrees(atan2(start.y_m - point[1], start.x_m - point[0])) % 360.0
                            end_angle = degrees(atan2(end.y_m - point[1], end.x_m - point[0])) % 360.0
                            clockwise = ((start_angle - end_angle) % 360.0) < ((end_angle - start_angle) % 360.0)
                            edge_inside = arc_inside_polygon_with_clearance(
                                point,
                                hypot(start.x_m - point[0], start.y_m - point[1]),
                                start_angle,
                                end_angle,
                                clockwise,
                                boundary,
                                danger_offset_m,
                            )
                        else:
                            edge_inside = segment_inside_polygon_with_clearance(
                                start_point, end_point, boundary, danger_offset_m
                            )
                        if not edge_inside:
                            route_danger_inside = False
                            break
                    if route_danger_inside:
                        record(
                            "DANGER_ROUTE_INSIDE_SITE", True, danger_offset_m,
                            "swept envelope inside site boundary", "m",
                            operation.id, placement.id, operation_sources + project.site.sources,
                        )
                    elif permitted_screen:
                        record(
                            "DANGER_ROUTE_PROTECTED", True, danger_offset_m,
                            "PROTECTIVE_SCREEN", "m", operation.id, placement.id,
                            operation_sources + project.site.sources, conditional=True,
                        )
                    else:
                        record(
                            "DANGER_ROUTE_INSIDE_SITE", False, danger_offset_m,
                            "swept envelope inside site boundary", "m",
                            operation.id, placement.id, operation_sources + project.site.sources,
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
