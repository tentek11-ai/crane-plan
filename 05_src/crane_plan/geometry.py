"""Базовая 2D-геометрия для расчёта площадки."""

from __future__ import annotations

from math import atan2, degrees, hypot, isfinite, sqrt

from .models import Point


EPS = 1e-9


def normalize_angular_sector(start: float, end: float) -> tuple[float, float, float]:
    """Shared planner/drawing convention: only positive full turns mean 360°.

    A reverse whole turn (360→0) is a single bearing, while e.g. 400→30
    is the positive sweep from 40° to 30° (350°), not a full circle.
    """
    sweep = 360.0 if end - start >= 360.0 - EPS else (end % 360.0 - start % 360.0) % 360.0
    return start % 360.0, end % 360.0, sweep


def distance(a: Point, b: Point) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def section_contour_height(contour: list[Point]) -> float:
    """Return the vertical extent of a section contour in metres."""
    if not contour:
        return 0.0
    heights = [height for _, height in contour]
    return max(heights) - min(heights)


def point_in_polygon(point: Point, polygon: list[Point], include_boundary: bool = True) -> bool:
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        if distance_point_to_segment(point, a, b) <= EPS:
            return include_boundary
        if (a[1] > y) != (b[1] > y):
            x_cross = (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            if x < x_cross:
                inside = not inside
    return inside


def distance_point_to_segment(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= EPS:
        return distance(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length_sq))
    return distance(p, (a[0] + t * dx, a[1] + t * dy))


def distance_segment_to_segment(a: Point, b: Point, c: Point, d: Point) -> float:
    """Exact minimum distance between two closed 2D segments."""
    if segments_intersect(a, b, c, d):
        return 0.0
    return min(
        distance_point_to_segment(a, c, d),
        distance_point_to_segment(b, c, d),
        distance_point_to_segment(c, a, b),
        distance_point_to_segment(d, a, b),
    )


def distance_to_polygon(point: Point, polygon: list[Point]) -> float:
    if len(polygon) < 2:
        return float("inf")
    return min(distance_point_to_segment(point, polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon)))


def polygon_bounds(polygon: list[Point]) -> tuple[float, float, float, float]:
    return min(x for x, _ in polygon), min(y for _, y in polygon), max(x for x, _ in polygon), max(y for _, y in polygon)


def polygon_centroid(polygon: list[Point]) -> Point:
    if not polygon:
        raise ValueError("Пустой полигон")
    return sum(x for x, _ in polygon) / len(polygon), sum(y for _, y in polygon) / len(polygon)


def polygon_area(polygon: list[Point]) -> float:
    if len(polygon) < 3:
        return 0.0
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))) / 2.0


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if ((o1 > EPS and o2 < -EPS) or (o1 < -EPS and o2 > EPS)) and ((o3 > EPS and o4 < -EPS) or (o3 < -EPS and o4 > EPS)):
        return True
    return any(abs(o) <= EPS and distance_point_to_segment(p, s, e) <= EPS for o, p, s, e in (
        (o1, c, a, b), (o2, d, a, b), (o3, a, c, d), (o4, b, c, d)
    ))


def polygon_self_intersects(polygon: list[Point]) -> bool:
    count = len(polygon)
    for i in range(count):
        a, b = polygon[i], polygon[(i + 1) % count]
        for j in range(i + 1, count):
            if j in {i, (i + 1) % count} or (j + 1) % count in {i, (i + 1) % count}:
                continue
            if segments_intersect(a, b, polygon[j], polygon[(j + 1) % count]):
                return True
    return False


def segment_intersects_polygon(a: Point, b: Point, polygon: list[Point], include_endpoints: bool = True) -> bool:
    if include_endpoints and (point_in_polygon(a, polygon) or point_in_polygon(b, polygon)):
        return True
    return any(segments_intersect(a, b, polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon)))


