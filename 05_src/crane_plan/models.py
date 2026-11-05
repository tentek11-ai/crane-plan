"""Переносимые модели данных проекта без внешних зависимостей."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .pprk_models import PPRKReleaseConfig


Point = tuple[float, float]


def _plain_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_value(item) for item in value]
    return value


class RestrictedZoneKind(str, Enum):
    LOAD_PROHIBITED = "LOAD_PROHIBITED"
    HEIGHT_OBSTACLE = "HEIGHT_OBSTACLE"
    FULL_EXCLUSION = "FULL_EXCLUSION"


@dataclass
class RestrictedZone:
    id: str
    name: str
    kind: RestrictedZoneKind
    polygon: list[Point]
    height_m: float
    horizontal_clearance_m: float = 0.0
    note: str = ""
    verified: bool = True
    source_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.kind = RestrictedZoneKind(self.kind)
        self.polygon = [tuple(point) for point in self.polygon]
        if len(set(self.polygon)) < 3:
            raise ValueError("Контур опасной зоны должен содержать не менее трёх уникальных точек")
        if self.height_m < 0:
            raise ValueError("Высота опасной зоны не может быть отрицательной")
        if self.horizontal_clearance_m < 0:
            raise ValueError("Дополнительный горизонтальный запас не может быть отрицательным")

    def __iter__(self):
        return iter(self.polygon)

    def __len__(self) -> int:
        return len(self.polygon)

    def __getitem__(self, index):
        return self.polygon[index]


@dataclass(frozen=True)
class WarningAcceptance:
    warning_id: str
    input_sha256: str
    comment: str = ""


@dataclass
class Load:
    name: str
    load_kg: float
    rigging_kg: float
    length_m: float
    width_m: float
    height_m: float
    lifts: int = 1
    active: bool = True
    exclusion_reason: str = ""
    rigging_height_m: float = 1.5
    rigging_type: str = ""
    rigging_branch_count: int | None = None
    sling_identification: str = ""
    rigging_capacity_kg: float | None = None
    rigging_evidence: str = ""
    rigging_verified: bool = False

    @property
    def total_kg(self) -> float:
        return self.load_kg + self.rigging_kg

    @property
    def largest_dimension_m(self) -> float:
        return max(self.length_m, self.width_m, self.height_m)


@dataclass
class WorkPoint:
    x: float
    y: float
    level_m: float
    load_index: int
    name: str = "Точка подачи груза"
    special_roof_load: bool = False

    @property
    def point(self) -> Point:
        return (self.x, self.y)


@dataclass
class SiteInput:
    boundary: list[Point]
    building: list[Point]
    restricted_zones: list[RestrictedZone] = field(default_factory=list)
    unloading_zone: list[Point] = field(default_factory=list)
    storage_zones: list[list[Point]] = field(default_factory=list)
    min_crane_to_building_m: float = 1.0
    max_crane_to_building_m: float = 25.0

    def __post_init__(self) -> None:
        normalized: list[RestrictedZone] = []
        for index, zone in enumerate(self.restricted_zones, start=1):
            if isinstance(zone, RestrictedZone):
                normalized.append(zone)
            else:
                normalized.append(
                    RestrictedZone(
                        id=f"runtime-legacy-zone-{index}",
                        name=f"Опасная зона {index}",
                        kind=RestrictedZoneKind.FULL_EXCLUSION,
                        polygon=[tuple(point) for point in zone],
                        height_m=0.0,
                        verified=False,
                    )
                )
        self.restricted_zones = normalized


@dataclass
class ProjectInput:
    name: str
    city: str
    year: int
    author: str
    email: str
    pit_bottom_m: float
    parapet_m: float
    site: SiteInput
    loads: list[Load]
    work_points: list[WorkPoint]
    priority: str = "cost"
    hours_per_day: float = 24.0
    utilization: float = 0.7
    protective_screen_possible: bool = False
    commercial_offer_present: bool = False
    commercial_offer_daily_cost: float = 0.0
    source_plan_pdf: str = ""
    source_section_pdf: str = ""
    plan_origin_x_px: float = 0.0
    plan_origin_y_px: float = 0.0
    plan_m_per_pixel: float = 0.0
    plan_render_scale: float = 1.5
    section_origin_x_px: float = 0.0
    section_origin_y_px: float = 0.0
    section_axis_dx: float = 0.0
    section_axis_dy: float = -1.0
    section_m_per_pixel: float = 0.0
    section_render_scale: float = 1.5
    plan_crop_box: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    section_crop_box: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    plan_background_intensity: float = 0.35
    section_background_intensity: float = 0.35
    floors: int = 1
    tie_ins_possible: bool = True
    tie_length_m: float = 12.0
    tie_angle_deg: float = 60.0
    section_building_contour: list[Point] = field(default_factory=list)
    organization: str = ""
    project_code: str = ""
    project_stage: str = "ППРк"
    checked_by: str = ""
    approved_by: str = ""
    schema_version: int = 4
    restricted_zones_confirmed: bool = False
    loads_verified: bool = False
    route_angle_step_deg: float = 1.0
    route_radius_step_m: float = 0.5
    vertical_clearance_m: float = 3.0
    warning_acceptances: list[WarningAcceptance] = field(default_factory=list)
    pprk_release: PPRKReleaseConfig = field(default_factory=PPRKReleaseConfig)

    def to_dict(self) -> dict[str, Any]:
        result = _plain_value(asdict(self))
        result["warning_acceptances"] = [
            {
                "warning_id": item.warning_id,
                "input_sha256": item.input_sha256,
                **({"comment": item.comment} if item.comment else {}),
            }
            for item in self.warning_acceptances
        ]
        return result


class RouteFailureCode(str, Enum):
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    DESTINATION_BLOCKED = "DESTINATION_BLOCKED"
    HEIGHT_EXCEEDED = "HEIGHT_EXCEEDED"
    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"
    INNER_BYPASS_BLOCKED = "INNER_BYPASS_BLOCKED"
    OUTER_BYPASS_BLOCKED = "OUTER_BYPASS_BLOCKED"
    SITE_BOUNDARY = "SITE_BOUNDARY"
    SECOND_CRANE_CONFLICT = "SECOND_CRANE_CONFLICT"
    NO_PATH = "NO_PATH"
    EXACT_RECHECK_FAILED = "EXACT_RECHECK_FAILED"


@dataclass(frozen=True)
class RouteEndpoint:
    id: str
    point: Point
    level_m: float = 0.0
    kind: str = ""


@dataclass(frozen=True)
class RouteFailure:
    code: RouteFailureCode
    message: str
    zone_id: str = ""
    required_m: float | None = None
    actual_m: float | None = None


@dataclass(frozen=True)
class RouteWaypoint:
    x: float
    y: float
    hook_height_m: float
    movement: str

    @property
    def point(self) -> Point:
        return (self.x, self.y)


@dataclass(frozen=True)
class RouteAlternative:
    kind: str
    accepted: bool
    min_clearance_m: float
    path_length_m: float
    failures: tuple[RouteFailure, ...] = ()


@dataclass(frozen=True)
class LiftRoute:
    operation_id: str
    waypoints: tuple[RouteWaypoint, ...]
    transport_hook_height_m: float
    alternatives: tuple[RouteAlternative, ...]
    input_sha256: str


@dataclass
class RoutePlanResult:
    route: LiftRoute | None
    failures: list[RouteFailure] = field(default_factory=list)


@dataclass(frozen=True)
class LogisticsLeg:
    operation_id: str
    source_kind: str
    source_id: str
    destination_kind: str
    destination_id: str
    source: RouteEndpoint
    destination: RouteEndpoint
    load_index: int


@dataclass
class ChainPlanResult:
    safe: bool
    routes: list[LiftRoute] = field(default_factory=list)
    failures: list[RouteFailure] = field(default_factory=list)
    failed_leg: LogisticsLeg | None = None


class SOZRRestrictionClass(str, Enum):
    PERMANENT = "PERMANENT"
    CONDITIONAL = "CONDITIONAL"


@dataclass(frozen=True)
class SOZRContour:
    zone_id: str
    points: tuple[Point, ...]
    restriction_class: SOZRRestrictionClass
    zone_height_m: float
    condition: str


@dataclass(frozen=True)
class SOZRPoint:
    label: str
    x: float
    y: float
    bearing_deg: float
    radius_m: float
    restriction_class: SOZRRestrictionClass
    zone_id: str
    zone_height_m: float
    condition: str


@dataclass(frozen=True)
class SOZRPlan:
    crane_id: str
    technical_radius_m: float
    permanent_contours: tuple[SOZRContour, ...]
    conditional_contours: tuple[SOZRContour, ...]
    points: tuple[SOZRPoint, ...]
    critical_routes: tuple[LiftRoute, ...]
    algorithm_version: str
    crane_x: float = 0.0
    crane_y: float = 0.0
    admissible_contours: tuple[tuple[Point, ...], ...] = ()


@dataclass(frozen=True)
class CraneConfiguration:
    id: str
    model: str
    priority: int
    jib_length_m: float
    max_capacity_kg: float
    max_free_standing_hook_height_m: float
    capacity_curve: tuple[tuple[float, float], ...]
    source: str


@dataclass
class Placement:
    crane_id: str
    model: str
    x: float
    y: float
    assigned_work_points: list[int]
    max_radius_m: float
    required_hook_height_m: float
    jib_length_m: float = 0.0
    assigned_contour_points: list[int] = field(default_factory=list)
    jib_level_m: float | None = None
    allowed_sector_start_deg: float | None = None
    allowed_sector_end_deg: float | None = None
    tower_exclusion_start_deg: float | None = None
    tower_exclusion_end_deg: float | None = None
    assigned_logistics_zones: list[int] = field(default_factory=list)
    max_free_standing_height_m: float = 0.0
    accepted_crane_height_m: float = 0.0
    tie_in_levels_m: list[float] = field(default_factory=list)
    tie_in_stage_sections: list[int] = field(default_factory=list)
    total_additional_sections: int = 0
    required_tie_length_m: float = 0.0
    tie_geometry_ok: bool = True
    tie_nearest_floors: list[int] = field(default_factory=list)
    radial_limits_m: list[tuple[float, float]] = field(default_factory=list)
    sozr_plan: SOZRPlan | None = None


@dataclass
class JointCranePlan:
    axis_distance_m: float
    working_horizontal_clearance_m: float
    parking_horizontal_clearance_m: float
    vertical_separation_m: float
    higher_crane_index: int
    priority_crane_index: int
    overlap_exists: bool
    overlap_area_m2: float
    overlap_polygon: list[Point] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    jib_structural_height_m: float = 2.0
    tower_protection_radius_m: float = 2.0
    combined_tower_envelope_m: float = 4.0
    schedule_stages: list[str] = field(default_factory=list)
    minimum_vertical_clearance_m: float = 1.0


@dataclass
class ScenarioResult:
    status: str
    placements: list[Placement]
    reasons: list[str]
    warnings: list[str]
    calendar_days: float | None = None
    score: float | None = None
    joint_plan: JointCranePlan | None = None
    estimated_cost: float | None = None
    total_active_lifts: int = 0
    accounted_lifts: int = 0
    crane_work_hours: list[float] = field(default_factory=list)
    selection_audit: list[str] = field(default_factory=list)
    routes: list[LiftRoute] = field(default_factory=list)
    route_failures: list[RouteFailure] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _plain_value(asdict(self))
