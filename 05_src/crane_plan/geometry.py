"""Базовая 2D-геометрия для расчёта площадки."""

from __future__ import annotations

from math import hypot, isfinite

from .models import Point


EPS = 1e-9


def distance(a: Point, b: Point) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


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