def segment_intersects_polygon_exact(
    a: Point,
    b: Point,
    polygon: list[Point],
    boundary_is_collision: bool = True,
) -> bool:
    """Return whether a complete segment enters a polygon.

    When boundary contact is allowed, collinear/tangent contact is ignored but a
    proper crossing into the interior remains a collision.
    """
    if point_in_polygon(a, polygon, include_boundary=boundary_is_collision):
        return True
    if point_in_polygon(b, polygon, include_boundary=boundary_is_collision):
        return True
    if boundary_is_collision:
        return any(
            segments_intersect(a, b, polygon[index], polygon[(index + 1) % len(polygon)])
            for index in range(len(polygon))
        )

    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    for index in range(len(polygon)):
        c, d = polygon[index], polygon[(index + 1) % len(polygon)]
        o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
        if o1 * o2 < -EPS and o3 * o4 < -EPS:
            return True
    midpoint = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    return point_in_polygon(midpoint, polygon, include_boundary=False)


def segment_circle_intersections(a: Point, b: Point, center: Point, radius: float) -> list[Point]:
    if radius < 0:
        raise ValueError("Радиус не может быть отрицательным")
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - center[0], a[1] - center[1]
    coefficient = dx * dx + dy * dy
    if coefficient <= EPS:
        return [a] if abs(distance(a, center) - radius) <= EPS else []
    linear = 2.0 * (fx * dx + fy * dy)
    constant = fx * fx + fy * fy - radius * radius
    discriminant = linear * linear - 4.0 * coefficient * constant
    if discriminant < -EPS:
        return []
    roots = [-linear / (2.0 * coefficient)] if abs(discriminant) <= EPS else [
        (-linear - sqrt(max(0.0, discriminant))) / (2.0 * coefficient),
        (-linear + sqrt(max(0.0, discriminant))) / (2.0 * coefficient),
    ]
    result: list[Point] = []
    for ratio in sorted(roots):
        if -EPS <= ratio <= 1.0 + EPS:
            point = (a[0] + ratio * dx, a[1] + ratio * dy)
            normalized = (round(point[0], 12), round(point[1], 12))
            if normalized not in result:
                result.append(normalized)
    return result


def _angle_on_arc(angle: float, start: float, end: float, clockwise: bool) -> bool:
    angle, start, end = angle % 360.0, start % 360.0, end % 360.0
    if clockwise:
        return (start - angle) % 360.0 <= (start - end) % 360.0 + EPS
    return (angle - start) % 360.0 <= (end - start) % 360.0 + EPS


def arc_intersects_polygon_exact(
    center: Point,
    radius: float,
    start_deg: float,
    end_deg: float,
    clockwise: bool,
    polygon: list[Point],
    boundary_is_collision: bool = True,
) -> bool:
    if radius < 0:
        raise ValueError("Радиус не может быть отрицательным")
    start_radians = start_deg * 3.141592653589793 / 180.0
    end_radians = end_deg * 3.141592653589793 / 180.0
    from math import cos, sin

    start_point = (center[0] + radius * cos(start_radians), center[1] + radius * sin(start_radians))
    end_point = (center[0] + radius * cos(end_radians), center[1] + radius * sin(end_radians))
    if point_in_polygon(start_point, polygon, include_boundary=boundary_is_collision):
        return True
    if point_in_polygon(end_point, polygon, include_boundary=boundary_is_collision):
        return True
    for index in range(len(polygon)):
        a, b = polygon[index], polygon[(index + 1) % len(polygon)]
        for point in segment_circle_intersections(a, b, center, radius):
            angle = degrees(atan2(point[1] - center[1], point[0] - center[0])) % 360.0
            if _angle_on_arc(angle, start_deg, end_deg, clockwise):
                return True
    return False


