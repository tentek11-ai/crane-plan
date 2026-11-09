"""Height-aware safety rules for user-defined restricted zones."""

from __future__ import annotations

from .geometry import EPS, distance_to_polygon, offset_polygon, point_in_polygon, validate_polygon
from .models import Point, RestrictedZone, RestrictedZoneKind


def validate_zone(zone: RestrictedZone) -> list[str]:
    issues = validate_polygon(zone.polygon, zone.name or "Опасная зона")
    if not zone.verified:
        issues.append(f"{zone.name or 'Опасная зона'}: подтвердите тип, высоту и границы после миграции старого проекта")
    if zone.height_m < 0:
        issues.append(f"{zone.name}: высота не может быть отрицательной")
    if zone.horizontal_clearance_m < 0:
        issues.append(f"{zone.name}: горизонтальный запас не может быть отрицательным")
    if not issues:
        try:
            buffered = buffered_zone_polygon(zone)
        except ValueError as error:
            issues.append(f"{zone.name}: не удалось построить защитный контур: {error}")
        else:
            issues.extend(validate_polygon(buffered, f"{zone.name}, защитный контур"))
    return issues


def buffered_zone_polygon(zone: RestrictedZone) -> list[Point]:
    if zone.horizontal_clearance_m <= EPS:
        return list(zone.polygon)
    buffered = offset_polygon(zone.polygon, zone.horizontal_clearance_m)
    issues = validate_polygon(buffered, "Защитный контур")
    if issues:
        raise ValueError("; ".join(issues))
    return buffered


def tower_is_allowed(
    zone: RestrictedZone,
    tower_center: Point,
    tower_protection_radius_m: float,
) -> bool:
    if tower_protection_radius_m < 0:
        raise ValueError("Защитный радиус башни не может быть отрицательным")
    polygon = buffered_zone_polygon(zone)
    if point_in_polygon(tower_center, polygon, include_boundary=True):
        return False
    return distance_to_polygon(tower_center, polygon) > tower_protection_radius_m + EPS


def _height_allows(zone: RestrictedZone, bottom_m: float, clearance_m: float) -> bool:
    if clearance_m < 0:
        raise ValueError("Вертикальный запас не может быть отрицательным")
    return bottom_m + EPS >= zone.height_m + clearance_m


def load_may_overfly(zone: RestrictedZone, load_bottom_m: float, clearance_m: float) -> bool:
    if zone.kind in {RestrictedZoneKind.LOAD_PROHIBITED, RestrictedZoneKind.FULL_EXCLUSION}:
        return False
    return _height_allows(zone, load_bottom_m, clearance_m)


def jib_may_overfly(zone: RestrictedZone, jib_bottom_m: float, clearance_m: float) -> bool:
    if zone.kind is RestrictedZoneKind.FULL_EXCLUSION:
        return False
    return _height_allows(zone, jib_bottom_m, clearance_m)
