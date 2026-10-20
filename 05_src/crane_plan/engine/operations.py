"""Build explicit, repeatable lifting operations from project requests."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

from .domain import (
    InputIssue,
    LiftEndpoint,
    LiftingOperation,
    LoadSpec,
    ProjectV3,
    SourceKind,
    SourceLocator,
)


@dataclass(frozen=True)
class OperationRequest:
    request_id: str
    stage_id: str
    load_template_id: str
    source: LiftEndpoint
    destination: LiftEndpoint
    count: int
    source_locator: SourceLocator
    load_overrides: Mapping[str, float] | None = None


class OperationBuildError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def load_standard_loads(path: str | Path) -> dict[str, LoadSpec]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    note = str(payload.get("note", "Standard load library value"))
    source = SourceLocator(
        SourceKind.ASSUMPTION,
        "",
        "",
        note=f"{note}. Default rigging height: 1.5 m; confirm for the selected sling arrangement.",
    )
    library: dict[str, LoadSpec] = {}
    for row in payload.get("loads", ()):
        load = LoadSpec(
            id=str(row["id"]),
            name=str(row["name"]),
            load_kg=float(row["load_kg"]),
            rigging_kg=float(row["rigging_kg"]),
            length_m=float(row["length_m"]),
            width_m=float(row["width_m"]),
            height_m=float(row["height_m"]),
            rigging_height_m=float(row.get("rigging_height_m", 1.5)),
            sources=(source,),
        )
        library[load.id] = load
    return library


def _operation_id(request: OperationRequest) -> str:
    values = {
        "request_id": request.request_id,
        "stage_id": request.stage_id,
        "load_template_id": request.load_template_id,
        "source": [request.source.x_m, request.source.y_m, request.source.z_m],
        "destination": [request.destination.x_m, request.destination.y_m, request.destination.z_m],
        "count": request.count,
        "load_overrides": sorted((request.load_overrides or {}).items()),
    }
    digest = hashlib.sha256(
        json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"OP-{digest.upper()}"


def _overridden_load(template: LoadSpec, request: OperationRequest) -> LoadSpec:
    overrides = dict(request.load_overrides or {})
    if not overrides:
        return template
    allowed = {
        "load_kg",
        "rigging_kg",
        "length_m",
        "width_m",
        "height_m",
        "rigging_height_m",
    }
    unknown = sorted(set(overrides) - allowed)
    if unknown:
        raise OperationBuildError("UNKNOWN_LOAD_FIELD", ", ".join(unknown))
    if request.source_locator.kind != SourceKind.PROJECT:
        raise OperationBuildError("PROJECT_SOURCE_REQUIRED", "Load overrides require a PROJECT source locator.")
    digest = hashlib.sha256(
        json.dumps(sorted(overrides.items()), separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return replace(
        template,
        id=f"{template.id}:override:{digest}",
        sources=template.sources + (request.source_locator,),
        **overrides,
    )


def build_operations(
    requests: Iterable[OperationRequest],
    load_library: Mapping[str, LoadSpec],
) -> tuple[LiftingOperation, ...]:
    operations: list[LiftingOperation] = []
    for request in requests:
        if request.load_template_id not in load_library:
            raise OperationBuildError("UNKNOWN_LOAD_TEMPLATE", request.load_template_id)
        if request.count <= 0:
            raise OperationBuildError("INVALID_LIFT_COUNT", str(request.count))
        load = _overridden_load(load_library[request.load_template_id], request)
        operations.append(
            LiftingOperation(
                id=_operation_id(request),
                name=f"{load.name}: {request.request_id}",
                stage_id=request.stage_id,
                source=request.source,
                destination=request.destination,
                load=load,
                count=request.count,
                sources=(request.source_locator,),
            )
        )
    return tuple(operations)


def validate_operations(project: ProjectV3) -> tuple[InputIssue, ...]:
    stage_ids = {stage.id for stage in project.stages}
    issues: list[InputIssue] = []
    for index, operation in enumerate(project.operations):
        if operation.stage_id not in stage_ids:
            issues.append(
                InputIssue(
                    "UNKNOWN_STAGE",
                    f"operations[{index}].stage_id",
                    f"Unknown construction stage: {operation.stage_id}",
                )
            )
        if operation.count <= 0:
            issues.append(
                InputIssue(
                    "INVALID_LIFT_COUNT",
                    f"operations[{index}].count",
                    "Lift count must be a positive integer.",
                )
            )
    return tuple(issues)
