"""Public orchestration API for the CranePlan 2.1 calculation core."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from .catalog import CraneConfigurationV3
from .constraints import PlacementEvaluation, evaluate_placement
from .domain import Point2D, ProjectSolutionV3, ProjectV3
from .protocol import CalculationProtocolV3, build_protocol
from .verification import VerificationReport, VerificationStatus, verify_solution


ENGINE_VERSION = "2.1.0"


@dataclass(frozen=True)
class EngineRequestV21:
    project: ProjectV3
    catalog: tuple[CraneConfigurationV3, ...]
    candidate_coordinates: tuple[Point2D, ...]
    proposed_solution: ProjectSolutionV3 | None = None
    run_id: str = "RUN-V21"
    created_at: str = "1970-01-01T00:00:00Z"


@dataclass(frozen=True)
class EngineResultV21:
    placement_evaluations: tuple[PlacementEvaluation, ...]
    accepted_solution: ProjectSolutionV3 | None
    verification: VerificationReport | None
    protocol: CalculationProtocolV3 | None


def run_engine_v21(request: EngineRequestV21) -> EngineResultV21:
    """Evaluate explicit candidates and independently verify an optional solution.

    Version 2.1 intentionally performs no coordinate search and no ranking.
    """

    started = perf_counter()
    stages = tuple(sorted(request.project.stages, key=lambda item: item.id))
    configurations = tuple(sorted(request.catalog, key=lambda item: (item.priority, item.id)))
    coordinates = tuple(sorted(set(request.candidate_coordinates)))
    evaluations = tuple(
        evaluate_placement(request.project, stage.id, point, config)
        for stage in stages
        for config in configurations
        for point in coordinates
    )

    if request.proposed_solution is None:
        return EngineResultV21(evaluations, None, None, None)

    catalog_by_id = {config.id: config for config in configurations}
    verification = verify_solution(request.project, catalog_by_id, request.proposed_solution)
    accepted = (
        request.proposed_solution
        if verification.status in {VerificationStatus.VALID, VerificationStatus.VALID_WITH_CONDITIONS}
        else None
    )
    duration_seconds = perf_counter() - started
    protocol = build_protocol(
        request.project,
        configurations,
        evaluations,
        request.proposed_solution,
        verification,
        run_id=request.run_id,
        created_at=request.created_at,
        duration_seconds=duration_seconds,
        algorithm_version=ENGINE_VERSION,
    )
    return EngineResultV21(evaluations, accepted, verification, protocol)
