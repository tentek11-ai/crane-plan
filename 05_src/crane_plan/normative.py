"""Проверяемые численные правила ФНП № 461.

Модуль намеренно не подставляет значения при неизвестных исходных данных.
Геометрическое построение полигонов будет добавлено отдельным слоем.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


HEIGHT_POINTS_M = (10.0, 20.0, 70.0, 120.0, 200.0, 300.0, 450.0)
LOAD_FALL_M = (4.0, 7.0, 10.0, 15.0, 20.0, 25.0, 30.0)
BUILDING_OBJECT_FALL_M = (3.5, 5.0, 7.0, 10.0, 15.0, 20.0, 25.0)
JOINT_WORK_HORIZONTAL_M = 5.0
JOINT_PARKING_HORIZONTAL_M = 2.0
JOINT_VERTICAL_M = 1.0


class NormativeInputError(ValueError):
    """Расчёт заблокирован из-за отсутствующего или недопустимого ввода."""


class FallScenario(StrEnum):
    MOVED_LOAD = "moved_load"
    OBJECT_FROM_BUILDING = "object_from_building"


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    status: str
    message: str


def _positive(name: str, value: float) -> float:
    if value is None or value <= 0:
        raise NormativeInputError(f"{name} должно быть больше нуля")
    return float(value)


def _non_negative(name: str, value: float) -> float:
    if value is None or value < 0:
        raise NormativeInputError(f"{name} не может быть отрицательным")
    return float(value)


def fall_distance(height_m: float, scenario: FallScenario | str) -> float:
    """Вернуть минимальное расстояние отлёта по приложению № 2.

    Для высоты до 10 м используется первая строка таблицы. Между верхними
    границами строк применяется линейная интерполяция. Высота свыше 450 м
    не покрыта таблицей и поэтому блокирует расчёт.
    """

    height = _positive("Высота возможного падения", height_m)
    try:
        scenario = FallScenario(scenario)
    except ValueError as exc:
        raise NormativeInputError("Неизвестный сценарий падения") from exc

    values = LOAD_FALL_M if scenario is FallScenario.MOVED_LOAD else BUILDING_OBJECT_FALL_M
    if height <= HEIGHT_POINTS_M[0]:
        return values[0]
    if height > HEIGHT_POINTS_M[-1]:
        raise NormativeInputError("Таблица ФНП не покрывает высоту более 450 м")

    for index in range(1, len(HEIGHT_POINTS_M)):
        upper_h = HEIGHT_POINTS_M[index]
        if height <= upper_h:
            lower_h = HEIGHT_POINTS_M[index - 1]
            ratio = (height - lower_h) / (upper_h - lower_h)
            return values[index - 1] + ratio * (values[index] - values[index - 1])

    raise AssertionError("Недостижимая ветвь интерполяции")


def danger_zone_offset_from_outer_edge(
    height_m: float,
    largest_load_dimension_m: float,
    scenario: FallScenario | str = FallScenario.MOVED_LOAD,
) -> float:
    """Смещение границы опасной зоны от наружной крайней точки груза/здания."""

    largest_dimension = _positive("Наибольший габарит груза", largest_load_dimension_m)
    return largest_dimension + fall_distance(height_m, scenario)


def required_hook_height(
    upper_level_m: float,
    load_height_m: float,
    rigging_height_m: float,
    people_may_be_below: bool,
) -> float:
    """Потребная отметка крюка по п. 156(к) ФНП № 461."""

    if upper_level_m is None:
        raise NormativeInputError("Не задана верхняя отметка")
    load_height = _positive("Высота груза", load_height_m)
    rigging_height = _positive("Высота строповки", rigging_height_m)
    clearance = 2.3 if people_may_be_below else 0.5
    return float(upper_level_m) + clearance + load_height + rigging_height


def validate_joint_crane_clearances(
    horizontal_m: float,
    vertical_jib_level_difference_m: float,
) -> CheckResult:
    """Проверить минимумы совместной работы по разделу ППР ФНП № 461."""

    horizontal = _non_negative("Горизонтальное расстояние", horizontal_m)
    vertical = _non_negative("Разность уровней стрел", vertical_jib_level_difference_m)
    if horizontal < JOINT_WORK_HORIZONTAL_M:
        return CheckResult(False, "BLOCKED", "Горизонтальное расстояние меньше 5 м")
    if vertical < JOINT_VERTICAL_M:
        return CheckResult(False, "BLOCKED", "Разность уровней стрел меньше 1 м")
    return CheckResult(True, "PASS_WITH_CONDITIONS", "Минимальные расстояния соблюдены; нужны решения ППР и ограничители")


def validate_joint_crane_parking_clearances(horizontal_m: float, vertical_m: float) -> CheckResult:
    """Проверить взаимные габариты башенных кранов на стоянке."""
    horizontal=_non_negative("Горизонтальное расстояние на стоянке",horizontal_m)
    vertical=_non_negative("Вертикальное расстояние на стоянке",vertical_m)
    if horizontal<JOINT_PARKING_HORIZONTAL_M:
        return CheckResult(False,"BLOCKED","На стоянке горизонтальное расстояние между кранами или их частями меньше 2 м")
    if vertical<JOINT_VERTICAL_M:
        return CheckResult(False,"BLOCKED","На стоянке вертикальное расстояние между кранами или их частями меньше 1 м")
    return CheckResult(True,"PASS_WITH_CONDITIONS","Стояночные габариты соблюдены; свободный поворот и фактические конфигурации подтверждаются ППРк")
