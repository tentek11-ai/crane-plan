"""Reproducible admissible-area calculations for the crane-placement study.

The module deliberately separates feasibility from ranking.  Every rejected
candidate retains machine-readable reason codes so a reported area can be
audited against the same project inputs and crane load chart.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import hypot, isfinite
from time import perf_counter

from .catalog import allowed_capacity_kg
from .geometry import distance, distance_to_polygon, point_in_polygon, polygon_bounds
from .models import CraneConfiguration, Point, ProjectInput
from .normative import (
    NormativeInputError,
    danger_zone_offset_from_outer_edge,
    required_hook_height,
)
from .optimizer import TOWER_PROTECTION_RADIUS_M, _loads_for_work_point, _ray_is_clear


ALGORITHM_VERSION = "admissible-area/1.1"
DEFAULT_RIGGING_HEIGHT_M = 1.5
EPS = 1e-6


@dataclass(frozen=True)
class CandidateEvaluation:
    point: Point
    passed: bool
    reason_codes: tuple[str, ...]
    critical_operation_id: str | None
    required_radius_m: float
    capacity_margin_kg: float
    height_margin_m: float
    source_locators: tuple[str, ...]


@dataclass(frozen=True)
class AdmissibleAreaRun:
    run_id: str
    algorithm_version: str
    step_m: float
    refinement_levels: int
    evaluated_steps_m: tuple[float, ...]
    candidate_evaluations: tuple[CandidateEvaluation, ...]
    accepted_points: tuple[Point, ...]
    counts_by_reason: dict[str, int]
    area_estimate_m2: float
    connected_component_count: int
    duration_seconds: float
    input_hashes: tuple[tuple[str, str], ...]


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _input_blocked(project: ProjectInput, config: CraneConfiguration, point: Point) -> CandidateEvaluation | None:
    if not project.site.boundary or not project.site.building or not project.work_points:
        return _blocked_result(project, config, point)
    if not config.capacity_curve or config.jib_length_m <= 0 or config.max_free_standing_hook_height_m <= 0:
        return _blocked_result(project, config, point)
    for work_point in project.work_points:
        if work_point.load_index < 0 or work_point.load_index >= len(project.loads):
            return _blocked_result(project, config, point)
        if not project.loads[work_point.load_index].active:
            return _blocked_result(project, config, point)
    for load in (load for load in project.loads if load.active):
        values = (load.load_kg, load.rigging_kg, load.length_m, load.width_m, load.height_m)
        if any(value is None or not isfinite(float(value)) for value in values):
            return _blocked_result(project, config, point)
        if load.load_kg < 0 or load.rigging_kg < 0 or min(load.length_m, load.width_m, load.height_m) <= 0:
            return _blocked_result(project, config, point)
    return None


def _source_locators(project: ProjectInput, config: CraneConfiguration) -> tuple[str, ...]:
    return (
        config.source.strip() or "crane configuration source:UNSPECIFIED",
        f"project input:{project.name or 'UNNAMED'}",
        "ФНП № 461: высота подъёма и опасная зона",
    )


def _blocked_result(project: ProjectInput, config: CraneConfiguration, point: Point) -> CandidateEvaluation:
    return CandidateEvaluation(
        point=point,
        passed=False,
        reason_codes=("INPUT_BLOCKED",),
        critical_operation_id=None,
        required_radius_m=0.0,
        capacity_margin_kg=0.0,
        height_margin_m=0.0,
        source_locators=_source_locators(project, config),
    )


def evaluate_candidate(
    project: ProjectInput,
    config: CraneConfiguration,
    point: Point,
) -> CandidateEvaluation:
    """Evaluate one tower-axis coordinate without ranking it.

    Equality at a limit is accepted.  Missing mandatory data returns the sole
    reason ``INPUT_BLOCKED`` instead of silently substituting a default.
    """

    blocked = _input_blocked(project, config, point)
    if blocked is not None:
        return blocked

    reasons: list[str] = []
    site = project.site
    if (
        not point_in_polygon(point, site.boundary)
        or distance_to_polygon(point, site.boundary) + EPS < TOWER_PROTECTION_RADIUS_M
    ):
        reasons.append("BASE_OUTSIDE_SITE")
    if point_in_polygon(point, site.building):
        reasons.append("BASE_INSIDE_BUILDING")
    if any(
        point_in_polygon(point, zone)
        or distance_to_polygon(point, zone) < TOWER_PROTECTION_RADIUS_M - EPS
        for zone in site.restricted_zones
    ):
        reasons.append("RESTRICTED_ZONE_CONFLICT")
    building_distance = distance_to_polygon(point, site.building)
    minimum_distance = max(site.min_crane_to_building_m, TOWER_PROTECTION_RADIUS_M)
    if building_distance + EPS < minimum_distance or building_distance > site.max_crane_to_building_m + EPS:
        reasons.append("BASE_CLEARANCE_CONFLICT")

    maximum_radius = min(config.jib_length_m, config.capacity_curve[-1][0])
    required_radius = 0.0
    capacity_margin = float("inf")
    height_margin = float("inf")
    critical_id: str | None = None

    for index, work_point in enumerate(project.work_points):
        radius = distance(point, work_point.point)
        required_radius = max(required_radius, radius)
        if radius > maximum_radius + EPS:
            reasons.append("REACH_EXCEEDED")
        for load in _loads_for_work_point(project,index):
            operation_id = f"WP-{index + 1}:{work_point.name}:{load.name}"
            available_capacity = allowed_capacity_kg(config, radius)
            margin = available_capacity - (float(load.load_kg) + float(load.rigging_kg))
            if margin < capacity_margin:
                capacity_margin = margin
                critical_id = operation_id
            if margin < -EPS:
                reasons.append("CAPACITY_INSUFFICIENT")

            try:
                hook_height = required_hook_height(
                    work_point.level_m,
                    load.height_m,
                    DEFAULT_RIGGING_HEIGHT_M,
                    True,
                )
            except NormativeInputError:
                return _blocked_result(project, config, point)
            current_height_margin = config.max_free_standing_hook_height_m - hook_height
            height_margin = min(height_margin, current_height_margin)
            if current_height_margin < -EPS and not project.tie_ins_possible:
                reasons.append("HEIGHT_INSUFFICIENT")

            if not _ray_is_clear(point, work_point.point, project):
                reasons.append("ROUTE_CONFLICT")

            if not project.protective_screen_possible:
                try:
                    danger_offset = danger_zone_offset_from_outer_edge(
                        work_point.level_m,
                        load.largest_dimension_m,
                    )
                except NormativeInputError:
                    return _blocked_result(project, config, point)
                if distance_to_polygon(work_point.point, site.boundary) + EPS < danger_offset:
                    reasons.append("DANGER_ZONE_CONFLICT")

    stable_reasons = tuple(dict.fromkeys(reasons))
    return CandidateEvaluation(
        point=(float(point[0]), float(point[1])),
        passed=not stable_reasons,
        reason_codes=stable_reasons,
        critical_operation_id=critical_id,
        required_radius_m=required_radius,
        capacity_margin_kg=0.0 if capacity_margin == float("inf") else capacity_margin,
        height_margin_m=0.0 if height_margin == float("inf") else height_margin,
        source_locators=_source_locators(project, config),
    )


def _component_count(points: tuple[Point, ...], neighbour_distance: float) -> int:
    remaining = set(points)
    components = 0
    while remaining:
        components += 1
        queue = deque([remaining.pop()])
        while queue:
            current = queue.popleft()
            neighbours = {
                candidate
                for candidate in remaining
                if hypot(candidate[0] - current[0], candidate[1] - current[1]) <= neighbour_distance + EPS
            }
            remaining.difference_update(neighbours)
            queue.extend(neighbours)
    return components


def calculate_admissible_area(
    project: ProjectInput,
    config: CraneConfiguration,
    step_m: float,
    refinement_levels: int,
    run_id: str,
) -> AdmissibleAreaRun:
    """Evaluate a regular grid and refine only mixed-status cells."""

    if not run_id.strip():
        raise ValueError("run_id is required")
    if not isfinite(step_m) or step_m <= 0:
        raise ValueError("step_m must be a positive finite number")
    if refinement_levels < 0:
        raise ValueError("refinement_levels cannot be negative")

    started = perf_counter()
    min_x, min_y, max_x, max_y = polygon_bounds(project.site.boundary)
    cache: dict[Point, CandidateEvaluation] = {}

    def result_at(candidate: Point) -> CandidateEvaluation:
        key = (round(candidate[0], 9), round(candidate[1], 9))
        if key not in cache:
            cache[key] = evaluate_candidate(project, config, key)
        return cache[key]

    cells: list[tuple[float, float, float, float]] = []
    y = min_y
    while y < max_y - EPS:
        x = min_x
        cell_height = min(step_m, max_y - y)
        while x < max_x - EPS:
            cell_width = min(step_m, max_x - x)
            cells.append((x, y, cell_width, cell_height))
            for corner in (
                (x, y),
                (x + cell_width, y),
                (x, y + cell_height),
                (x + cell_width, y + cell_height),
            ):
                result_at(corner)
            x += step_m
        y += step_m

    terminal_cells: list[tuple[float, float, float, float]] = []
    active_cells = cells
    evaluated_steps = [step_m]
    for level in range(refinement_levels + 1):
        next_cells: list[tuple[float, float, float, float]] = []
        for x, y, width, height in active_cells:
            corners = (
                (x, y),
                (x + width, y),
                (x, y + height),
                (x + width, y + height),
            )
            statuses = {result_at(corner).passed for corner in corners}
            if level < refinement_levels and len(statuses) > 1:
                half_width = width / 2.0
                half_height = height / 2.0
                for dx, dy in (
                    (0.0, 0.0),
                    (half_width, 0.0),
                    (0.0, half_height),
                    (half_width, half_height),
                ):
                    child = (x + dx, y + dy, half_width, half_height)
                    next_cells.append(child)
                    cx, cy, cw, ch = child
                    for corner in (
                        (cx, cy),
                        (cx + cw, cy),
                        (cx, cy + ch),
                        (cx + cw, cy + ch),
                    ):
                        result_at(corner)
            else:
                terminal_cells.append((x, y, width, height))
        if not next_cells:
            break
        active_cells = next_cells
        evaluated_steps.append(step_m / (2 ** (level + 1)))

    area = 0.0
    for x, y, width, height in terminal_cells:
        corners = (
            (x, y),
            (x + width, y),
            (x, y + height),
            (x + width, y + height),
        )
        accepted_fraction = sum(result_at(corner).passed for corner in corners) / 4.0
        area += accepted_fraction * width * height

    evaluations = tuple(cache[key] for key in sorted(cache, key=lambda item: (item[1], item[0])))
    accepted = tuple(item.point for item in evaluations if item.passed)
    counts: Counter[str] = Counter()
    for item in evaluations:
        if item.passed:
            counts["PASS"] += 1
        else:
            counts.update(item.reason_codes)

    project_hash = _canonical_hash(project.to_dict())
    config_hash = _canonical_hash(asdict(config))
    finest_step = step_m / (2 ** refinement_levels)
    return AdmissibleAreaRun(
        run_id=run_id,
        algorithm_version=ALGORITHM_VERSION,
        step_m=float(step_m),
        refinement_levels=int(refinement_levels),
        evaluated_steps_m=tuple(evaluated_steps),
        candidate_evaluations=evaluations,
        accepted_points=accepted,
        counts_by_reason=dict(sorted(counts.items())),
        area_estimate_m2=round(area, 9),
        connected_component_count=_component_count(accepted, max(step_m, finest_step) * 1.01),
        duration_seconds=perf_counter() - started,
        input_hashes=(("project_sha256", project_hash), ("crane_configuration_sha256", config_hash)),
    )
