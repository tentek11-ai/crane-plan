"""Canonical, reproducible protocol for version 3 calculations."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping

from .catalog import CraneConfigurationV3
from .constraints import PlacementEvaluation
from .domain import ProjectSolutionV3, ProjectV3, SourceLocator
from .verification import VerificationReport


def _primitive(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    if isinstance(value, set):
        items = [_primitive(item) for item in value]
        return sorted(items, key=lambda item: canonical_json(item))
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NaN and infinity are not valid protocol values")
    if isinstance(value, Path):
        return str(value)
    return value


def canonical_json(value: object) -> str:
    return json.dumps(
        _primitive(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CalculationProtocolV3:
    run_id: str
    created_at: str
    duration_seconds: float
    algorithm_version: str
    normative_profile_id: str
    catalog_version: str
    input_sha256: str
    result_sha256: str
    project: ProjectV3
    catalog: tuple[CraneConfigurationV3, ...]
    placement_evaluations: tuple[PlacementEvaluation, ...]
    solution: ProjectSolutionV3 | None
    verification: VerificationReport | None
    source_locators: tuple[SourceLocator, ...]
    rejected_reason_counts: tuple[tuple[str, int], ...]
    schema_version: int = 3


def _all_sources(
    project: ProjectV3,
    catalog: tuple[CraneConfigurationV3, ...],
) -> tuple[SourceLocator, ...]:
    sources: list[SourceLocator] = list(project.site.sources)
    for stage in project.stages:
        sources.extend(stage.sources)
    for operation in project.operations:
        sources.extend(operation.sources)
        sources.extend(operation.load.sources)
    sources.extend(config.source for config in catalog)
    unique = {canonical_json(source): source for source in sources}
    return tuple(unique[key] for key in sorted(unique))


def build_protocol(
    project: ProjectV3,
    configurations: tuple[CraneConfigurationV3, ...] | list[CraneConfigurationV3],
    placement_evaluations: tuple[PlacementEvaluation, ...] | list[PlacementEvaluation],
    solution: ProjectSolutionV3 | None,
    verification: VerificationReport | None,
    *,
    run_id: str,
    created_at: str,
    duration_seconds: float,
    algorithm_version: str,
) -> CalculationProtocolV3:
    if not algorithm_version.strip():
        raise ValueError("algorithm_version is required")
    if not project.normative_profile_id.strip():
        raise ValueError("normative_profile_id is required")
    if not project.catalog_version.strip():
        raise ValueError("catalog_version is required")
    if not run_id.strip() or not created_at.strip():
        raise ValueError("run_id and created_at are required")

    catalog = tuple(sorted(configurations, key=lambda item: item.id))
    evaluations = tuple(
        sorted(
            placement_evaluations,
            key=lambda item: (item.stage_id, item.configuration_id, item.crane_point),
        )
    )
    candidate_identity = tuple(
        (evaluation.stage_id, evaluation.configuration_id, evaluation.crane_point)
        for evaluation in evaluations
    )
    input_payload = {"project": project, "catalog": catalog, "candidates": candidate_identity}
    result_payload = {
        "placement_evaluations": evaluations,
        "solution": solution,
        "verification": verification,
    }
    reason_counts: Counter[str] = Counter()
    for evaluation in evaluations:
        reason_counts.update(code.value for code in evaluation.reason_codes)

    return CalculationProtocolV3(
        run_id=run_id,
        created_at=created_at,
        duration_seconds=duration_seconds,
        algorithm_version=algorithm_version,
        normative_profile_id=project.normative_profile_id,
        catalog_version=project.catalog_version,
        input_sha256=sha256_hex(input_payload),
        result_sha256=sha256_hex(result_payload),
        project=project,
        catalog=catalog,
        placement_evaluations=evaluations,
        solution=solution,
        verification=verification,
        source_locators=_all_sources(project, catalog),
        rejected_reason_counts=tuple(sorted(reason_counts.items())),
    )


def save_protocol(path: str | Path, protocol: CalculationProtocolV3) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(protocol) + "\n", encoding="utf-8")
    return target
