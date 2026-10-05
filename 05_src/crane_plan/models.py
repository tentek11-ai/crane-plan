"""Переносимые модели данных проекта без внешних зависимостей."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


Point = tuple[float, float]


@dataclass
class Load:
    name: str
    load_kg: float
    rigging_kg: float
    length_m: float
    width_m: float
    height_m: float
    lifts: int = 1

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

    @property
    def point(self) -> Point:
        return (self.x, self.y)


@dataclass
class SiteInput:
    boundary: list[Point]
    building: list[Point]
    restricted_zones: list[list[Point]] = field(default_factory=list)
    unloading_zone: list[Point] = field(default_factory=list)
    storage_zones: list[list[Point]] = field(default_factory=list)
    min_crane_to_building_m: float = 1.0
    max_crane_to_building_m: float = 25.0


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
    organization: str = ""
    project_code: str = ""
    project_stage: str = "ППРк"
    checked_by: str = ""
    approved_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
