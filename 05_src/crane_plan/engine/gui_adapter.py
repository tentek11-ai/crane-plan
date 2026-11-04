"""Pure conversion from the legacy desktop models to engine schema V3."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil
import re

from crane_plan.geometry import polygon_centroid
from crane_plan.models import ProjectInput, ScenarioResult

from .catalog import EPS, CraneConfigurationV3
from .domain import (
    ConstructionStage,
    CranePlacementV3,
    LiftEndpoint,
    LiftingOperation,
    LoadSpec,
    OperationAssignment,
    ProjectSolutionV3,
    ProjectV3,
    SiteGeometry,
    SourceKind,
    SourceLocator,
    StageSolutionV3,
)


BASE_LEGACY_CONFIGURATION_ID = "LIEBHERR-130-ECB-6-60"
BASE_V3_CONFIGURATION_ID = "LIEBHERR-130-ECB-6-60-V3"


@dataclass(frozen=True)
class AdapterIssue:
    code: str
    message: str


@dataclass(frozen=True)
class AdaptedScenarioV21:
    project: ProjectV3 | None
    catalog: tuple[CraneConfigurationV3, ...]
    solution: ProjectSolutionV3 | None
    issues: tuple[AdapterIssue, ...]
    conditional_messages: tuple[str, ...] = ()


def _project_id(project: ProjectInput) -> str:
    slug = re.sub(r"[^0-9A-Za-zА-Яа-я]+", "-", f"{project.city}-{project.name}").strip("-")
    return f"GUI-{project.year}-{slug or 'PROJECT'}"


def _project_source(project: ProjectInput, locator: str, note: str = "") -> SourceLocator:
    return SourceLocator(SourceKind.PROJECT, project.name or "PROJECT", locator, note=note)


def _logistics_source(project: ProjectInput) -> tuple[tuple[float, float] | None, AdapterIssue | None]:
    if len(project.site.storage_zones) > 1:
        return None, AdapterIssue(
            "LOGISTICS_SOURCE_AMBIGUOUS",
            "Задано несколько зон складирования; источник перемещения груза необходимо назначить явно.",
        )
    if len(project.site.storage_zones) == 1:
        return polygon_centroid(project.site.storage_zones[0]), None
    if project.site.unloading_zone:
        return polygon_centroid(project.site.unloading_zone), None
    return None, AdapterIssue(
        "LOGISTICS_SOURCE_REQUIRED",
        "Нанесите одну зону складирования либо зону разгрузки.",
    )


def _configuration_for_placement(
    crane_id: str,
    jib_length_m: float,
    catalog: tuple[CraneConfigurationV3, ...],
) -> tuple[CraneConfigurationV3 | None, AdapterIssue | None, str | None]:
    if crane_id != BASE_LEGACY_CONFIGURATION_ID:
        return None, AdapterIssue(
            "CONFIGURATION_NOT_IN_V3_CATALOG",
            f"Конфигурация {crane_id} пока не подтверждена в каталоге V3.",
        ), None
    base = next((item for item in catalog if item.id == BASE_V3_CONFIGURATION_ID), None)
    if base is None:
        return None, AdapterIssue(
            "CONFIGURATION_NOT_IN_V3_CATALOG",
            f"В каталоге V3 отсутствует {BASE_V3_CONFIGURATION_ID}.",
        ), None
    actual_jib = jib_length_m or base.jib_length_m
    if not any(abs(actual_jib - allowed) <= EPS for allowed in base.allowed_jib_lengths_m):
        return None, AdapterIssue(
            "JIB_LENGTH_NOT_SUPPORTED",
            f"Длина стрелы {actual_jib:g} м отсутствует в разрешённом ряду.",
        ), None
    if abs(actual_jib - base.jib_length_m) <= EPS:
        return base, None, None
    suffix = f"{actual_jib:g}"
    derived = replace(base, id=f"{base.id}@JIB-{suffix}M", jib_length_m=actual_jib)
    message = (
        f"Стрела {actual_jib:g} м проверена по консервативной грузовой характеристике "
        f"паспортной стрелы {base.jib_length_m:g} м."
    )
    return derived, None, message


def adapt_scenario_v21(
    project: ProjectInput,
    scenario: ScenarioResult,
    catalog: tuple[CraneConfigurationV3, ...],
    *,
    scenario_index: int,
) -> AdaptedScenarioV21:
    """Convert one legacy scenario without importing or touching Tkinter."""

    issues: list[AdapterIssue] = []
    source_point, logistics_issue = _logistics_source(project)
    if logistics_issue:
        issues.append(logistics_issue)
    if len(scenario.placements) != 1:
        issues.append(
            AdapterIssue(
                "MULTI_CRANE_NOT_SUPPORTED",
                "Ядро 2.1 первого этапа проверяет только однокрановые варианты.",
            )
        )
    if source_point is None:
        return AdaptedScenarioV21(None, (), None, tuple(issues))

    project_source = _project_source(project, "Исходные данные проекта")
    active_indices = [index for index, load in enumerate(project.loads) if load.active]
    assigned_indices = {point.load_index for point in project.work_points}
    unassigned_indices = [index for index in active_indices if index not in assigned_indices]
    operations: list[LiftingOperation] = []
    for work_index, point in enumerate(project.work_points):
        load_indices: list[int] = []
        if point.load_index in active_indices:
            load_indices.append(point.load_index)
        load_indices.extend(index for index in unassigned_indices if index not in load_indices)
        for load_index in load_indices:
            load = project.loads[load_index]
            if project.loads_verified:
                load_sources = (
                    _project_source(
                        project,
                        f"Таблица грузов: {load.name}",
                        "Масса, оснастка и принятая высота строповки 1,5 м подтверждены пользователем.",
                    ),
                )
            else:
                load_sources = (
                    SourceLocator(
                        SourceKind.ASSUMPTION,
                        "",
                        "",
                        note=f"Типовые данные груза «{load.name}» и высота строповки 1,5 м требуют подтверждения.",
                    ),
                )
            load_spec = LoadSpec(
                id=f"LOAD-L{load_index + 1}",
                name=load.name,
                load_kg=load.load_kg,
                rigging_kg=load.rigging_kg,
                length_m=load.length_m,
                width_m=load.width_m,
                height_m=load.height_m,
                rigging_height_m=1.5,
                sources=load_sources,
            )
            operations.append(
                LiftingOperation(
                    id=f"OP-W{work_index + 1}-L{load_index + 1}",
                    name=f"{load.name} → {point.name}",
                    stage_id="MAIN_STAGE",
                    source=LiftEndpoint(source_point[0], source_point[1], 0.0),
                    destination=LiftEndpoint(point.x, point.y, point.level_m),
                    load=load_spec,
                    count=load.lifts,
                    sources=(_project_source(project, f"Точка подачи: {point.name}"),),
                )
            )

    mounting_level = max((point.level_m for point in project.work_points), default=0.0)
    duration = max(1, int(ceil(scenario.calendar_days or 1)))
    stage = ConstructionStage(
        "MAIN_STAGE",
        "Основной этап",
        1,
        duration,
        mounting_level,
        (_project_source(project, "Монтажный горизонт"),),
    )
    project_v3 = ProjectV3(
        project_id=_project_id(project),
        name=project.name,
        city=project.city,
        stages=(stage,),
        site=SiteGeometry(
            boundary=tuple(project.site.boundary),
            building=tuple(project.site.building),
            restricted_zones=tuple(tuple(zone) for zone in project.site.restricted_zones),
            min_crane_to_building_m=project.site.min_crane_to_building_m,
            max_crane_to_building_m=project.site.max_crane_to_building_m,
            sources=(_project_source(project, "План: границы площадки, здания и запретных зон"),),
        ),
        operations=tuple(operations),
        normative_profile_id="RF-2026",
        catalog_version="3.0.0-2026-10-20",
    )

    if len(scenario.placements) != 1:
        return AdaptedScenarioV21(project_v3, (), None, tuple(issues))
    legacy_placement = scenario.placements[0]
    configuration, config_issue, conditional_message = _configuration_for_placement(
        legacy_placement.crane_id,
        legacy_placement.jib_length_m,
        catalog,
    )
    if config_issue:
        issues.append(config_issue)
        return AdaptedScenarioV21(project_v3, (), None, tuple(issues))
    if legacy_placement.tie_in_levels_m or (
        legacy_placement.accepted_crane_height_m
        and legacy_placement.accepted_crane_height_m > configuration.max_free_standing_hook_height_m + EPS
    ):
        issues.append(
            AdapterIssue(
                "TIE_INS_NOT_VERIFIED",
                "Пристёжки и высота выше свободностоящей конфигурации требуют экспертной проверки.",
            )
        )
    placement_id = f"SCENARIO-{scenario_index + 1}-CRANE-1"
    protective_measures = ("PROTECTIVE_SCREEN",) if project.protective_screen_possible else ()
    placement_v3 = CranePlacementV3(
        placement_id,
        "MAIN_STAGE",
        configuration.id,
        legacy_placement.x,
        legacy_placement.y,
        protective_measures,
    )
    assignments = tuple(OperationAssignment(operation.id, placement_id) for operation in operations)
    solution = ProjectSolutionV3(
        project_v3.project_id,
        (StageSolutionV3("MAIN_STAGE", (placement_v3,), assignments),),
    )
    conditions = (conditional_message,) if conditional_message else ()
    return AdaptedScenarioV21(project_v3, (configuration,), solution, tuple(issues), conditions)