def distance_arc_to_segment(
    center: Point,
    radius: float,
    start_deg: float,
    end_deg: float,
    clockwise: bool,
    a: Point,
    b: Point,
) -> float:
    """Exact minimum distance between a circular arc and a segment."""
    from math import cos, radians, sin

    for point in segment_circle_intersections(a, b, center, radius):
        angle = degrees(atan2(point[1] - center[1], point[0] - center[0])) % 360.0
        if _angle_on_arc(angle, start_deg, end_deg, clockwise):
            return 0.0
    candidates: list[float] = []
    for angle in (start_deg, end_deg):
        value = radians(angle)
        arc_point = (center[0] + radius * cos(value), center[1] + radius * sin(value))
        candidates.append(distance_point_to_segment(arc_point, a, b))
    for point in (a, b):
        radial = distance(center, point)
        if radial > EPS:
            angle = degrees(atan2(point[1] - center[1], point[0] - center[0])) % 360.0
            if _angle_on_arc(angle, start_deg, end_deg, clockwise):
                candidates.append(abs(radial - radius))
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq > EPS:
        ratio = ((center[0] - a[0]) * dx + (center[1] - a[1]) * dy) / length_sq
        if -EPS <= ratio <= 1.0 + EPS:
            closest = (a[0] + max(0.0, min(1.0, ratio)) * dx, a[1] + max(0.0, min(1.0, ratio)) * dy)
            radial = distance(center, closest)
            if radial > EPS:
                angle = degrees(atan2(closest[1] - center[1], closest[0] - center[0])) % 360.0
                if _angle_on_arc(angle, start_deg, end_deg, clockwise):
                    candidates.append(abs(radial - radius))
    return min(candidates)


def segment_inside_polygon_with_clearance(a: Point, b: Point, polygon: list[Point], clearance: float) -> bool:
    if not point_in_polygon(a, polygon, include_boundary=False) or not point_in_polygon(b, polygon, include_boundary=False):
        return False
    edges = [(polygon[index], polygon[(index + 1) % len(polygon)]) for index in range(len(polygon))]
    return all(distance_segment_to_segment(a, b, start, end) + EPS >= clearance for start, end in edges)


def arc_inside_polygon_with_clearance(
    center: Point,
    radius: float,
    start_deg: float,
    end_deg: float,
    clockwise: bool,
    polygon: list[Point],
    clearance: float,
) -> bool:
    from math import cos, radians, sin

    span = (start_deg - end_deg) % 360.0 if clockwise else (end_deg - start_deg) % 360.0
    middle = (start_deg - span / 2.0) % 360.0 if clockwise else (start_deg + span / 2.0) % 360.0
    for angle in (start_deg, middle, end_deg):
        value = radians(angle)
        point = (center[0] + radius * cos(value), center[1] + radius * sin(value))
        if not point_in_polygon(point, polygon, include_boundary=False):
            return False
    return all(
        distance_arc_to_segment(center, radius, start_deg, end_deg, clockwise, polygon[index], polygon[(index + 1) % len(polygon)]) + EPS >= clearance
        for index in range(len(polygon))
    )


def sector_intersects_polygon_exact(
    center: Point,
    radius: float,
    start_deg: float,
    end_deg: float,
    clockwise: bool,
    polygon: list[Point],
) -> bool:
    """Check the closed area swept by a radial boom during rotation."""
    from math import cos, radians, sin

    start_angle, end_angle = radians(start_deg), radians(end_deg)
    start_tip = (center[0] + radius * cos(start_angle), center[1] + radius * sin(start_angle))
    end_tip = (center[0] + radius * cos(end_angle), center[1] + radius * sin(end_angle))
    if segment_intersects_polygon_exact(center, start_tip, polygon):
        return True
    if segment_intersects_polygon_exact(center, end_tip, polygon):
        return True
    if arc_intersects_polygon_exact(center, radius, start_deg, end_deg, clockwise, polygon):
        return True
    for point in polygon:
        if distance(center, point) <= radius + EPS:
            angle = degrees(atan2(point[1] - center[1], point[0] - center[0])) % 360.0
            if _angle_on_arc(angle, start_deg, end_deg, clockwise):
                return True
    return False


