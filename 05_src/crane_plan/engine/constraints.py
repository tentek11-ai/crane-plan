"""Deterministic hard-constraint evaluation for crane placements."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from math import hypot

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

from .catalog import (
    EPS,
    CraneConfigurationV3,
    conservative_capacity_kg,
    validate_capacity_curve,
)
from .domain import LiftingOperation, Point2D, ProjectV3, validate_project
from .operations import validate_operations


class ConstraintCode(StrEnum):
    INPUT_BLOCKED = "INPUT_BLOCKED"
    BASE_OUTSIDE_SITE = "BASE_OUTSIDE_SITE"
    BASE_INSIDE_BUILDING = "BASE_INSIDE_BUILDING"
    RESTRICTED_ZONE_CONFLICT = "RESTRICTED_ZONE_CONFLICT"
    BASE_CLEARANCE_CONFLICT = "BASE_CLEARANCE_CONFLICT"
    REACH_EXCEEDED = "REACH_EXCEEDED"
    CAPACITY_INSUFFICIENT = "CAPACITY_INSUFFICIENT"
    HEIGHT_INSUFFICIENT = "HEIGHT_INSUFFICIENT"
    ROUTE_CONFLICT = "ROUTE_CONFLICT"
    DANGER_ZONE_CONFLICT = "DANGER_ZONE_CONFLICT"
    CONFIGURATION_UNSUPPORTED = "CONFIGURATION_UNSUPPORTED"


@dataclass(frozen=True)
class OperationEvaluation:
    operation_id: str
    passed: bool
    radius_m: float
    available_capacity_kg: float
    capacity_margin_kg: float
    utilization: float | None
    required_hook_height_m: float
    height_margin_m: float
    reason_codes: tuple[ConstraintCode, ...]


@dataclass(frozen=True)
class PlacementEvaluation:
    stage_id: str
    crane_point: Point2D
    configuration_id: str
    passed: bool
    operation_evaluations: tuple[OperationEvaluation, ...]
    reason_codes: tuple[ConstraintCode, ...]
    critical_capacity_operation_id: str | None
    critical_height_operation_id: str | None


def _append_unique(codes: list[ConstraintCode], code: ConstraintCode) -> None:
    if code not in codes:
        codes.append(code)


def _configuration_supported(config: CraneConfigurationV3) -> bool:
    jib_is_allowed = any(abs(config.jib_length_m - value) <= EPS for value in config.allowed_jib_lengths_m)
    return jib_is_allowed and not validate_capacity_curve(config)


def evaluate_operation(
    operation: LiftingOperation,
    crane_point: Point2D,
    config: CraneConfigurationV3,
    project: ProjectV3,
) -> OperationEvaluation:
    operation_project = replace(project, operations=(operation,))
    if validate_project(operation_project) or validate_operations(operation_project):
        return OperationEvaluation(
            operation.id,
            False,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            (ConstraintCode.INPUT_BLOCKED,),
        )

    source_point = (operation.source.x_m, operation.source.y_m)
    destination_point = (operation.destination.x_m, operation.destination.y_m)
    source_radius = hypot(source_point[0] - crane_point[0], source_point[1] - crane_point[1])
    destination_radius = hypot(
        destination_point[0] - crane_point[0], destination_point[1] - crane_point[1]
    )
    radius_m = max(source_radius, destination_radius)
    available_capacity_kg = conservative_capacity_kg(config, radius_m)
    capacity_margin_kg = available_capacity_kg - operation.load.total_kg
    utilization = operation.load.total_kg / available_capacity_kg if available_capacity_kg > 0 else None
    required_height_m = required_hook_height(
        operation.destination.z_m,
        operation.load.height_m,
        operation.load.rigging_height_m,
        people_may_be_below=False,
    )
    height_margin_m = config.max_free_standing_hook_height_m - required_height_m

    reasons: list[ConstraintCode] = []
    if not _configuration_supported(config):
        _append_unique(reasons, ConstraintCode.CONFIGURATION_UNSUPPORTED)
    if radius_m > config.jib_length_m + EPS:
        _append_unique(reasons, ConstraintCode.REACH_EXCEEDED)
    if capacity_margin_kg < -EPS:
        _append_unique(reasons, ConstraintCode.CAPACITY_INSUFFICIENT)
    if height_margin_m < -EPS:
        _append_unique(reasons, ConstraintCode.HEIGHT_INSUFFICIENT)
    for zone in project.site.restricted_zones:
        if segment_intersects_polygon(source_point, destination_point, list(zone)):
            _append_unique(reasons, ConstraintCode.ROUTE_CONFLICT)
            break
    try:
        danger_offset_m = danger_zone_offset_from_outer_edge(
            max(operation.source.z_m, operation.destination.z_m, EPS),
            operation.load.largest_dimension_m,
        )
    except NormativeInputError:
        return OperationEvaluation(
            operation.id,
            False,
            radius_m,
            available_capacity_kg,
            capacity_margin_kg,
            utilization,
            required_height_m,
            height_margin_m,
            (ConstraintCode.INPUT_BLOCKED,),
        )
    if not circle_inside_polygon(destination_point, danger_offset_m, list(project.site.boundary)):
        _append_unique(reasons, ConstraintCode.DANGER_ZONE_CONFLICT)

    return OperationEvaluation(
        operation.id,
        not reasons,
        radius_m,
        available_capacity_kg,
        capacity_margin_kg,
        utilization,
        required_height_m,
        height_margin_m,
        tuple(reasons),
    )


def evaluate_placement(
    project: ProjectV3,
    stage_id: str,
    crane_point: Point2D,
    config: CraneConfigurationV3,
) -> PlacementEvaluation:
    reasons: list[ConstraintCode] = []
    if validate_project(project) or validate_operations(project):
        return PlacementEvaluation(
            stage_id,
            crane_point,
            config.id,
            False,
            (),
            (ConstraintCode.INPUT_BLOCKED,),
            None,
            None,
        )

    boundary = list(project.site.boundary)
    building = list(project.site.building)
    if not point_in_polygon(crane_point, boundary):
        _append_unique(reasons, ConstraintCode.BASE_OUTSIDE_SITE)
    if point_in_polygon(crane_point, building):
        _append_unique(reasons, ConstraintCode.BASE_INSIDE_BUILDING)
    for zone in project.site.restricted_zones:
        if point_in_polygon(crane_point, list(zone)):
            _append_unique(reasons, ConstraintCode.RESTRICTED_ZONE_CONFLICT)
            break
    building_distance_m = distance_to_polygon(crane_point, building)
    if (
        building_distance_m + EPS < project.site.min_crane_to_building_m
        or building_distance_m > project.site.max_crane_to_building_m + EPS
    ):
        _append_unique(reasons, ConstraintCode.BASE_CLEARANCE_CONFLICT)
    if not _configuration_supported(config):
        _append_unique(reasons, ConstraintCode.CONFIGURATION_UNSUPPORTED)

    evaluations = tuple(
        evaluate_operation(operation, crane_point, config, project)
        for operation in project.operations
        if operation.stage_id == stage_id
    )
    for evaluation in evaluations:
        for code in evaluation.reason_codes:
            _append_unique(reasons, code)

    critical_capacity = min(evaluations, key=lambda item: (item.capacity_margin_kg, item.operation_id)).operation_id if evaluations else None
    critical_height = min(evaluations, key=lambda item: (item.height_margin_m, item.operation_id)).operation_id if evaluations else None
    return PlacementEvaluation(
        stage_id,
        crane_point,
        config.id,
        not reasons and bool(evaluations),
        evaluations,
        tuple(reasons),
        critical_capacity,
        critical_height,
    )
