"""Traceable crane configuration catalog and conservative chart lookup."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

from .domain import SourceKind, SourceLocator


EPS = 1e-6


@dataclass(frozen=True)
class CapacityPoint:
    radius_m: float
    capacity_kg: float


@dataclass(frozen=True)
class CraneConfigurationV3:
    id: str
    manufacturer: str
    model: str
    priority: int
    jib_length_m: float
    max_free_standing_hook_height_m: float
    capacity_curve: tuple[CapacityPoint, ...]
    allowed_jib_lengths_m: tuple[float, ...]
    allowed_tower_section_heights_m: tuple[float, ...]
    source: SourceLocator


@dataclass(frozen=True)
class CatalogIssue:
    code: str
    path: str
    message: str


def validate_capacity_curve(config: CraneConfigurationV3) -> tuple[CatalogIssue, ...]:
    issues: list[CatalogIssue] = []
    curve = config.capacity_curve
    if not curve:
        issues.append(CatalogIssue("CURVE_EMPTY", "capacity_curve", "Capacity curve cannot be empty."))
    for index, point in enumerate(curve):
        if not math.isfinite(point.radius_m) or not math.isfinite(point.capacity_kg):
            issues.append(
                CatalogIssue("NON_FINITE_VALUE", f"capacity_curve[{index}]", "Radius and capacity must be finite.")
            )
        if index == 0:
            continue
        previous = curve[index - 1]
        if abs(point.radius_m - previous.radius_m) <= EPS:
            issues.append(
                CatalogIssue("RADIUS_DUPLICATE", f"capacity_curve[{index}].radius_m", "Chart radii must be unique.")
            )
        elif point.radius_m < previous.radius_m:
            issues.append(
                CatalogIssue(
                    "RADIUS_ORDER_INVALID",
                    f"capacity_curve[{index}].radius_m",
                    "Chart radii must be strictly increasing.",
                )
            )
        if point.capacity_kg > previous.capacity_kg + EPS:
            issues.append(
                CatalogIssue(
                    "CAPACITY_NOT_MONOTONE",
                    f"capacity_curve[{index}].capacity_kg",
                    "Capacity cannot increase as radius increases.",
                )
            )

    source = config.source
    sha256 = source.sha256.lower()
    complete_hash = len(sha256) == 64 and all(character in "0123456789abcdef" for character in sha256)
    if not source.document_id.strip() or not source.locator.strip() or not complete_hash:
        issues.append(
            CatalogIssue(
                "SOURCE_INCOMPLETE",
                "source",
                "Crane data require document id, page locator and a 64-character SHA-256.",
            )
        )
    return tuple(issues)


def conservative_capacity_kg(config: CraneConfigurationV3, radius_m: float) -> float:
    """Return the next outward chart capacity without interpolation."""

    if not config.capacity_curve or not math.isfinite(radius_m):
        return 0.0
    terminal_radius = config.capacity_curve[-1].radius_m
    if radius_m > terminal_radius + EPS:
        return 0.0
    for point in config.capacity_curve:
        if radius_m <= point.radius_m + EPS:
            return point.capacity_kg
    return 0.0


def _parse_configuration(data: dict[str, object]) -> CraneConfigurationV3:
    source_data = data["source"]
    if not isinstance(source_data, dict):
        raise ValueError("SOURCE_INCOMPLETE")
    source = SourceLocator(
        kind=SourceKind(str(source_data.get("kind", "PASSPORT"))),
        document_id=str(source_data.get("document_id", "")),
        locator=str(source_data.get("locator", "")),
        note=str(source_data.get("note", "")),
        sha256=str(source_data.get("sha256", "")),
    )
    return CraneConfigurationV3(
        id=str(data["id"]),
        manufacturer=str(data["manufacturer"]),
        model=str(data["model"]),
        priority=int(data["priority"]),
        jib_length_m=float(data["jib_length_m"]),
        max_free_standing_hook_height_m=float(data["max_free_standing_hook_height_m"]),
        capacity_curve=tuple(CapacityPoint(float(row[0]), float(row[1])) for row in data["capacity_curve"]),  # type: ignore[union-attr]
        allowed_jib_lengths_m=tuple(float(value) for value in data["allowed_jib_lengths_m"]),  # type: ignore[union-attr]
        allowed_tower_section_heights_m=tuple(
            float(value) for value in data["allowed_tower_section_heights_m"]  # type: ignore[union-attr]
        ),
        source=source,
    )


def load_catalog_v3(path: str | Path) -> tuple[CraneConfigurationV3, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 3:
        raise ValueError("Unsupported crane catalog schema; expected version 3")
    configurations = tuple(_parse_configuration(item) for item in payload.get("configurations", ()))
    all_issues: list[str] = []
    for index, config in enumerate(configurations):
        for issue in validate_capacity_curve(config):
            all_issues.append(f"configurations[{index}].{issue.path}: {issue.code}: {issue.message}")
    if all_issues:
        raise ValueError("Invalid crane catalog:\n" + "\n".join(all_issues))
    return tuple(sorted(configurations, key=lambda config: (config.priority, config.id)))