def validate_polygon(polygon: list[Point], name: str) -> list[str]:
    issues: list[str] = []
    if len(polygon) < 3:
        return [f"{name}: требуется минимум три вершины"]
    if any(not (isfinite(x) and isfinite(y)) for x, y in polygon):
        issues.append(f"{name}: координаты должны быть конечными числами")
    if polygon_area(polygon) <= EPS:
        issues.append(f"{name}: площадь равна нулю")
    if polygon_self_intersects(polygon):
        issues.append(f"{name}: обнаружено самопересечение")
    return issues


def polygon_inside_polygon(inner: list[Point], outer: list[Point]) -> bool:
    """Проверить не только вершины, но и рёбра вложенного полигона."""
    for start,end in zip(inner,inner[1:]+inner[:1]):
        for index in range(21):
            ratio=index/20
            if not point_in_polygon((start[0]+(end[0]-start[0])*ratio,start[1]+(end[1]-start[1])*ratio),outer):
                return False
    return True


def offset_polygon(polygon: list[Point], offset: float, miter_limit: float = 6.0) -> list[Point]:
    """Построить наружный параллельный контур простого полигона.

    На острых/вогнутых вершинах применяется ограничение длины усов. Входной
    полигон должен предварительно пройти validate_polygon().
    """
    if offset < 0 or len(polygon) < 3:
        raise ValueError("Для смещения нужен простой полигон и неотрицательное расстояние")
    signed = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1])) / 2.0
    direction = 1.0 if signed > 0 else -1.0
    result: list[Point] = []
    for i, current in enumerate(polygon):
        previous, following = polygon[i - 1], polygon[(i + 1) % len(polygon)]
        e1=(current[0]-previous[0],current[1]-previous[1]); e2=(following[0]-current[0],following[1]-current[1])
        l1=max(hypot(*e1),EPS); l2=max(hypot(*e2),EPS)
        n1=(direction*e1[1]/l1,-direction*e1[0]/l1); n2=(direction*e2[1]/l2,-direction*e2[0]/l2)
        bx,by=n1[0]+n2[0],n1[1]+n2[1]; bl=hypot(bx,by)
        if bl<=EPS:
            result.append((current[0]+n1[0]*offset,current[1]+n1[1]*offset)); continue
        bx,by=bx/bl,by/bl; denominator=max(EPS,bx*n1[0]+by*n1[1]); length=min(offset/denominator,offset*miter_limit)
        result.append((current[0]+bx*length,current[1]+by*length))
    if polygon_self_intersects(result):
        # Безопасный консервативный резерв: расширяем габаритный прямоугольник.
        x0,y0,x1,y1=polygon_bounds(polygon)
        return [(x0-offset,y0-offset),(x1+offset,y0-offset),(x1+offset,y1+offset),(x0-offset,y1+offset)]
    return result


def circle_inside_polygon(center: Point, radius: float, polygon: list[Point]) -> bool:
    return point_in_polygon(center, polygon) and distance_to_polygon(center, polygon) + EPS >= radius


def candidate_grid(boundary: list[Point], step_m: float = 2.0, max_points: int = 250_000) -> list[Point]:
    if not isfinite(step_m) or step_m <= 0:
        raise ValueError("Шаг расчётной сетки должен быть положительным конечным числом")
    min_x, min_y, max_x, max_y = polygon_bounds(boundary)
    estimated = (int((max_x - min_x) / step_m) + 1) * (int((max_y - min_y) / step_m) + 1)
    if estimated > max_points:
        raise ValueError(f"Расчётная сетка слишком велика: около {estimated} точек при ограничении {max_points}. Увеличьте шаг или уменьшите границу площадки.")
    result: list[Point] = []
    y = min_y
    while y <= max_y + EPS:
        x = min_x
        while x <= max_x + EPS:
            p = (round(x, 6), round(y, 6))
            if point_in_polygon(p, boundary):
                result.append(p)
            x += step_m
        y += step_m
    return result
