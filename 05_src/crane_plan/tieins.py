"""Предварительная компоновка пристёжек и пятиметровых секций башни."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, cos, radians

from .models import Point


SECTION_HEIGHT_M = 5.0
MAX_SECTIONS_PER_STAGE = 5
TIE_OFFSET_M = 6.0
STAGE_RISE_M = SECTION_HEIGHT_M * MAX_SECTIONS_PER_STAGE


@dataclass(frozen=True)
class TieInStage:
    number: int
    level_m: float
    sections_this_stage: int
    total_sections: int
    accepted_height_m: float
    nearest_floor: int
    contour_available: bool = True


@dataclass(frozen=True)
class TieInPlan:
    required_height_m: float
    free_standing_height_m: float
    accepted_height_m: float
    stages: list[TieInStage] = field(default_factory=list)
    required_tie_length_m: float = 0.0
    geometry_ok: bool = True
    reasons: list[str] = field(default_factory=list)

    @property
    def total_sections(self) -> int:
        return sum(stage.sections_this_stage for stage in self.stages)


def horizontal_intersections(polygon: list[Point], height_m: float) -> list[float]:
    """X intersections of a horizontal level with a closed section contour."""
    if len(polygon) < 3:
        return []
    result: list[float] = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if abs(a[1] - b[1]) < 1e-9:
            if abs(height_m - a[1]) < 1e-6:
                result.extend((a[0], b[0]))
            continue
        low, high = sorted((a[1], b[1]))
        if low - 1e-9 <= height_m < high - 1e-9:
            ratio = (height_m - a[1]) / (b[1] - a[1])
            result.append(a[0] + ratio * (b[0] - a[0]))
    return sorted(set(round(value, 8) for value in result))


def required_pair_tie_length(horizontal_distance_m: float, angle_deg: float) -> float:
    if horizontal_distance_m < 0:
        raise ValueError("Расстояние до здания не может быть отрицательным")
    if not 0 < angle_deg < 180:
        raise ValueError("Угол между тягами должен быть больше 0 и меньше 180 градусов")
    projection = cos(radians(angle_deg / 2.0))
    if projection <= 0:
        raise ValueError("Для заданного угла невозможно определить длину тяг")
    return horizontal_distance_m / projection


def calculate_tie_in_plan(
    required_height_m: float,
    free_standing_height_m: float,
    building_height_m: float,
    floors: int,
    tie_length_m: float = 12.0,
    tie_angle_deg: float = 60.0,
    horizontal_distance_m: float = 0.0,
    section_contour: list[Point] | None = None,
    tie_ins_possible: bool = True,
) -> TieInPlan:
    """Select the minimum number of 5 m mast sections and tie-in stages."""
    if required_height_m <= 0 or free_standing_height_m <= 0 or building_height_m <= 0:
        raise ValueError("Высоты крана и здания должны быть положительными")
    if floors <= 0:
        raise ValueError("Количество этажей должно быть положительным целым числом")
    if tie_length_m <= 0:
        raise ValueError("Длина тяги должна быть положительной")
    required_length = required_pair_tie_length(horizontal_distance_m, tie_angle_deg)
    if required_height_m <= free_standing_height_m + 1e-9:
        return TieInPlan(required_height_m, free_standing_height_m, free_standing_height_m, [], required_length, True, [])
    if not tie_ins_possible:
        return TieInPlan(required_height_m, free_standing_height_m, free_standing_height_m, [], required_length, False,
                         ["Требуемая высота превышает свободностоящую, но применение пристёжек запрещено пользователем"])

    extra_sections = ceil((required_height_m - free_standing_height_m - 1e-9) / SECTION_HEIGHT_M)
    stage_count = ceil(extra_sections / MAX_SECTIONS_PER_STAGE)
    floor_height = building_height_m / floors
    contour = section_contour or []
    stages: list[TieInStage] = []
    remaining = extra_sections
    reasons: list[str] = []
    for index in range(stage_count):
        sections = min(MAX_SECTIONS_PER_STAGE, remaining)
        total = min(extra_sections, index * MAX_SECTIONS_PER_STAGE + sections)
        level = free_standing_height_m - TIE_OFFSET_M + index * STAGE_RISE_M
        accepted = free_standing_height_m + total * SECTION_HEIGHT_M
        nearest_floor = max(1, min(floors, round(level / floor_height)))
        contour_available = bool(horizontal_intersections(contour, level)) if contour else level <= building_height_m + 1e-9
        if level <= 0:
            reasons.append(f"Пристёжка {index + 1}: расчётная отметка {level:.1f} м неположительна")
        if level > building_height_m + 1e-9 or not contour_available:
            reasons.append(f"Пристёжка {index + 1}: на отметке {level:.1f} м отсутствует доступный контур здания")
        stages.append(TieInStage(index + 1, level, sections, total, accepted, nearest_floor, contour_available))
        remaining -= sections

    if required_length > tie_length_m + 1e-9:
        reasons.append(f"Тяги длиной {tie_length_m:.1f} м не достигают здания; требуется не менее {required_length:.1f} м при угле {tie_angle_deg:.1f}°")
    accepted_height = free_standing_height_m + extra_sections * SECTION_HEIGHT_M
    return TieInPlan(required_height_m, free_standing_height_m, accepted_height, stages, required_length, not reasons, reasons)
