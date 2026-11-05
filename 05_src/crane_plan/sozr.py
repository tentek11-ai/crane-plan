"""Build one deterministic graphical SOZR model per crane."""

from __future__ import annotations

from math import atan2, degrees, hypot

from .geometry import (
    EPS, distance, distance_to_polygon, point_in_polygon, segment_circle_intersections,
    segment_intersects_polygon_exact,
)
from .models import (
    LiftRoute,
    Point,
    ProjectInput,
    RestrictedZone,
    RestrictedZoneKind,
    SOZRContour,
    SOZRPlan,
    SOZRPoint,
    SOZRRestrictionClass,
)
from .restricted_zones import buffered_zone_polygon
from .normative import NormativeInputError, danger_zone_offset_from_outer_edge


ALGORITHM_VERSION = "SOZR-1.0"


def bearing_from_north_clockwise(origin: Point, point: Point) -> float:
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    return round(degrees(atan2(dx, dy)) % 360.0, 9)


def _restriction(zone: RestrictedZone) -> tuple[SOZRRestrictionClass, str]:
    if zone.kind is RestrictedZoneKind.HEIGHT_OBSTACLE:
        return (
            SOZRRestrictionClass.CONDITIONAL,
            f"Проход разрешён только при нижней отметке груза и стрелы не ниже {zone.height_m + 3.0:g} м",
        )
    if zone.kind is RestrictedZoneKind.LOAD_PROHIBITED:
        return (
            SOZRRestrictionClass.PERMANENT,
            "Пронос груза запрещён; проход пустой стрелы проверяется по высоте",
        )
    return SOZRRestrictionClass.PERMANENT, "Постоянный полный запрет"


def _segment_intersection(a: Point, b: Point, c: Point, d: Point) -> Point | None:
    ab = (b[0] - a[0], b[1] - a[1])
    cd = (d[0] - c[0], d[1] - c[1])
    denominator = ab[0] * cd[1] - ab[1] * cd[0]
    if abs(denominator) <= EPS:
        return None
    ac = (c[0] - a[0], c[1] - a[1])
    t = (ac[0] * cd[1] - ac[1] * cd[0]) / denominator
    u = (ac[0] * ab[1] - ac[1] * ab[0]) / denominator
    if -EPS <= t <= 1.0 + EPS and -EPS <= u <= 1.0 + EPS:
        return (a[0] + t * ab[0], a[1] + t * ab[1])
    return None


def _prefix(crane_id: str) -> str:
    if crane_id.startswith("К"):
        return crane_id
    digits = "".join(character for character in crane_id if character.isdigit())
    return f"К{digits}" if digits else f"К{crane_id}"


def _angle_allowed(angle: float, sector: tuple[float, float] | None) -> bool:
    if sector is None:
        return True
    if abs(sector[1] - sector[0]) >= 360.0 - EPS:
        return True
    start, end = sector[0] % 360.0, sector[1] % 360.0
    angle %= 360.0
    return start - EPS <= angle <= end + EPS if start <= end else angle >= start - EPS or angle <= end + EPS


def _cell_intersects_polygon(cell: tuple[Point, ...], polygon: list[Point]) -> bool:
    if any(point_in_polygon(point, polygon) for point in cell) or any(point_in_polygon(point, list(cell)) for point in polygon):
        return True
    return any(
        segment_intersects_polygon_exact(cell[index], cell[(index + 1) % len(cell)], polygon)
        for index in range(len(cell))
    )


def _admissible_cells(
    crane_point: Point,
    technical_radius_m: float,
    zones: list[RestrictedZone],
    routes: list[LiftRoute],
    project: ProjectInput,
    allowed_sector: tuple[float, float] | None,
) -> tuple[tuple[Point, ...], ...]:
    radius_limit = technical_radius_m
    if routes:
        per_route = [max((distance(crane_point, point.point) for point in route.waypoints), default=0.0) for route in routes]
        positive = [value for value in per_route if value > EPS]
        if positive:
            radius_limit = min(radius_limit, min(positive))
    danger_offset = 0.0
    if not project.protective_screen_possible:
        levels = [max(point.level_m, EPS) for point in project.work_points] or [EPS]
        for load in (item for item in project.loads if item.active):
            for level in levels:
                try:
                    danger_offset = max(danger_offset, danger_zone_offset_from_outer_edge(level, load.largest_dimension_m))
                except NormativeInputError:
                    return ()
    step = max(1.0, min(2.0, radius_limit / 25.0 if radius_limit > EPS else 1.0))
    buffered = [buffered_zone_polygon(zone) for zone in zones]
    result: list[tuple[Point, ...]] = []
    x = crane_point[0] - radius_limit
    while x < crane_point[0] + radius_limit - EPS:
        y = crane_point[1] - radius_limit
        while y < crane_point[1] + radius_limit - EPS:
            cell = ((x, y), (x + step, y), (x + step, y + step), (x, y + step))
            center = (x + step / 2.0, y + step / 2.0)
            corners_ok = all(
                distance(crane_point, point) <= radius_limit + EPS
                and point_in_polygon(point, project.site.boundary, include_boundary=False)
                and distance_to_polygon(point, project.site.boundary) + EPS >= danger_offset
                for point in cell
            )
            if (
                corners_ok
                and _angle_allowed(degrees(atan2(center[1] - crane_point[1], center[0] - crane_point[0])) % 360.0, allowed_sector)
                and not any(_cell_intersects_polygon(cell, polygon) for polygon in buffered)
            ):
                result.append(cell)
            y += step
        x += step
    return tuple(result)


