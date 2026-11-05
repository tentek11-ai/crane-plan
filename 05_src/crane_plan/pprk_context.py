"""Traceable, read-only reporting context assembled from verified project results.

This module deliberately does not call geometry, capacity or optimization code.  It
copies project inputs, accepted scenario outputs and independent verification
checks into a uniform evidence ledger for the PPRk composer.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from math import isclose, isfinite
import re
from typing import Any, Mapping

from .engine.integration import ScenarioVerificationV21
from .engine.protocol import canonical_json, sha256_hex
from .models import ProjectInput, ScenarioResult
from .pprk_models import CompletenessIssue, meaningful_evidence_text


@dataclass(frozen=True)
class PPRKValueTrace:
    field_id: str
    value: object
    unit: str
    source: str
    rule: str
    algorithm_version: str
    operation_id: str = ""
    crane_id: str = ""
    verified: bool = True

    def __post_init__(self) -> None:
        if not self.field_id.strip():
            raise ValueError("field_id is required")
        numeric = isinstance(self.value, (int, float)) and not isinstance(self.value, bool)
        if numeric and (not isfinite(float(self.value)) or not all(
            item.strip() for item in (self.source, self.rule, self.algorithm_version)
        )):
            raise ValueError("Every numeric PPRk value requires source, rule and algorithm_version")


@dataclass(frozen=True)
class PPRKActiveLoad:
    """Immutable project evidence passed through composition to appendices."""

    load_index: int
    name: str
    active: bool
    load_kg: float
    rigging_kg: float
    total_kg: float
    dimensions_m: tuple[float, float, float]
    operation_ids: tuple[str, ...]
    confirmed: bool
    warnings: tuple[str, ...] = ()
    sling_fields: tuple[tuple[str, str], ...] = ()
    lifts: int | None = None
    verified_total_kg: float | None = None
    capacity_evidence: tuple[PPRKValueTrace, ...] = ()


@dataclass(frozen=True)
class PPRKContext:
    object_name: str
    object_address: str
    organization: str
    project_code: str
    verification_status: str
    protocol_run_id: str
    protocol_input_sha256: str
    protocol_result_sha256: str
    crane_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    values: Mapping[str, object]
    traces: tuple[PPRKValueTrace, ...]
    completeness_issues: tuple[CompletenessIssue, ...]
    scenario_render_snapshot: str = ""
    scenario_render_sha256: str = ""
    active_loads: tuple[PPRKActiveLoad, ...] | None = None
    scenario_index: int = 0

    def trace(self, field_id: str, operation_id: str = "", crane_id: str = "") -> PPRKValueTrace:
        for item in self.traces:
            if (
                item.field_id == field_id
                and item.operation_id == operation_id
                and item.crane_id == crane_id
            ):
                return item
        raise KeyError((field_id, operation_id, crane_id))


def scenario_render_snapshot(scenario: ScenarioResult) -> str:
    """Canonical identity of every engineering value available to drawings."""

    return canonical_json(_render_primitive(scenario))


def scenario_render_sha256(scenario: ScenarioResult) -> str:
    return sha256_hex(_render_primitive(scenario))


def _render_primitive(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _render_primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _render_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_render_primitive(item) for item in value]
    if isinstance(value, set):
        return sorted((_render_primitive(item) for item in value), key=canonical_json)
    if hasattr(value, "__dict__"):
        return {str(key): _render_primitive(item) for key, item in vars(value).items()}
    return value


_CHECK_RULES = {
    "REACH": "Independent engine reach check: required radius <= configured jib length",
    "CAPACITY_INSUFFICIENT": "Independent engine load-chart check: load plus rigging <= Q(R)",
    "HEIGHT": "Independent engine hook-height check against accepted configuration",
}


def _source_text(sources: object, fallback: str) -> str:
    rows: list[str] = []
    for source in sources or ():
        kind = getattr(source, "kind", "")
        kind_value = getattr(kind, "value", kind)
        document = getattr(source, "document_id", "")
        locator = getattr(source, "locator", "")
        note = getattr(source, "note", "")
        row = ":".join(str(item) for item in (kind_value, document, locator) if item)
        if not row:
            row = str(note)
        if row:
            rows.append(row)
    return "; ".join(rows) or fallback


def build_pprk_context(
    project: ProjectInput,
    scenario: ScenarioResult,
    verification: ScenarioVerificationV21,
) -> PPRKContext:
    """Build the reporting boundary without recomputing engineering decisions."""

    protocol = verification.protocol
    algorithm_version = str(getattr(protocol, "algorithm_version", "") or "UNAVAILABLE")
    verified_result = bool(verification.release_allowed and protocol is not None)
    traces: list[PPRKValueTrace] = []
    issues: list[CompletenessIssue] = []

    def require(code: str, message: str, field_id: str) -> None:
        issues.append(CompletenessIssue(code, message, True, field_id))

    def add(
        field_id: str,
        value: object,
        unit: str,
        source: str,
        rule: str,
        version: str = algorithm_version,
        *,
        operation_id: str = "",
        crane_id: str = "",
        verified: bool = verified_result,
    ) -> None:
        traces.append(
            PPRKValueTrace(
                field_id,
                value,
                unit,
                source,
                rule,
                version,
                operation_id,
                crane_id,
                verified,
            )
        )

    # Direct project inputs and a transparent coordinate difference used by the
    # existing UI as the manually entered building height.
    add("project.year", project.year, "year", "ProjectInput.year", "User-entered project year", "PROJECT-SCHEMA-4", verified=True)
    add("project.pit_bottom_m", project.pit_bottom_m, "m", "ProjectInput.pit_bottom_m", "User-entered bottom elevation", "PROJECT-SCHEMA-4", verified=True)
    add("project.parapet_m", project.parapet_m, "m", "ProjectInput.parapet_m", "User-entered parapet elevation", "PROJECT-SCHEMA-4", verified=True)
    building_height_m = project.parapet_m - project.pit_bottom_m
    add("project.building_height_m", building_height_m, "m", "ProjectInput.pit_bottom_m + ProjectInput.parapet_m", "parapet elevation - pit-bottom elevation", "PROJECT-SCHEMA-4", verified=True)
    add("project.floors", project.floors, "count", "ProjectInput.floors", "User-entered floor count", "PROJECT-SCHEMA-4", verified=True)
    add("site.storage_zone_count", len(project.site.storage_zones), "count", "ProjectInput.site.storage_zones", "Count of user-drawn storage polygons", "PROJECT-SCHEMA-4", verified=True)

    operation_ids_by_load: dict[int, list[str]] = {}
    protocol_project = getattr(protocol, "project", None)
    for operation in getattr(protocol_project, "operations", ()) or ():
        load_identifier = str(getattr(getattr(operation, "load", None), "id", ""))
        match = re.search(r"L(\d+)$", load_identifier) or re.search(r"-L(\d+)$", str(getattr(operation, "id", "")))
        if match:
            operation_ids_by_load.setdefault(int(match.group(1)) - 1, []).append(str(operation.id))

    solution = getattr(protocol, "solution", None)
    solution_placements: list[tuple[str, object]] = []
    expected_assignments: set[tuple[str, str]] = set()
    for stage in getattr(solution, "stages", ()) or ():
        for placement in getattr(stage, "placements", ()) or ():
            solution_placements.append((str(getattr(stage, "stage_id", "")), placement))
        for assignment in getattr(stage, "assignments", ()) or ():
            expected_assignments.add((str(assignment.operation_id), str(assignment.placement_id)))

    # Canonical identity is the protocol placement ID.  Legacy ``crane_id`` is
    # a configuration/catalog identifier and is retained separately.
    unused_solution_indexes = set(range(len(solution_placements)))
    canonical_crane_ids: list[str] = []
    selected_solution_for_legacy: list[object | None] = []
    for placement_index, legacy in enumerate(scenario.placements):
        matched_index = next(
            (
                index
                for index in sorted(unused_solution_indexes)
                if (getattr(solution_placements[index][1], "x_m", None), getattr(solution_placements[index][1], "y_m", None))
                == (legacy.x, legacy.y)
            ),
            None,
        )
        if matched_index is None and placement_index in unused_solution_indexes:
            matched_index = placement_index
        if matched_index is None:
            canonical_crane_ids.append(legacy.crane_id)
            selected_solution_for_legacy.append(None)
        else:
            unused_solution_indexes.remove(matched_index)
            selected = solution_placements[matched_index][1]
            canonical_crane_ids.append(str(getattr(selected, "id", legacy.crane_id)))
            selected_solution_for_legacy.append(selected)

    active_load_rows = [(index, load) for index, load in enumerate(project.loads) if load.active]
    active_loads = [load for _, load in active_load_rows]
    for original_index, load in active_load_rows:
        load_source = f"ProjectInput.loads[{original_index}]"
        related_operations = tuple(operation_ids_by_load.get(original_index, ()))
        if not related_operations:
            require("PPRK_LOAD_OPERATION_REQUIRED", f"Груз «{load.name}» не связан с проверенной операцией.", f"loads[{original_index}]")
            related_operations = ("",)
        for operation_id in related_operations:
            add("load.mass_kg", load.load_kg, "kg", load_source, "User-confirmed active load mass", "PROJECT-SCHEMA-4", operation_id=operation_id, verified=project.loads_verified)
            add("load.rigging_kg", load.rigging_kg, "kg", load_source, "User-confirmed rigging mass", "PROJECT-SCHEMA-4", operation_id=operation_id, verified=project.loads_verified)
            add("load.length_m", load.length_m, "m", load_source, "User-confirmed load geometry", "PROJECT-SCHEMA-4", operation_id=operation_id, verified=project.loads_verified)
            add("load.lift_count", load.lifts, "count", load_source, "User-entered active lift count", "PROJECT-SCHEMA-4", operation_id=operation_id, verified=project.loads_verified)

    crane_ids = tuple(canonical_crane_ids)
    for placement_index, placement in enumerate(scenario.placements):
        source = f"ScenarioResult.placements[{placement_index}]"
        crane_id = canonical_crane_ids[placement_index]
        selected_solution = selected_solution_for_legacy[placement_index]
        authoritative_configuration_id = str(getattr(selected_solution, "configuration_id", ""))
        if not authoritative_configuration_id:
            require("PPRK_CONFIGURATION_ID_REQUIRED", f"Для установки {crane_id} отсутствует ID выбранной конфигурации протокола.", f"placements/{crane_id}/configuration_id")
        add(
            "crane.configuration_id",
            authoritative_configuration_id,
            "",
            f"CalculationProtocol.solution.placements[{crane_id}]" if selected_solution is not None else "missing",
            "Selected protocol configuration identity",
            crane_id=crane_id,
        )
        add(
            "crane.legacy_configuration_reference",
            placement.crane_id,
            "",
            source,
            "Legacy scenario configuration reference retained for migration/audit only",
            crane_id=crane_id,
        )
        for field_id, value, unit, rule in (
            ("crane.x_m", placement.x, "m", "Selected crane base coordinate"),
            ("crane.y_m", placement.y, "m", "Selected crane base coordinate"),
            ("crane.max_radius_m", placement.max_radius_m, "m", "Accepted scenario maximum working radius"),
            ("crane.jib_length_m", placement.jib_length_m, "m", "Accepted catalog jib configuration"),
            ("crane.required_hook_height_m", placement.required_hook_height_m, "m", "Accepted scenario hook-height requirement"),
            ("crane.max_free_standing_height_m", placement.max_free_standing_height_m, "m", "Accepted catalog free-standing height"),
            ("crane.accepted_height_m", placement.accepted_crane_height_m, "m", "Accepted scenario tower height"),
            ("crane.total_additional_sections", placement.total_additional_sections, "count", "Accepted scenario tower-section count"),
            ("crane.required_tie_length_m", placement.required_tie_length_m, "m", "Accepted preliminary tie geometry"),
        ):
            add(field_id, value, unit, source, rule, crane_id=crane_id)
        for field_id, value, unit, rule in (
            ("crane.jib_level_m", placement.jib_level_m, "m", "Accepted bottom elevation of jib"),
            ("crane.allowed_sector_start_deg", placement.allowed_sector_start_deg, "deg", "Accepted working sector start"),
            ("crane.allowed_sector_end_deg", placement.allowed_sector_end_deg, "deg", "Accepted working sector end"),
            ("crane.tower_exclusion_start_deg", placement.tower_exclusion_start_deg, "deg", "Accepted tower-protection sector start"),
            ("crane.tower_exclusion_end_deg", placement.tower_exclusion_end_deg, "deg", "Accepted tower-protection sector end"),
        ):
            if value is not None:
                add(field_id, value, unit, source, rule, crane_id=crane_id)
        for radial_index, radial_limit in enumerate(placement.radial_limits_m):
            for component_index, value in enumerate(radial_limit):
                add("crane.radial_limit_m", value, "m", f"{source}.radial_limits_m[{radial_index}][{component_index}]", "Accepted radial operating limit", crane_id=crane_id)
        for coverage_field, indexes in (
            ("coverage.work_point_index", placement.assigned_work_points),
            ("coverage.contour_point_index", placement.assigned_contour_points),
            ("coverage.logistics_zone_index", placement.assigned_logistics_zones),
        ):
            for index in indexes:
                add(coverage_field, index, "index", source, "Accepted scenario coverage assignment", crane_id=crane_id)
        if not placement.assigned_work_points:
            require("PPRK_COVERAGE_REQUIRED", f"Кран {crane_id} не имеет подтвержденных точек подачи.", f"placements/{crane_id}/coverage")
        for tie_index, level in enumerate(placement.tie_in_levels_m):
            add("crane.tie_level_m", level, "m", f"{source}.tie_in_levels_m[{tie_index}]", "Accepted preliminary tie level", crane_id=crane_id)
        for tie_index, section_count in enumerate(placement.tie_in_stage_sections):
            add("crane.tie_stage_sections", section_count, "count", f"{source}.tie_in_stage_sections[{tie_index}]", "Accepted tower sections at tie stage", crane_id=crane_id)

        sozr = placement.sozr_plan
        if sozr is None:
            require("PPRK_SOZR_REQUIRED", f"Для крана {crane_id} отсутствует схема СОЗР.", f"placements/{crane_id}/sozr")
        else:
            add("sozr.technical_radius_m", sozr.technical_radius_m, "m", f"{source}.sozr_plan", "Accepted SOZR technical radius", sozr.algorithm_version, crane_id=crane_id)
            for point_index, point in enumerate(sozr.points):
                point_source = f"{source}.sozr_plan.points[{point_index}]"
                for field_id, value, unit in (
                    ("sozr.point.x_m", point.x, "m"),
                    ("sozr.point.y_m", point.y, "m"),
                    ("sozr.point.bearing_deg", point.bearing_deg, "deg"),
                    ("sozr.point.radius_m", point.radius_m, "m"),
                    ("sozr.point.zone_height_m", point.zone_height_m, "m"),
                ):
                    add(field_id, value, unit, point_source, "Accepted SOZR constraint point", sozr.algorithm_version, operation_id=point.label, crane_id=crane_id)
            for contour_kind, contours in (
                ("permanent", sozr.permanent_contours),
                ("conditional", sozr.conditional_contours),
            ):
                for contour_index, contour in enumerate(contours):
                    contour_source = f"{source}.sozr_plan.{contour_kind}_contours[{contour_index}]"
                    for point_index, (x_m, y_m) in enumerate(contour.points):
                        add(f"sozr.{contour_kind}_contour.x_m", x_m, "m", f"{contour_source}.points[{point_index}]", "Accepted SOZR contour coordinate", sozr.algorithm_version, operation_id=contour.zone_id, crane_id=crane_id)
                        add(f"sozr.{contour_kind}_contour.y_m", y_m, "m", f"{contour_source}.points[{point_index}]", "Accepted SOZR contour coordinate", sozr.algorithm_version, operation_id=contour.zone_id, crane_id=crane_id)
                    add(f"sozr.{contour_kind}_contour.zone_height_m", contour.zone_height_m, "m", contour_source, "Accepted SOZR obstacle height", sozr.algorithm_version, operation_id=contour.zone_id, crane_id=crane_id)
            for contour_index, contour in enumerate(sozr.admissible_contours):
                for point_index, (x_m, y_m) in enumerate(contour):
                    contour_source = f"{source}.sozr_plan.admissible_contours[{contour_index}][{point_index}]"
                    add("sozr.admissible_contour.x_m", x_m, "m", contour_source, "Accepted admissible-area contour coordinate", sozr.algorithm_version, crane_id=crane_id)
                    add("sozr.admissible_contour.y_m", y_m, "m", contour_source, "Accepted admissible-area contour coordinate", sozr.algorithm_version, crane_id=crane_id)
            if not sozr.admissible_contours:
                require("PPRK_ADMISSIBLE_AREA_REQUIRED", f"Для крана {crane_id} отсутствует контур допустимой области.", f"placements/{crane_id}/admissible_area")

    for zone_index, zone in enumerate(project.site.restricted_zones):
        source = "; ".join(zone.source_refs) or f"ProjectInput.site.restricted_zones[{zone_index}]"
        add("restricted_zone.height_m", zone.height_m, "m", source, "User-entered obstacle height above project zero", "PROJECT-SCHEMA-4", operation_id=zone.id, verified=zone.verified)
        add("restricted_zone.horizontal_clearance_m", zone.horizontal_clearance_m, "m", source, "User-entered zone clearance", "PROJECT-SCHEMA-4", operation_id=zone.id, verified=zone.verified)

    route_operation_ids: list[str] = []
    for route_index, route in enumerate(scenario.routes):
        route_operation_ids.append(route.operation_id)
        route_source = f"ScenarioResult.routes[{route_index}] input={route.input_sha256}"
        route_crane_id = next((crane_id for operation_id, crane_id in expected_assignments if operation_id == route.operation_id), "")
        if not route_crane_id:
            work_match = re.match(r"WP(\d+):", route.operation_id)
            if work_match:
                prefix = f"OP-W{work_match.group(1)}-"
                route_crane_id = next((crane_id for operation_id, crane_id in expected_assignments if operation_id.startswith(prefix)), "")
        add("route.transport_hook_height_m", route.transport_hook_height_m, "m", route_source, "Accepted route transport height", operation_id=route.operation_id, crane_id=route_crane_id)
        for waypoint_index, waypoint in enumerate(route.waypoints):
            waypoint_source = f"{route_source}.waypoints[{waypoint_index}]"
            add("route.waypoint.x_m", waypoint.x, "m", waypoint_source, "Accepted route waypoint", operation_id=route.operation_id, crane_id=route_crane_id)
            add("route.waypoint.y_m", waypoint.y, "m", waypoint_source, "Accepted route waypoint", operation_id=route.operation_id, crane_id=route_crane_id)
            add("route.waypoint.hook_height_m", waypoint.hook_height_m, "m", waypoint_source, "Accepted route waypoint hook height", operation_id=route.operation_id, crane_id=route_crane_id)
        for alternative_index, alternative in enumerate(route.alternatives):
            alternative_source = f"{route_source}.alternatives[{alternative_index}]"
            add("route.alternative.min_clearance_m", alternative.min_clearance_m, "m", alternative_source, "Accepted route-alternative clearance", operation_id=route.operation_id, crane_id=route_crane_id)
            add("route.alternative.path_length_m", alternative.path_length_m, "m", alternative_source, "Accepted route-alternative length", operation_id=route.operation_id, crane_id=route_crane_id)

    # The protocol route carries the canonical operation/placement identities;
    # legacy scenario routes may retain older logistics labels.
    protocol_solution = getattr(protocol, "solution", None)
    for route_index, route in enumerate(getattr(protocol_solution, "operation_routes", ()) or ()):
        operation_id = str(route.operation_id)
        if operation_id in route_operation_ids:
            continue
        route_operation_ids.append(operation_id)
        route_source = f"CalculationProtocol.solution.operation_routes[{route_index}]"
        crane_id = str(getattr(route, "placement_id", ""))
        add("route.transport_hook_height_m", route.transport_hook_height_m, "m", route_source, "Verified protocol route transport height", operation_id=operation_id, crane_id=crane_id)
        for waypoint_index, waypoint in enumerate(route.waypoints):
            waypoint_source = f"{route_source}.waypoints[{waypoint_index}]"
            add("route.waypoint.x_m", waypoint.x_m, "m", waypoint_source, "Verified protocol route waypoint", operation_id=operation_id, crane_id=crane_id)
            add("route.waypoint.y_m", waypoint.y_m, "m", waypoint_source, "Verified protocol route waypoint", operation_id=operation_id, crane_id=crane_id)
            add("route.waypoint.hook_height_m", waypoint.hook_height_m, "m", waypoint_source, "Verified protocol route waypoint hook height", operation_id=operation_id, crane_id=crane_id)

    if scenario.joint_plan is not None:
        joint = scenario.joint_plan
        joint_source = "ScenarioResult.joint_plan"
        for field_id, value, unit, rule in (
            ("joint.axis_distance_m", joint.axis_distance_m, "m", "Accepted distance between crane axes"),
            ("joint.working_horizontal_clearance_m", joint.working_horizontal_clearance_m, "m", "Accepted working clearance"),
            ("joint.parking_horizontal_clearance_m", joint.parking_horizontal_clearance_m, "m", "Accepted parking clearance"),
            ("joint.vertical_separation_m", joint.vertical_separation_m, "m", "Accepted vertical separation"),
            ("joint.higher_crane_index", joint.higher_crane_index, "index", "Accepted higher-crane assignment"),
            ("joint.priority_crane_index", joint.priority_crane_index, "index", "Accepted priority assignment"),
            ("joint.overlap_area_m2", joint.overlap_area_m2, "m2", "Accepted overlap area"),
            ("joint.jib_structural_height_m", joint.jib_structural_height_m, "m", "Accepted jib structural envelope"),
            ("joint.tower_protection_radius_m", joint.tower_protection_radius_m, "m", "Accepted tower protection radius"),
            ("joint.combined_tower_envelope_m", joint.combined_tower_envelope_m, "m", "Accepted combined tower envelope"),
        ):
            add(field_id, value, unit, joint_source, rule)
        for point_index, (x_m, y_m) in enumerate(joint.overlap_polygon):
            add("joint.overlap_polygon.x_m", x_m, "m", f"{joint_source}.overlap_polygon[{point_index}]", "Accepted joint-work overlap polygon")
            add("joint.overlap_polygon.y_m", y_m, "m", f"{joint_source}.overlap_polygon[{point_index}]", "Accepted joint-work overlap polygon")

    for field_id, value, unit, source, rule in (
        ("schedule.calendar_days", scenario.calendar_days, "day", "ScenarioResult.calendar_days", "Accepted calculated duration"),
        ("comparison.score", scenario.score, "score", "ScenarioResult.score", "Accepted scenario ranking score"),
        ("comparison.estimated_cost", scenario.estimated_cost, "currency", "ScenarioResult.estimated_cost", "Accepted scenario cost estimate"),
    ):
        if value is not None:
            add(field_id, value, unit, source, rule)
    for crane_index, work_hours in enumerate(scenario.crane_work_hours):
        add("schedule.crane_work_hours", work_hours, "hour", f"ScenarioResult.crane_work_hours[{crane_index}]", "Accepted calculated crane work duration", crane_id=canonical_crane_ids[crane_index] if crane_index < len(canonical_crane_ids) else "")

    check_source = None
    if verification.engine_result is not None:
        check_source = getattr(verification.engine_result, "verification", None)
    if check_source is None and protocol is not None:
        check_source = getattr(protocol, "verification", None)
    checks = tuple(getattr(check_source, "checks", ()) or ())
    required_checks = {"REACH", "CAPACITY_INSUFFICIENT", "HEIGHT"}
    checks_by_assignment: dict[tuple[str, str], dict[str, object]] = {}
    work_radii: list[float] = []
    verified_heights: list[float] = []
    verification_outputs: list[dict[str, object]] = []
    verified_danger_offsets: list[float] = []
    for check in checks:
        source = _source_text(check.sources, f"CalculationProtocol[{getattr(protocol, 'run_id', '')}]")
        common = {"operation_id": check.operation_id or "", "crane_id": check.crane_id or "", "verified": bool(check.passed)}
        code_id = str(check.code).lower()
        output_row: dict[str, object] = {
            "code": check.code,
            "passed": bool(check.passed),
            "operation_id": check.operation_id or "",
            "crane_id": check.crane_id or "",
            "units": check.units,
        }
        for role, value in (("measured", check.measured_value), ("limit", check.limit)):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                add(
                    f"verification.{code_id}.{role}",
                    value,
                    check.units,
                    source,
                    f"Independent engine verification output {check.code} ({role})",
                    **common,
                )
                output_row[role] = value
        verification_outputs.append(output_row)
        if (
            str(check.code).startswith("DANGER_ZONE")
            and bool(check.passed)
            and isinstance(check.measured_value, (int, float))
            and not isinstance(check.measured_value, bool)
        ):
            verified_danger_offsets.append(float(check.measured_value))
        if check.code not in required_checks:
            continue
        assignment_key = (check.operation_id or "", check.crane_id or "")
        checks_by_assignment.setdefault(assignment_key, {})[check.code] = check
        rule = _CHECK_RULES[check.code]
        if check.code == "REACH":
            add("reach.required_m", check.measured_value, check.units, source, rule, **common)
            add("reach.available_m", check.limit, check.units, source, rule, **common)
            if isinstance(check.measured_value, (int, float)):
                work_radii.append(float(check.measured_value))
        elif check.code == "CAPACITY_INSUFFICIENT":
            add("capacity.required_kg", check.measured_value, check.units, source, rule, **common)
            add("capacity.available_kg", check.limit, check.units, source, rule, **common)
        elif check.code == "HEIGHT":
            add("height.required_m", check.measured_value, check.units, source, rule, **common)
            add("height.available_m", check.limit, check.units, source, rule, **common)
            if isinstance(check.measured_value, (int, float)):
                verified_heights.append(float(check.measured_value))

    if protocol is None:
        issues.append(CompletenessIssue("PPRK_PROTOCOL_REQUIRED", "Отсутствует проверенный расчетный протокол.", True, "verification.protocol"))
        add("verification.protocol", None, "", "missing", "Protocol is required for traceable calculated values", "UNAVAILABLE", verified=False)
    else:
        status_value = str(getattr(verification.status, "value", verification.status))
        if not verification.release_allowed or status_value not in {"VERIFIED", "VERIFIED_WITH_CONDITIONS"}:
            require("PPRK_VERIFICATION_REJECTED", "Выбранный вариант не разрешен независимой проверкой.", "verification.status")
        if not expected_assignments:
            require("PPRK_ASSIGNMENTS_REQUIRED", "В протоколе отсутствуют назначения операций кранам.", "verification.assignments")
        for operation_id, crane_id in sorted(expected_assignments):
            assignment_checks = checks_by_assignment.get((operation_id, crane_id), {})
            for code in sorted(required_checks):
                field_id = f"{operation_id}/{crane_id}/{code}"
                check = assignment_checks.get(code)
                if check is None:
                    require("PPRK_TRACE_REQUIRED", f"Для назначения {operation_id}/{crane_id} отсутствует проверка {code}.", field_id)
                elif not bool(getattr(check, "passed", False)):
                    require("PPRK_CHECK_FAILED", f"Проверка {code} для {operation_id}/{crane_id} не пройдена.", field_id)

    # Transfer operation margins from the evaluated selected candidate.  These
    # are engine outputs, not differences recomputed by the reporting layer.
    placement_evaluations = tuple(getattr(protocol, "placement_evaluations", ()) or ())
    for stage_id, selected in solution_placements:
        matching = next(
            (
                evaluation
                for evaluation in placement_evaluations
                if str(getattr(evaluation, "stage_id", "")) == stage_id
                and str(getattr(evaluation, "configuration_id", "")) == str(getattr(selected, "configuration_id", ""))
                and tuple(getattr(evaluation, "crane_point", ())) == (getattr(selected, "x_m", None), getattr(selected, "y_m", None))
            ),
            None,
        )
        assigned_operations = {operation_id for operation_id, crane_id in expected_assignments if crane_id == str(selected.id)}
        if matching is None:
            for operation_id in sorted(assigned_operations):
                require("PPRK_MARGIN_TRACE_REQUIRED", f"Нет оценки запаса для {operation_id}/{selected.id}.", f"{operation_id}/{selected.id}/margins")
            continue
        by_operation = {str(item.operation_id): item for item in getattr(matching, "operation_evaluations", ()) or ()}
        for operation_id in sorted(assigned_operations):
            evaluation = by_operation.get(operation_id)
            if evaluation is None:
                require("PPRK_MARGIN_TRACE_REQUIRED", f"Нет оценки запаса для {operation_id}/{selected.id}.", f"{operation_id}/{selected.id}/margins")
                continue
            evaluation_source = f"CalculationProtocol.placement_evaluations[{stage_id}/{selected.id}/{operation_id}]"
            for field_id, value, unit, rule in (
                ("capacity.margin_kg", evaluation.capacity_margin_kg, "kg", "Engine-evaluated capacity margin"),
                ("capacity.utilization", evaluation.utilization, "ratio", "Engine-evaluated capacity utilization"),
                ("height.margin_m", evaluation.height_margin_m, "m", "Engine-evaluated hook-height margin"),
            ):
                if value is not None:
                    add(field_id, value, unit, evaluation_source, rule, operation_id=operation_id, crane_id=str(selected.id), verified=bool(getattr(evaluation, "passed", True)))

    catalog_by_id = {str(config.id): config for config in (getattr(protocol, "catalog", ()) or ())}
    selected_configuration_pairs = [
        (selected, catalog_by_id[str(getattr(selected, "configuration_id", ""))])
        for _, selected in solution_placements
        if str(getattr(selected, "configuration_id", "")) in catalog_by_id
    ]
    selected_configurations = [config for _, config in selected_configuration_pairs]
    passport_capacities: list[float] = []
    for config in selected_configurations:
        curve_capacities = [
            float(point.capacity_kg)
            for point in (getattr(config, "capacity_curve", ()) or ())
            if isinstance(getattr(point, "capacity_kg", None), (int, float))
        ]
        if curve_capacities:
            passport_capacities.append(max(curve_capacities))
        else:
            require("PPRK_CAPACITY_CURVE_REQUIRED", f"Для конфигурации {config.id} отсутствует паспортная грузовая характеристика.", f"catalog/{config.id}/capacity_curve")
    if solution_placements and len(selected_configurations) != len(solution_placements):
        require("PPRK_CONFIGURATION_REQUIRED", "Не для всех выбранных кранов найдена паспортная конфигурация.", "verification.catalog")
    for selected, config in selected_configuration_pairs:
        curve_capacities = [float(point.capacity_kg) for point in (getattr(config, "capacity_curve", ()) or ())]
        if not curve_capacities:
            continue
        add(
            "crane.passport_max_capacity_kg",
            max(curve_capacities),
            "kg",
            _source_text((getattr(config, "source", None),), f"CalculationProtocol.catalog[{config.id}]"),
            "Maximum published capacity value in selected configuration capacity curve",
            crane_id=str(selected.id),
        )

    operation_ids = tuple(sorted(set(route_operation_ids) | {operation_id for operation_id, _ in expected_assignments} | {str(getattr(check, "operation_id", "")) for check in checks if getattr(check, "operation_id", None)}))
    tie_levels = tuple(level for placement in scenario.placements for level in placement.tie_in_levels_m)
    tower_sections = tuple(count for placement in scenario.placements for count in placement.tie_in_stage_sections)
    sozr_labels = tuple(point.label for placement in scenario.placements if placement.sozr_plan for point in placement.sozr_plan.points)
    for point_index, (x_m, y_m) in enumerate(project.site.unloading_zone):
        add("site.unloading_zone.x_m", x_m, "m", f"ProjectInput.site.unloading_zone[{point_index}]", "User-drawn unloading-zone coordinate", "PROJECT-SCHEMA-4", verified=True)
        add("site.unloading_zone.y_m", y_m, "m", f"ProjectInput.site.unloading_zone[{point_index}]", "User-drawn unloading-zone coordinate", "PROJECT-SCHEMA-4", verified=True)
    values: dict[str, object] = {
        "object_name": project.name,
        "object_address": project.pprk_release.object_address,
        "crane_count": len(scenario.placements),
        "crane_model": ", ".join(dict.fromkeys(placement.model for placement in scenario.placements)),
        "crane_models": tuple(placement.model for placement in scenario.placements),
        "crane_configuration_ids": tuple(str(getattr(selected, "configuration_id", "")) for selected in selected_solution_for_legacy),
        "legacy_configuration_references": tuple(placement.crane_id for placement in scenario.placements),
        "crane_configurations": tuple(f"{placement.model}; стрела {placement.jib_length_m:g} м" for placement in scenario.placements),
        "building_height_m": building_height_m,
        "floors": project.floors,
        "hook_height_m": tuple(verified_heights) or tuple(placement.required_hook_height_m for placement in scenario.placements),
        "jib_length_m": tuple(placement.jib_length_m for placement in scenario.placements),
        "max_capacity_t": (max(passport_capacities) / 1000.0) if passport_capacities else None,
        "active_loads": tuple(load.name for load in active_loads),
        "load_masses_kg": tuple(load.load_kg for load in active_loads),
        "rigging_masses_kg": tuple(load.rigging_kg for load in active_loads),
        "lift_counts": tuple(load.lifts for load in active_loads),
        "max_load_length_m": max((load.length_m for load in active_loads), default=None),
        "storage_zone_count": len(project.site.storage_zones),
        "unloading_zone": tuple(project.site.unloading_zone),
        "tie_levels_m": tie_levels,
        "tower_sections": tower_sections,
        "work_radii_m": tuple(work_radii),
        "sozr_points": sozr_labels,
        "route_register": operation_ids,
        "calendar_days": scenario.calendar_days,
        "estimated_cost": scenario.estimated_cost,
        "comparison_score": scenario.score,
        "crane_work_hours": tuple(scenario.crane_work_hours),
        "joint_work_schedule": tuple(scenario.joint_plan.schedule_stages) if scenario.joint_plan else (),
        "verification_outputs": tuple(verification_outputs),
        "verified_danger_zone_offset_m": max(verified_danger_offsets) if verified_danger_offsets else None,
        "verified_mitigation_types": tuple(sorted({str(check.limit) for check in checks
            if check.code in {"DANGER_ZONE_PROTECTED", "DANGER_ROUTE_PROTECTED"} and check.passed and not check.review_required})),
        "project_basis": project.pprk_release.project_basis,
        "plan_sheet_refs": project.pprk_release.plan_sheet_refs,
        "responsible_fire_safety": project.pprk_release.responsible_fire_safety,
        "max_wind_speed_m_s": project.pprk_release.max_wind_speed_m_s,
        "fall_protection_system": project.pprk_release.fall_protection_system,
        "power_supply_scheme": project.pprk_release.power_supply_scheme,
        "waste_plan": project.pprk_release.waste_plan,
        "external_document_register": project.pprk_release.external_document_register,
        "receiving_platform_ids": tuple(project.pprk_release.receiving_platform_ids),
        "opening_ids": tuple(project.pprk_release.opening_ids),
        "bucket_volume_m3": project.pprk_release.bucket_volume_m3,
    }
    add("crane.count", len(scenario.placements), "count", "ScenarioResult.placements", "Count of accepted crane placements")
    if passport_capacities:
        add("capacity.passport_maximum_t", values["max_capacity_t"], "t", "CalculationProtocol.catalog", "Selected configuration passport maximum converted kg to t")
    if project.pprk_release.max_wind_speed_m_s is not None:
        add(
            "release.max_wind_speed_m_s",
            project.pprk_release.max_wind_speed_m_s,
            "m/s",
            "ProjectInput.pprk_release.max_wind_speed_m_s",
            "User-entered release requirement",
            "PROJECT-SCHEMA-4",
            verified=True,
        )
    if project.pprk_release.bucket_volume_m3 is not None:
        add(
            "release.bucket_volume_m3",
            project.pprk_release.bucket_volume_m3,
            "m3",
            "ProjectInput.pprk_release.bucket_volume_m3",
            "User-entered active bucket volume",
            "PROJECT-SCHEMA-4",
            verified=True,
        )

    if not project.pprk_release.object_address.strip():
        require("PPRK_ADDRESS_REQUIRED", "Не заполнен адрес объекта.", "object_address")
    if not (project.pprk_release.developer_organization or project.organization).strip():
        require("PPRK_ORGANIZATION_REQUIRED", "Не заполнена организация-разработчик.", "organization")
    if not (project.pprk_release.project_code or project.project_code).strip():
        require("PPRK_CODE_REQUIRED", "Не заполнен шифр проекта.", "project_code")
    if not scenario.placements:
        require("PPRK_CRANES_REQUIRED", "В варианте отсутствуют краны.", "cranes")
    if not active_loads:
        require("PPRK_LOADS_REQUIRED", "Отсутствуют активные грузы.", "loads")
    elif not project.loads_verified:
        require("PPRK_LOADS_UNVERIFIED", "Массы и оснастка грузов не подтверждены.", "loads")
    if not route_operation_ids:
        require("PPRK_ROUTES_REQUIRED", "Отсутствуют проверенные маршруты подачи.", "routes")
    else:
        route_id_set = set(route_operation_ids)
        for operation_id, _ in sorted(expected_assignments):
            if operation_id not in route_id_set:
                require("PPRK_ROUTE_OPERATION_REQUIRED", f"Для операции {operation_id} отсутствует маршрут.", f"routes/{operation_id}")
    if any(not zone.verified for zone in project.site.restricted_zones):
        require("PPRK_ZONES_UNVERIFIED", "Не все опасные зоны подтверждены.", "restricted_zones")

    render_snapshot = scenario_render_snapshot(scenario)
    # A project checkbox confirms input collection, not correspondence to the
    # independently verified operation. Match every assigned operation against
    # the authoritative protocol's capacity check in kg, within 0.001 kg (1 g).
    active_payload = []
    protocol_checks = tuple(getattr(getattr(protocol, "verification", None), "checks", ()) or ())
    for index, load in active_load_rows:
        related = tuple(sorted(set(operation_ids_by_load.get(index, ()))))
        assignments = sorted(pair for pair in expected_assignments if pair[0] in related)
        warnings = []
        evidence = []
        if not related or {pair[0] for pair in assignments} != set(related):
            warnings.append("Груз не связан со всеми проверенными назначениями операций.")
        if not project.loads_verified:
            warnings.append("Исходные данные груза не подтверждены разработчиком.")
        if not verified_result:
            warnings.append("Протокол не разрешён независимой проверкой.")
        rigging_valid = (
            load.rigging_verified is True
            and all(meaningful_evidence_text(getattr(load, field_id), field_id=field_id) for field_id in
                    ("rigging_type", "sling_identification", "rigging_evidence"))
            and type(load.rigging_branch_count) is int and load.rigging_branch_count > 0
            and type(load.rigging_capacity_kg) in (int, float)
            and isfinite(load.rigging_capacity_kg) and load.rigging_capacity_kg >= load.total_kg > 0)
        if not rigging_valid:
            message = "НЕ ЗАПОЛНЕНО: проверенные тип оснастки, число ветвей, идентификатор стропа и паспортная грузоподъёмность с документом подтверждения."
            warnings.append(message)
            require("PPRK_RIGGING_EVIDENCE_REQUIRED", f"Груз «{load.name}»: {message}", f"loads[{index}].rigging")
        sling_fields = (("Тип", load.rigging_type), ("Ветвей", str(load.rigging_branch_count)),
                        ("Строп", load.sling_identification), ("Грузоподъёмность, кг", str(load.rigging_capacity_kg)),
                        ("Подтверждающий документ", load.rigging_evidence)) if rigging_valid else ()
        for operation_id, crane_id in assignments:
            matching = [check for check in protocol_checks if check.code == "CAPACITY_INSUFFICIENT" and check.operation_id == operation_id and check.crane_id == crane_id]
            check = matching[0] if len(matching) == 1 else None
            numeric = check is not None and all(type(value) in (float, int) and isfinite(value) and value >= 0 for value in (check.measured_value, check.limit))
            valid = bool(numeric and check.passed and not check.review_required and check.units == "kg" and check.measured_value <= check.limit + .001)
            matches = bool(valid and type(load.total_kg) in (int, float) and isfinite(load.total_kg) and isclose(load.total_kg, check.measured_value, rel_tol=0, abs_tol=.001))
            if not matches:
                measured = f"{check.measured_value} {check.units}" if check else "проверка отсутствует или неоднозначна"
                warnings.append(f"{operation_id}/{crane_id}: масса проекта {load.total_kg:g} кг не подтверждена протоколом ({measured}); допуск 0.001 кг.")
            if numeric:
                trace = PPRKValueTrace(
                    "load.verified_total_kg", check.measured_value, check.units,
                    f"CalculationProtocol[{getattr(protocol, 'run_id', '')}].verification/{operation_id}/{crane_id}/CAPACITY_INSUFFICIENT",
                    "Passed assigned capacity evidence in kg; project total matches within 0.001 kg (absolute, 1 g)",
                    algorithm_version, operation_id, crane_id, bool(matches and verified_result),
                )
                evidence.append(trace)
                traces.append(trace)
        confirmed = bool(not warnings and assignments and project.loads_verified)
        if warnings:
            require("PPRK_LOAD_EVIDENCE_REQUIRED", f"Груз «{load.name}»: " + "; ".join(warnings), f"loads[{index}]")
        # Existing input traces must not retain a misleading verified checkbox.
        load_source = f"ProjectInput.loads[{index}]"
        traces = [replace(trace, verified=confirmed) if trace.source == load_source and trace.field_id.startswith("load.") else trace for trace in traces]
        active_payload.append(PPRKActiveLoad(
            index, load.name, load.active, load.load_kg, load.rigging_kg,
            load.total_kg, (load.length_m, load.width_m, load.height_m), related,
            confirmed, tuple(warnings), sling_fields=sling_fields, lifts=load.lifts,
            verified_total_kg=float(evidence[0].value) if confirmed else None,
            capacity_evidence=tuple(evidence),
        ))

    return PPRKContext(
        project.name,
        str(values["object_address"]),
        project.pprk_release.developer_organization or project.organization,
        project.pprk_release.project_code or project.project_code,
        str(getattr(verification.status, "value", verification.status)),
        str(getattr(protocol, "run_id", "") or ""),
        str(getattr(protocol, "input_sha256", "") or ""),
        str(getattr(protocol, "result_sha256", "") or ""),
        crane_ids,
        operation_ids,
        values,
        tuple(traces),
        tuple(issues),
        render_snapshot,
        scenario_render_sha256(scenario),
        tuple(active_payload),
        verification.scenario_index,
    )
