"""Polar, height-aware route planning for tower-crane lift operations."""

from __future__ import annotations

import hashlib
import heapq
import json
from dataclasses import asdict, dataclass
from math import atan2, cos, degrees, hypot, pi, radians, sin
from typing import Callable, Sequence

from .geometry import (
    EPS,
    normalize_angular_sector,
    arc_intersects_polygon_exact,
    arc_inside_polygon_with_clearance,
    distance_point_to_segment,
    distance_arc_to_segment,
    distance_segment_to_segment,
    distance_to_polygon,
    point_in_polygon,
    sector_intersects_polygon_exact,
    segment_intersects_polygon_exact,
    segment_inside_polygon_with_clearance,
    segments_intersect,
)
from .models import (
    LiftRoute,
    Load,
    Point,
    ProjectInput,
    RouteAlternative,
    RouteEndpoint,
    RouteFailure,
    RouteFailureCode,
    RoutePlanResult,
    RouteWaypoint,
)
from .normative import NormativeInputError, danger_zone_offset_from_outer_edge
from .restricted_zones import buffered_zone_polygon, jib_may_overfly, load_may_overfly


@dataclass(frozen=True)
class RoutePlannerSettings:
    angle_step_deg: float = 1.0
    radius_step_m: float = 0.5
    vertical_clearance_m: float = 3.0
    minimum_radius_m: float = 0.0

    def __post_init__(self) -> None:
        if self.angle_step_deg <= 0 or self.angle_step_deg > 180:
            raise ValueError("Шаг угла должен быть в диапазоне (0; 180]")
        if self.radius_step_m <= 0:
            raise ValueError("Шаг вылета должен быть положительным")
        if self.vertical_clearance_m < 0 or self.minimum_radius_m < 0:
            raise ValueError("Запасы и минимальный вылет не могут быть отрицательными")


@dataclass(frozen=True)
class OtherCraneConstraint:
    crane_id: str
    tower_center: Point
    tower_radius_m: float
    jib_level_m: float
    jib_height_m: float
    routes: tuple[LiftRoute, ...]
    permitted_sectors: tuple[tuple[float, float], ...]
    jib_length_m: float = 0.0

    def __post_init__(self) -> None:
        if self.tower_radius_m < 0 or self.jib_height_m <= 0 or self.jib_length_m < 0:
            raise ValueError("Габариты соседнего крана должны быть положительными")


def _angle_in_sectors(angle: float, sectors: tuple[tuple[float, float], ...]) -> bool:
    if not sectors:
        return True
    angle %= 360.0
    for start, end in sectors:
        start, end, sweep = normalize_angular_sector(start, end)
        if sweep == 360.0:
            return True
        if (start <= end and start-EPS <= angle <= end+EPS) or (start > end and (angle >= start-EPS or angle <= end+EPS)):
            return True
    return False


def _vertical_conflict(bottom_a: float, height_a: float, bottom_b: float, height_b: float, clearance: float = 1.0) -> bool:
    top_a=bottom_a+height_a; top_b=bottom_b+height_b
    return not (top_a+clearance <= bottom_b+EPS or top_b+clearance <= bottom_a+EPS)


def _active_other_jibs(other: OtherCraneConstraint):
    for route in other.routes:
        for waypoint in route.waypoints:
            point=waypoint.point
            _,angle=_polar(point,other.tower_center)
            if _angle_in_sectors(angle,other.permitted_sectors):
                jib_tip = (
                    _point(other.tower_center, other.jib_length_m, angle)
                    if other.jib_length_m > EPS
                    else point
                )
                yield other.tower_center,jib_tip


def _segment_buffer_polygon(start: Point, end: Point, radius: float = 1e-6) -> list[Point]:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = hypot(dx, dy)
    if length <= EPS:
        return [
            (start[0] - radius, start[1] - radius), (start[0] + radius, start[1] - radius),
            (start[0] + radius, start[1] + radius), (start[0] - radius, start[1] + radius),
        ]
    nx, ny = -dy / length * radius, dx / length * radius
    return [(start[0] + nx, start[1] + ny), (end[0] + nx, end[1] + ny),
            (end[0] - nx, end[1] - ny), (start[0] - nx, start[1] - ny)]