def build_sozr_plan(
    crane_id: str,
    crane_point: Point,
    technical_radius_m: float,
    zones: list[RestrictedZone],
    routes: list[LiftRoute],
    project: ProjectInput,
    allowed_sector: tuple[float, float] | None = None,
) -> SOZRPlan:
    contours: list[SOZRContour] = []
    candidates: list[tuple[Point, SOZRRestrictionClass, str, float, str]] = []
    by_class: dict[SOZRRestrictionClass, list[tuple[RestrictedZone, list[Point], str]]] = {
        SOZRRestrictionClass.PERMANENT: [],
        SOZRRestrictionClass.CONDITIONAL: [],
    }
    for zone in zones:
        polygon = buffered_zone_polygon(zone)
        restriction_class, condition = _restriction(zone)
        by_class[restriction_class].append((zone, polygon, condition))
        if any(distance(crane_point, point) <= technical_radius_m + EPS for point in polygon) or any(
            segment_circle_intersections(
                polygon[index], polygon[(index + 1) % len(polygon)], crane_point, technical_radius_m
            )
            for index in range(len(polygon))
        ):
            contours.append(
                SOZRContour(
                    zone.id,
                    tuple(polygon),
                    restriction_class,
                    zone.height_m,
                    condition,
                )
            )
        for point in polygon:
            if distance(crane_point, point) <= technical_radius_m + EPS:
                candidates.append((point, restriction_class, zone.id, zone.height_m, condition))
        for index in range(len(polygon)):
            for point in segment_circle_intersections(
                polygon[index], polygon[(index + 1) % len(polygon)], crane_point, technical_radius_m
            ):
                candidates.append((point, restriction_class, zone.id, zone.height_m, condition))

    for permanent_zone, permanent, _ in by_class[SOZRRestrictionClass.PERMANENT]:
        for conditional_zone, conditional, _ in by_class[SOZRRestrictionClass.CONDITIONAL]:
            for p_index in range(len(permanent)):
                for c_index in range(len(conditional)):
                    point = _segment_intersection(
                        permanent[p_index],
                        permanent[(p_index + 1) % len(permanent)],
                        conditional[c_index],
                        conditional[(c_index + 1) % len(conditional)],
                    )
                    if point is not None and distance(crane_point, point) <= technical_radius_m + EPS:
                        candidates.append(
                            (
                                point,
                                SOZRRestrictionClass.PERMANENT,
                                f"{permanent_zone.id}/{conditional_zone.id}",
                                max(permanent_zone.height_m, conditional_zone.height_m),
                                "Переход постоянного ограничения в условное высотное",
                            )
                        )

    unique: dict[tuple[int, int, str, str], tuple[Point, SOZRRestrictionClass, str, float, str]] = {}
    for candidate in candidates:
        point, restriction_class, zone_id, _, condition = candidate
        key = (
            round(point[0] * 1_000_000),
            round(point[1] * 1_000_000),
            zone_id,
            condition,
        )
        unique[key] = candidate
    ordered = sorted(
        unique.values(),
        key=lambda item: (
            bearing_from_north_clockwise(crane_point, item[0]),
            distance(crane_point, item[0]),
            item[1].value,
            item[2],
        ),
    )
    prefix = _prefix(crane_id)
    points = tuple(
        SOZRPoint(
            f"{prefix}-{index}",
            point[0],
            point[1],
            bearing_from_north_clockwise(crane_point, point),
            round(hypot(point[0] - crane_point[0], point[1] - crane_point[1]), 9),
            restriction_class,
            zone_id,
            zone_height,
            condition,
        )
        for index, (point, restriction_class, zone_id, zone_height, condition) in enumerate(ordered, start=1)
    )
    return SOZRPlan(
        crane_id,
        technical_radius_m,
        tuple(contour for contour in contours if contour.restriction_class is SOZRRestrictionClass.PERMANENT),
        tuple(contour for contour in contours if contour.restriction_class is SOZRRestrictionClass.CONDITIONAL),
        points,
        tuple(routes),
        ALGORITHM_VERSION,
        crane_point[0],
        crane_point[1],
        _admissible_cells(crane_point, technical_radius_m, zones, routes, project, allowed_sector),
    )
