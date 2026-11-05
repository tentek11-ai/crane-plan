"""Application-facing verification policy for legacy GUI scenarios."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Sequence

from crane_plan.models import ProjectInput, ScenarioResult

from .catalog import CraneConfigurationV3
from .gui_adapter import adapt_scenario_v21
from .protocol import CalculationProtocolV3
from .service import EngineRequestV21, EngineResultV21, run_engine_v21
from .verification import VerificationCheck, VerificationStatus


class IntegrationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    VERIFIED_WITH_CONDITIONS = "VERIFIED_WITH_CONDITIONS"
    EXPERT_REVIEW_REQUIRED = "EXPERT_REVIEW_REQUIRED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ScenarioVerificationV21:
    scenario_index: int
    status: IntegrationStatus
    release_allowed: bool
    messages: tuple[str, ...]
    engine_result: EngineResultV21 | None
    protocol: CalculationProtocolV3 | None

    def to_dict(self) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        verification = self.engine_result.verification if self.engine_result else None
        if verification:
            checks = [
                {
                    "code": check.code,
                    "passed": check.passed,
                    "measured_value": check.measured_value,
                    "limit": check.limit,
                    "units": check.units,
                    "operation_id": check.operation_id,
                    "crane_id": check.crane_id,
                    "conditional": check.conditional,
                    "review_required": check.review_required,
                }
                for check in verification.checks
            ]
        return {
            "scenario_index": self.scenario_index,
            "status": self.status.value,
            "release_allowed": self.release_allowed,
            "messages": list(self.messages),
            "run_id": self.protocol.run_id if self.protocol else None,
            "input_sha256": self.protocol.input_sha256 if self.protocol else None,
            "result_sha256": self.protocol.result_sha256 if self.protocol else None,
            "checks": checks,
        }


_CHECK_TRANSLATIONS = {
    "SOURCE_EVIDENCE": "Исходные значения содержат неподтверждённые допущения.",
    "CONFIGURATION_SUPPORTED": "Конфигурация крана отсутствует в подтверждённом паспортном ряду.",
    "BASE_INSIDE_SITE": "Основание крана находится вне границы строительной площадки.",
    "BASE_OUTSIDE_BUILDING": "Основание крана пересекает контур здания.",
    "RESTRICTED_ZONE_CLEAR": "Основание крана попадает в запретную зону.",
    "BASE_CLEARANCE": "Не соблюдено допустимое расстояние от крана до здания.",
    "REACH": "Требуемый вылет превышает длину стрелы.",
    "ROUTE_CLEAR": "Маршрут перемещения груза пересекает запретную зону.",
    "DANGER_ZONE_INSIDE_SITE": "Опасная зона выходит за границу строительной площадки.",
    "DANGER_ZONE_PROTECTED": "Выход опасной зоны компенсируется защитным ограждением монтажного горизонта.",
    "DANGER_ZONE_CONFLICT": "Опасная зона выходит за границу площадки без допустимой защитной меры.",
}


def _format_number(value: object) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _check_message(check: VerificationCheck) -> str:
    measured = _format_number(check.measured_value)
    limit = _format_number(check.limit)
    if check.code == "CAPACITY_INSUFFICIENT":
        return f"{check.code}: требуется {measured} кг, доступно {limit} кг."
    if check.code == "HEIGHT":
        return f"{check.code}: требуемая высота крюка {measured} м, доступно {limit} м."
    explanation = _CHECK_TRANSLATIONS.get(check.code, "Проверка требует внимания.")
    suffix = f" Измерено: {measured}; предел: {limit} {check.units}." if check.measured_value is not None else ""
    return f"{check.code}: {explanation}{suffix}"


def _verification_messages(engine_result: EngineResultV21) -> tuple[str, ...]:
    if engine_result.verification is None:
        return ("ENGINE_RESULT_INCOMPLETE: ядро не сформировало независимый отчёт проверки.",)
    return tuple(
        _check_message(check)
        for check in engine_result.verification.checks
        if not check.passed or check.conditional or check.review_required
    )


def verify_scenario_v21(
    project: ProjectInput,
    scenario: ScenarioResult,
    catalog: tuple[CraneConfigurationV3, ...],
    *,
    scenario_index: int,
    run_id: str,
    created_at: str,
) -> ScenarioVerificationV21:
    adapted = adapt_scenario_v21(project, scenario, catalog, scenario_index=scenario_index)
    adapter_messages = tuple(f"{issue.code}: {issue.message}" for issue in adapted.issues)
    if adapted.project is None or adapted.solution is None or not adapted.catalog:
        return ScenarioVerificationV21(
            scenario_index,
            IntegrationStatus.EXPERT_REVIEW_REQUIRED,
            False,
            adapter_messages or ("ADAPTER_INCOMPLETE: вариант нельзя однозначно преобразовать в схему V3.",),
            None,
            None,
        )

    candidate_coordinates = tuple(
        (placement.x_m, placement.y_m)
        for stage in adapted.solution.stages
        for placement in stage.placements
    )
    engine_result = run_engine_v21(
        EngineRequestV21(
            project=adapted.project,
            catalog=adapted.catalog,
            candidate_coordinates=candidate_coordinates,
            proposed_solution=adapted.solution,
            run_id=run_id,
            created_at=created_at,
        )
    )
    messages = adapter_messages + adapted.conditional_messages + _verification_messages(engine_result)
    verification = engine_result.verification
    if verification is None:
        status = IntegrationStatus.EXPERT_REVIEW_REQUIRED
    elif verification.status == VerificationStatus.INVALID:
        status = IntegrationStatus.REJECTED
    elif adapted.issues or verification.status == VerificationStatus.EXPERT_REVIEW_REQUIRED:
        status = IntegrationStatus.EXPERT_REVIEW_REQUIRED
    elif adapted.conditional_messages or verification.status == VerificationStatus.VALID_WITH_CONDITIONS:
        status = IntegrationStatus.VERIFIED_WITH_CONDITIONS
    else:
        status = IntegrationStatus.VERIFIED
    release_allowed = status in {IntegrationStatus.VERIFIED, IntegrationStatus.VERIFIED_WITH_CONDITIONS}
    return ScenarioVerificationV21(
        scenario_index,
        status,
        release_allowed,
        messages,
        engine_result,
        engine_result.protocol,
    )


def verify_scenarios_v21(
    project: ProjectInput,
    scenarios: list[ScenarioResult],
    catalog: tuple[CraneConfigurationV3, ...],
    *,
    run_id: str,
    created_at: str,
) -> tuple[ScenarioVerificationV21, ...]:
    results: list[ScenarioVerificationV21] = []
    for scenario_index, scenario in enumerate(scenarios):
        try:
            results.append(
                verify_scenario_v21(
                    project,
                    scenario,
                    catalog,
                    scenario_index=scenario_index,
                    run_id=f"{run_id}-S{scenario_index + 1}",
                    created_at=created_at,
                )
            )
        except Exception as exc:
            results.append(
                ScenarioVerificationV21(
                    scenario_index,
                    IntegrationStatus.EXPERT_REVIEW_REQUIRED,
                    False,
                    (f"ENGINE_EXCEPTION: независимая проверка не выполнена: {exc}",),
                    None,
                    None,
                )
            )
    return tuple(results)


def default_release_index(results: Sequence[ScenarioVerificationV21]) -> int | None:
    for index, result in enumerate(results):
        if result.release_allowed:
            return index
    return 0 if results else None


def release_blockers(
    results: Sequence[ScenarioVerificationV21],
    selected_index: int | None,
) -> tuple[str, ...]:
    if selected_index is None:
        return ("Выберите рассчитанный вариант.",)
    if selected_index < 0 or selected_index >= len(results):
        return ("Выбранный вариант устарел; выполните расчёт повторно.",)
    result = results[selected_index]
    if result.release_allowed:
        return ()
    heading = {
        IntegrationStatus.EXPERT_REVIEW_REQUIRED: "Вариант требует экспертной проверки и не может быть выпущен.",
        IntegrationStatus.REJECTED: "Вариант отклонён независимой проверкой и не может быть выпущен.",
    }.get(result.status, "Вариант не допускается к выпуску.")
    return (heading,) + result.messages


def scenario_for_report(
    scenario: ScenarioResult,
    verification: ScenarioVerificationV21,
) -> ScenarioResult:
    return replace(scenario, warnings=list(scenario.warnings) + list(verification.messages))