def _circle_polygon(center: Point, radius: float, sides: int = 48) -> list[Point]:
    effective = max(radius, 1e-6)
    return [
        (center[0] + effective * cos(2 * pi * index / sides), center[1] + effective * sin(2 * pi * index / sides))
        for index in range(sides)
    ]


def _polar(point: Point, origin: Point) -> tuple[float, float]:
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    return hypot(dx, dy), degrees(atan2(dy, dx)) % 360.0


def _point(origin: Point, radius: float, angle_deg: float) -> Point:
    angle = radians(angle_deg)
    return (origin[0] + radius * cos(angle), origin[1] + radius * sin(angle))


def _axis(step: float, upper: float, extras: tuple[float, ...], lower: float = 0.0) -> list[float]:
    values: list[float] = []
    value = lower
    while value <= upper + EPS:
        values.append(round(value, 9))
        value += step
    values.extend(value for value in extras if lower - EPS <= value <= upper + EPS)
    return sorted(set(round(value, 9) for value in values))


def _input_hash(project: ProjectInput, source: RouteEndpoint, destination: RouteEndpoint, settings: RoutePlannerSettings, other_cranes: Sequence[OtherCraneConstraint]) -> str:
    payload = {
        "project": project.to_dict(),
        "source": source.__dict__,
        "destination": destination.__dict__,
        "settings": settings.__dict__,
        "other_cranes": [asdict(item) for item in other_cranes],
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _transport_heights(
    load: Load,
    source: RouteEndpoint,
    destination: RouteEndpoint,
    project: ProjectInput,
    settings: RoutePlannerSettings,
    max_hook_height_m: float,
) -> list[float]:
    load_below_hook = load.rigging_height_m + load.height_m
    minimum = max(source.level_m, destination.level_m) + load_below_hook
    values = [minimum]
    for zone in project.site.restricted_zones:
        values.append(zone.height_m + settings.vertical_clearance_m + load_below_hook)
    return sorted(set(round(value, 9) for value in values if value <= max_hook_height_m + EPS))


def _edge_length(a: tuple[int, int], b: tuple[int, int], angles: list[float], radii: list[float]) -> float:
    ai, ri = a
    aj, rj = b
    if ai == aj:
        return abs(radii[ri] - radii[rj])
    delta = min((angles[ai] - angles[aj]) % 360.0, (angles[aj] - angles[ai]) % 360.0)
    return radii[ri] * radians(delta)


def plan_lift_route(
    crane_point: Point,
    jib_length_m: float,
    jib_bottom_m: float,
    max_hook_height_m: float,
    load: Load,
    source: RouteEndpoint,
    destination: RouteEndpoint,
    project: ProjectInput,
    capacity_at_radius: Callable[[float], float],
    settings: RoutePlannerSettings,
    other_cranes: Sequence[OtherCraneConstraint] = (),
) -> RoutePlanResult:
    source_radius, source_angle = _polar(source.point, crane_point)
    destination_radius, destination_angle = _polar(destination.point, crane_point)
    operation_id = f"{source.id}->{destination.id}"
    failures_seen: dict[RouteFailureCode, RouteFailure] = {}

    if source_radius > jib_length_m + EPS:
        failure = RouteFailure(RouteFailureCode.SOURCE_BLOCKED, "Источник находится за максимальным вылетом")
        return RoutePlanResult(None, [failure])
    if destination_radius > jib_length_m + EPS:
        failure = RouteFailure(RouteFailureCode.DESTINATION_BLOCKED, "Точка подачи находится за максимальным вылетом")
        return RoutePlanResult(None, [failure])

    angles = _axis(settings.angle_step_deg, 360.0 - settings.angle_step_deg, ())
    angles = sorted(set(angles + [round(source_angle, 9), round(destination_angle, 9)]))
    radii = _axis(settings.radius_step_m, jib_length_m, (source_radius, destination_radius), settings.minimum_radius_m)
    heights = _transport_heights(load, source, destination, project, settings, max_hook_height_m)
    if not heights:
        failure = RouteFailure(
            RouteFailureCode.HEIGHT_EXCEEDED,
            "Требуемая транспортная высота превышает допустимую высоту крюка",
            required_m=max(source.level_m, destination.level_m) + load.rigging_height_m + load.height_m,
            actual_m=max_hook_height_m,
        )
        return RoutePlanResult(None, [failure])

    start = (angles.index(round(source_angle, 9)), radii.index(round(source_radius, 9)))
    goal = (angles.index(round(destination_angle, 9)), radii.index(round(destination_radius, 9)))
    candidates: list[tuple[float, float, float, list[tuple[int, int]], set[str]]] = []
    rejected_alternatives: list[RouteAlternative] = []

    for hook_height in heights:
        load_bottom = hook_height - load.rigging_height_m - load.height_m
        try:
            danger_offset = danger_zone_offset_from_outer_edge(
                max(source.level_m, destination.level_m, EPS), load.largest_dimension_m
            )
        except NormativeInputError as error:
            return RoutePlanResult(None, [RouteFailure(RouteFailureCode.SITE_BOUNDARY, str(error))])
        state_cache: dict[tuple[int, int], bool] = {}
        clearance_cache: dict[tuple[int, int], float] = {}

        def valid_state(node: tuple[int, int]) -> bool:
            if node in state_cache:
                return state_cache[node]
            angle_index, radius_index = node
            angle, radius = angles[angle_index], radii[radius_index]
            load_point = _point(crane_point, radius, angle)
            if capacity_at_radius(radius) + EPS < load.total_kg:
                failures_seen.setdefault(
                    RouteFailureCode.CAPACITY_EXCEEDED,
                    RouteFailure(
                        RouteFailureCode.CAPACITY_EXCEEDED,
                        "Грузоподъёмность недостаточна на требуемом вылете",
                        required_m=load.total_kg,
                        actual_m=capacity_at_radius(radius),
                    ),
                )
                state_cache[node] = False
                return False
            if not point_in_polygon(load_point, project.site.boundary, include_boundary=True) or (
                not project.protective_screen_possible
                and distance_to_polygon(load_point, project.site.boundary) + EPS < danger_offset
            ):
                failures_seen.setdefault(
                    RouteFailureCode.SITE_BOUNDARY,
                    RouteFailure(RouteFailureCode.SITE_BOUNDARY, "Траектория выходит за границу стройплощадки"),
                )
                state_cache[node] = False
                return False
            jib_tip = _point(crane_point, jib_length_m, angle)
            for other in other_cranes:
                if distance_point_to_segment(other.tower_center,crane_point,jib_tip) <= other.tower_radius_m+EPS:
                    failures_seen.setdefault(
                        RouteFailureCode.SECOND_CRANE_CONFLICT,
                        RouteFailure(RouteFailureCode.SECOND_CRANE_CONFLICT,f"Конфликт башня–стрела с {other.crane_id}",zone_id=other.crane_id),
                    )
                    state_cache[node]=False; return False
                if _vertical_conflict(jib_bottom_m,2.0,other.jib_level_m,other.jib_height_m):
                    for other_start,other_end in _active_other_jibs(other):
                        if segments_intersect(crane_point,jib_tip,other_start,other_end):
                            failures_seen.setdefault(
                                RouteFailureCode.SECOND_CRANE_CONFLICT,
                                RouteFailure(RouteFailureCode.SECOND_CRANE_CONFLICT,f"Конфликт стрела–стрела с {other.crane_id}",zone_id=other.crane_id),
                            )
                            state_cache[node]=False; return False
                load_radius=max(load.length_m,load.width_m)/2.0
                load_top=hook_height-load.rigging_height_m
                load_height=max(load.height_m,load_top-load_bottom)
                if _vertical_conflict(load_bottom,load_height,other.jib_level_m,other.jib_height_m):
                    for other_start,other_end in _active_other_jibs(other):
                        if distance_point_to_segment(load_point,other_start,other_end) <= load_radius+EPS:
                            failures_seen.setdefault(
                                RouteFailureCode.SECOND_CRANE_CONFLICT,
                                RouteFailure(RouteFailureCode.SECOND_CRANE_CONFLICT,f"Конфликт груз–стрела с {other.crane_id}",zone_id=other.crane_id),
                            )
                            state_cache[node]=False; return False
            for zone in project.site.restricted_zones:
                polygon = buffered_zone_polygon(zone)
                if not load_may_overfly(zone, load_bottom, settings.vertical_clearance_m) and point_in_polygon(load_point, polygon):
                    state_cache[node] = False
                    return False
                if not jib_may_overfly(zone, jib_bottom_m, settings.vertical_clearance_m) and segment_intersects_polygon_exact(crane_point, jib_tip, polygon):
                    state_cache[node] = False
                    return False
            state_cache[node] = True
            return True

        def state_clearance(node: tuple[int, int]) -> float:
            if node in clearance_cache:
                return clearance_cache[node]
            angle_index, radius_index = node
            angle, radius = angles[angle_index], radii[radius_index]
            load_point = _point(crane_point, radius, angle)
            jib_tip = _point(crane_point, jib_length_m, angle)
            clearance = distance_to_polygon(load_point, project.site.boundary)
            for zone in project.site.restricted_zones:
                polygon = buffered_zone_polygon(zone)
                if load_may_overfly(zone, load_bottom, settings.vertical_clearance_m):
                    clearance = min(clearance, load_bottom - zone.height_m - settings.vertical_clearance_m)
                else:
                    clearance = min(clearance, distance_to_polygon(load_point, polygon))
                if jib_may_overfly(zone, jib_bottom_m, settings.vertical_clearance_m):
                    clearance = min(clearance, jib_bottom_m - zone.height_m - settings.vertical_clearance_m)
                else:
                    boom_clearance = min(
                        [distance_point_to_segment(point, crane_point, jib_tip) for point in polygon]
                        + [distance_to_polygon(crane_point, polygon), distance_to_polygon(jib_tip, polygon)]
                    )
                    clearance = min(clearance, boom_clearance)
            clearance_cache[node] = max(0.0, clearance)
            return clearance_cache[node]

        if not valid_state(start):
            failure = RouteFailure(RouteFailureCode.SOURCE_BLOCKED, "Исходная точка заблокирована")
            failures_seen.setdefault(RouteFailureCode.SOURCE_BLOCKED, failure)
            rejected_alternatives.append(RouteAlternative(f"height:{hook_height:g}", False, 0.0, 0.0, (failure,)))
            continue
        if not valid_state(goal):
            failure = RouteFailure(RouteFailureCode.DESTINATION_BLOCKED, "Точка подачи заблокирована")
            failures_seen.setdefault(RouteFailureCode.DESTINATION_BLOCKED, failure)
            rejected_alternatives.append(RouteAlternative(f"height:{hook_height:g}", False, 0.0, 0.0, (failure,)))
            continue

        exact_reject = False

        def valid_edge(a: tuple[int, int], b: tuple[int, int]) -> bool:
            nonlocal exact_reject
            ai, ri = a
            aj, rj = b
            height_bottom = load_bottom
            if ai == aj:
                start_point = _point(crane_point, radii[ri], angles[ai])
                end_point = _point(crane_point, radii[rj], angles[ai])
                if not project.protective_screen_possible and not segment_inside_polygon_with_clearance(
                    start_point, end_point, project.site.boundary, danger_offset
                ):
                    failures_seen.setdefault(
                        RouteFailureCode.SITE_BOUNDARY,
                        RouteFailure(RouteFailureCode.SITE_BOUNDARY, "Нормативная опасная зона груза выходит за границу стройплощадки", required_m=danger_offset),
                    )
                    exact_reject = True
                    return False
                load_radius = max(load.length_m, load.width_m) / 2.0
                load_height = load.height_m
                for other in other_cranes:
                    if _vertical_conflict(load_bottom, load_height, other.jib_level_m, other.jib_height_m):
                        for other_start, other_end in _active_other_jibs(other):
                            if distance_segment_to_segment(start_point, end_point, other_start, other_end) <= load_radius + EPS:
                                failures_seen.setdefault(
                                    RouteFailureCode.SECOND_CRANE_CONFLICT,
                                    RouteFailure(RouteFailureCode.SECOND_CRANE_CONFLICT, f"Конфликт груз–стрела с {other.crane_id} на участке маршрута", zone_id=other.crane_id),
                                )
                                exact_reject = True
                                return False
                for zone in project.site.restricted_zones:
                    if not load_may_overfly(zone, height_bottom, settings.vertical_clearance_m) and segment_intersects_polygon_exact(start_point, end_point, buffered_zone_polygon(zone)):
                        exact_reject = True
                        return False
                return True
            clockwise = (angles[ai] - angles[aj]) % 360.0 < (angles[aj] - angles[ai]) % 360.0
            if not project.protective_screen_possible and not arc_inside_polygon_with_clearance(
                crane_point, radii[ri], angles[ai], angles[aj], clockwise,
                project.site.boundary, danger_offset,
            ):
                failures_seen.setdefault(
                    RouteFailureCode.SITE_BOUNDARY,
                    RouteFailure(RouteFailureCode.SITE_BOUNDARY, "Нормативная опасная зона груза выходит за границу стройплощадки", required_m=danger_offset),
                )
                exact_reject = True
                return False
            load_radius = max(load.length_m, load.width_m) / 2.0
            load_height = load.height_m
            for other in other_cranes:
                if sector_intersects_polygon_exact(
                    crane_point, jib_length_m, angles[ai], angles[aj], clockwise,
                    _circle_polygon(other.tower_center, other.tower_radius_m),
                ):
                    failures_seen.setdefault(
                        RouteFailureCode.SECOND_CRANE_CONFLICT,
                        RouteFailure(RouteFailureCode.SECOND_CRANE_CONFLICT, f"Конфликт башня–стрела с {other.crane_id} на секторе поворота", zone_id=other.crane_id),
                    )
                    exact_reject = True
                    return False
                for other_start, other_end in _active_other_jibs(other):
                    if _vertical_conflict(jib_bottom_m, 2.0, other.jib_level_m, other.jib_height_m) and sector_intersects_polygon_exact(
                        crane_point, jib_length_m, angles[ai], angles[aj], clockwise,
                        _segment_buffer_polygon(other_start, other_end),
                    ):
                        failures_seen.setdefault(
                            RouteFailureCode.SECOND_CRANE_CONFLICT,
                            RouteFailure(RouteFailureCode.SECOND_CRANE_CONFLICT, f"Конфликт стрела–стрела с {other.crane_id} на секторе поворота", zone_id=other.crane_id),
                        )
                        exact_reject = True
                        return False
                    if _vertical_conflict(load_bottom, load_height, other.jib_level_m, other.jib_height_m) and distance_arc_to_segment(
                        crane_point, radii[ri], angles[ai], angles[aj], clockwise, other_start, other_end
                    ) <= load_radius + EPS:
                        failures_seen.setdefault(
                            RouteFailureCode.SECOND_CRANE_CONFLICT,
                            RouteFailure(RouteFailureCode.SECOND_CRANE_CONFLICT, f"Конфликт груз–стрела с {other.crane_id} на дуге маршрута", zone_id=other.crane_id),
                        )
                        exact_reject = True
                        return False
            for zone in project.site.restricted_zones:
                polygon = buffered_zone_polygon(zone)
                if not load_may_overfly(zone, height_bottom, settings.vertical_clearance_m) and arc_intersects_polygon_exact(
                    crane_point, radii[ri], angles[ai], angles[aj], clockwise, polygon
                ):
                    exact_reject = True
                    return False
                if not jib_may_overfly(zone, jib_bottom_m, settings.vertical_clearance_m) and sector_intersects_polygon_exact(
                    crane_point, jib_length_m, angles[ai], angles[aj], clockwise, polygon
                ):
                    exact_reject = True
                    return False
            return True

        best = {start: (state_clearance(start), 0.0)}
        parents: dict[tuple[int, int], tuple[int, int]] = {}
        queue = [(-state_clearance(start), 0.0, start)]
        while queue:
            negative_clearance, distance_so_far, node = heapq.heappop(queue)
            clearance_so_far = -negative_clearance
            known_clearance, known_distance = best.get(node, (-1.0, float("inf")))
            if clearance_so_far + EPS < known_clearance or (
                abs(clearance_so_far - known_clearance) <= EPS and distance_so_far > known_distance + EPS
            ):
                continue
            if node == goal:
                break
            angle_index, radius_index = node
            neighbours = [
                ((angle_index - 1) % len(angles), radius_index),
                ((angle_index + 1) % len(angles), radius_index),
            ]
            if radius_index > 0:
                neighbours.append((angle_index, radius_index - 1))
            if radius_index + 1 < len(radii):
                neighbours.append((angle_index, radius_index + 1))
            for neighbour in neighbours:
                if not valid_state(neighbour) or not valid_edge(node, neighbour):
                    continue
                candidate_distance = distance_so_far + _edge_length(node, neighbour, angles, radii)
                candidate_clearance = min(clearance_so_far, state_clearance(neighbour))
                previous_clearance, previous_distance = best.get(neighbour, (-1.0, float("inf")))
                if candidate_clearance > previous_clearance + EPS or (
                    abs(candidate_clearance - previous_clearance) <= EPS
                    and candidate_distance + EPS < previous_distance
                ):
                    best[neighbour] = (candidate_clearance, candidate_distance)
                    parents[neighbour] = node
                    heapq.heappush(queue, (-candidate_clearance, candidate_distance, neighbour))

        if goal not in best:
            alternative_failures: list[RouteFailure] = []
            if exact_reject:
                exact_failure = failures_seen.setdefault(
                    RouteFailureCode.EXACT_RECHECK_FAILED,
                    RouteFailure(RouteFailureCode.EXACT_RECHECK_FAILED, "Дискретный переход отклонён точной геометрической проверкой"),
                )
                alternative_failures.append(exact_failure)
            alternative_failures.append(
                RouteFailure(RouteFailureCode.NO_PATH, f"Маршрут на высоте крюка {hook_height:g} м не найден")
            )
            rejected_alternatives.append(
                RouteAlternative(f"height:{hook_height:g}", False, 0.0, 0.0, tuple(alternative_failures))
            )
            continue

        nodes = [goal]
        while nodes[-1] != start:
            nodes.append(parents[nodes[-1]])
        nodes.reverse()
        route_radii = [radii[node[1]] for node in nodes]
        kinds: set[str] = set()
        endpoint_min = min(source_radius, destination_radius)
        endpoint_max = max(source_radius, destination_radius)
        if min(route_radii) < endpoint_min - EPS:
            kinds.add("inner")
        if max(route_radii) > endpoint_max + EPS:
            kinds.add("outer")
        minimum_hook = max(source.level_m, destination.level_m) + load.rigging_height_m + load.height_m
        if hook_height > minimum_hook + EPS:
            kinds.add("over")
        if not kinds:
            kinds.add("direct")
        route_clearance, route_distance = best[goal]
        candidates.append((route_clearance, route_distance, hook_height, nodes, kinds))

    if not candidates:
        failures = list(failures_seen.values())
        failures.append(RouteFailure(RouteFailureCode.NO_PATH, "Безопасный маршрут не найден ни для одной проверенной высоты"))
        return RoutePlanResult(None, failures)

    route_clearance, path_length, hook_height, nodes, kinds = min(
        candidates, key=lambda item: (-item[0], item[1], -item[2])
    )
    waypoints: list[RouteWaypoint] = []
    previous = None
    for index, node in enumerate(nodes):
        angle_index, radius_index = node
        point = source.point if index == 0 else destination.point if index == len(nodes) - 1 else _point(crane_point, radii[radius_index], angles[angle_index])
        if previous is None:
            movement = "hoist"
        elif previous[0] == angle_index:
            movement = "trolley"
        else:
            movement = "slew"
        waypoints.append(RouteWaypoint(point[0], point[1], hook_height, movement))
        previous = node
    alternatives = tuple(rejected_alternatives) + tuple(
        RouteAlternative(kind, True, route_clearance, path_length) for kind in sorted(kinds)
    )
    route = LiftRoute(
        operation_id=operation_id,
        waypoints=tuple(waypoints),
        transport_hook_height_m=hook_height,
        alternatives=alternatives,
        input_sha256=_input_hash(project, source, destination, settings, other_cranes),
    )
    return RoutePlanResult(route, [])

