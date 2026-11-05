"""Planning and rendering of bundle-driven calculated PPRk sheets.

The module selects paper formats and delegates engineering graphics to the
existing report/SOZR drawing primitives.  It never recalculates crane geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isclose
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.pagesizes import A1, A2, A3, landscape
from reportlab.lib.units import mm

from .geometry import distance_to_polygon, offset_polygon
from .models import ProjectInput, ScenarioResult
from .pprk_composer import PPRKBundle, PPRKContentsEntry, PPRKDocumentPart, PPRKSheet
from .pprk_context import scenario_render_sha256
from .pprk_context import PPRKActiveLoad

if TYPE_CHECKING:
    from reportlab.pdfgen.canvas import Canvas
    from .pprk_context import PPRKContext
    from .report import SectionDrawing


@dataclass(frozen=True)
class SheetFormat:
    name: str
    page_size: tuple[float, float]
    usable_width_mm: float
    usable_height_mm: float


@dataclass(frozen=True)
class SectionTransformContract:
    """Exact section transform shared by format planning and PDF drawing."""

    calibrated: bool
    left: float
    bottom: float
    shown_width: float
    shown_height: float
    pixel_scale: float
    pixel_height: float
    origin_x: float
    origin_y: float
    axis_dx: float
    axis_dy: float
    metres_per_pixel: float
    minimum_elevation: float
    elevation_span: float
    contour_min_x: float

    def height_point(self, value: float) -> tuple[float, float]:
        if self.calibrated:
            px = self.origin_x + self.axis_dx * (value / self.metres_per_pixel)
            py = self.origin_y + self.axis_dy * (value / self.metres_per_pixel)
            return self.left + px * self.pixel_scale, self.bottom + (self.pixel_height - py) * self.pixel_scale
        return self.origin_x, self.origin_y + (value - self.minimum_elevation) / self.elevation_span * self.shown_height

    def point(self, point: tuple[float, float]) -> tuple[float, float]:
        horizontal, value = point
        if self.calibrated:
            px = self.origin_x + (value * self.axis_dx + horizontal * self.axis_dy) / self.metres_per_pixel
            py = self.origin_y + (value * self.axis_dy - horizontal * self.axis_dx) / self.metres_per_pixel
            return self.left + px * self.pixel_scale, self.bottom + (self.pixel_height - py) * self.pixel_scale
        return (
            self.origin_x + (horizontal - self.contour_min_x) * mm,
            self.origin_y + (value - self.minimum_elevation) / self.elevation_span * self.shown_height,
        )


@dataclass(frozen=True)
class CalculatedSheetPlan:
    sheet_id: str
    source_sheet_id: str
    title: str
    render_kind: str
    designation: str
    stage: str
    sheet_format: SheetFormat
    crane_index: int | None = None
    item_start: int = 0
    item_end: int = 0
    section_drawing: SectionDrawing | None = field(default=None, compare=False, repr=False)
    active_loads: tuple[PPRKActiveLoad, ...] | None = None
    pending_reason: str = ""


@dataclass(frozen=True)
class CalculatedSheetRenderContext:
    project: ProjectInput
    scenario: ScenarioResult
    pprk_context: "PPRKContext | None" = None
    verified_danger_zone_offset_m: float | None = None
    require_verified_danger_zone: bool = False
    scenario_index: int = 0
    protocol_run_id: str = ""
    protocol_result_sha256: str = ""


_FORMATS = (
    SheetFormat("A3", landscape(A3), 385.0, 247.0),
    SheetFormat("A2", landscape(A2), 559.0, 370.0),
    SheetFormat("A1", landscape(A1), 806.0, 544.0),
)

_LOAD_WIDTHS = [12 * mm, 80 * mm, 25 * mm, 27 * mm, 25 * mm, 42 * mm, 20 * mm]
_LOAD_HEADER = ["№", "Груз", "Груз, кг", "Оснастка, кг", "Итого, кг", "Габарит, м", "Подъёмов"]


def _load_schedule_rows(source, item_start: int, item_end: int) -> list[list[str]]:
    if source is None:
        return [_LOAD_HEADER, ["", "НЕ ЗАПОЛНЕНО: исходные данные грузов в комплекте", "", "", "", "", ""]]
    active = [item for item in (source.loads if isinstance(source, ProjectInput) else source) if item.active]
    rows = [_LOAD_HEADER]
    for index, load in enumerate(active[item_start:item_end], item_start + 1):
        rows.append([
            str(index), load.name, f"{load.load_kg:g}", f"{load.rigging_kg:g}",
            f"{load.total_kg:g}", "×".join(f"{value:g}" for value in (load.dimensions_m if isinstance(load, PPRKActiveLoad) else (load.length_m, load.width_m, load.height_m))), str(load.lifts) if load.lifts is not None else "НЕ ЗАПОЛНЕНО",
        ])
    return rows


def load_schedule_table_height(project: ProjectInput, item_start: int, item_end: int) -> float:
    from .report import _canvas_table_height, _font

    return _canvas_table_height(_load_schedule_rows(project, item_start, item_end), _LOAD_WIDTHS, _font(), 7)


def _measured_ranges(
    item_count: int,
    height_for_range,
    available_height: float,
) -> tuple[tuple[int, int], ...] | None:
    if item_count == 0:
        return ((0, 0),) if height_for_range(0, 0) <= available_height else None
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < item_count:
        if height_for_range(start, start + 1) > available_height:
            return None
        end = start + 1
        while end < item_count and height_for_range(start, end + 1) <= available_height:
            end += 1
        ranges.append((start, end))
        start = end
    return tuple(ranges)


def _load_schedule_layout(active_loads) -> tuple[SheetFormat, tuple[tuple[int, int], ...]]:
    count = sum(1 for load in active_loads or () if load.active)
    for sheet_format in _FORMATS:
        available = sheet_format.page_size[1] - 73 * mm
        ranges = _measured_ranges(count, lambda start, end: load_schedule_table_height(active_loads, start, end), available)
        if ranges is not None:
            return sheet_format, ranges
    raise ValueError("Строка грузовой ведомости не помещается на A1")


def sozr_table_height(plan, item_start: int, item_end: int) -> float:
    from .sozr_report import measure_sozr_table_height

    return measure_sozr_table_height(plan, item_start, item_end)


def _sozr_layout(plan, minimum_format: SheetFormat) -> tuple[SheetFormat, tuple[tuple[int, int], ...]]:
    start_index = next(index for index, item in enumerate(_FORMATS) if item.name == minimum_format.name)
    for sheet_format in _FORMATS[start_index:]:
        available = sheet_format.page_size[1] - 92 * mm
        ranges = _measured_ranges(
            len(plan.points),
            lambda start, end: sozr_table_height(plan, start, end),
            available,
        )
        if ranges is not None:
            return sheet_format, ranges
    raise ValueError("Строка таблицы СОЗР не помещается на A1")


def _section_elevations(project: ProjectInput, scenario: ScenarioResult) -> list[float]:
    elevations = [0.0, project.parapet_m - project.pit_bottom_m]
    for placement in scenario.placements:
        elevations.extend([
            placement.required_hook_height_m,
            placement.jib_level_m or 0.0,
            placement.accepted_crane_height_m or 0.0,
            placement.max_free_standing_height_m or 0.0,
            *placement.tie_in_levels_m,
        ])
    elevations.extend(point[1] for point in project.section_building_contour)
    return elevations


def section_transform_contract(
    project: ProjectInput,
    scenario: ScenarioResult,
    page_size: tuple[float, float],
) -> SectionTransformContract:
    """Build the one transform used by both section preflight and renderer."""

    from pathlib import Path

    width, height = page_size
    left, bottom = 22 * mm, 48 * mm
    draw_w, draw_h = width - 29 * mm, height - 68 * mm
    source = Path(project.source_section_pdf) if project.source_section_pdf else None
    calibrated = bool(source and source.exists() and project.section_m_per_pixel > 0)
    elevations = _section_elevations(project, scenario)
    minimum, maximum = min(elevations), max(elevations)
    span = max(1.0, maximum - minimum)
    contour_min_x = min((point[0] for point in project.section_building_contour), default=0.0)
    if calibrated:
        from pypdf import PdfReader

        page = PdfReader(str(source)).pages[0]
        x0, y0, x1, y1 = project.section_crop_box
        pixel_w = float(page.mediabox.width) * project.section_render_scale * (x1 - x0)
        pixel_h = float(page.mediabox.height) * project.section_render_scale * (y1 - y0)
        scale = min(draw_w / pixel_w, draw_h / pixel_h)
        shown_w, shown_h = pixel_w * scale, pixel_h * scale
        return SectionTransformContract(
            True,
            left + (draw_w - shown_w) / 2,
            bottom + (draw_h - shown_h) / 2,
            shown_w,
            shown_h,
            scale,
            pixel_h,
            project.section_origin_x_px,
            project.section_origin_y_px,
            project.section_axis_dx,
            project.section_axis_dy,
            project.section_m_per_pixel,
            minimum,
            span,
            contour_min_x,
        )
    left_crane_extent = 0.0
    if project.section_building_contour:
        left_crane_extent = max(
            (
                distance_to_polygon((placement.x, placement.y), project.site.building)
                for index, placement in enumerate(scenario.placements)
                if index % 2 == 0
            ),
            default=0.0,
        )
    return SectionTransformContract(
        False,
        left,
        bottom,
        draw_w,
        draw_h,
        1.0,
        draw_h,
        22 * mm + 70 * mm + left_crane_extent * mm,
        35 * mm,
        0.0,
        -1.0,
        1.0,
        minimum,
        span,
        contour_min_x,
    )


def _section_anchors_fit(
    contract: SectionTransformContract,
    project: ProjectInput,
    scenario: ScenarioResult,
    sheet_format: SheetFormat,
) -> bool:
    # Reject extreme calibrations before expanding a tower into lattice panels.
    points = [contract.height_point(value) for value in _section_elevations(project, scenario)]
    points.extend(contract.point(point) for point in project.section_building_contour)
    width, height = sheet_format.page_size
    return all(7 * mm <= x <= width - 7 * mm and 20 * mm <= y <= height - 20 * mm for x, y in points)


def choose_sheet_format(
    bounds: tuple[float, float, float, float],
    min_text_mm: float,
) -> SheetFormat:
    """Return the smallest landscape ISO sheet fitting plotted mm extents.

    ``bounds`` are already-scaled drawing extents in millimetres.  The caller
    controls engineering scale; this function protects the reserved frame and
    a readable text height of at least 1.8 mm.
    """

    if min_text_mm < 1.8:
        raise ValueError("Минимальная высота текста на графическом листе — 1,8 мм")
    min_x, min_y, max_x, max_y = (float(value) for value in bounds)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0 or height <= 0:
        raise ValueError("Границы графического листа должны иметь положительную площадь")
    for candidate in _FORMATS:
        if width <= candidate.usable_width_mm and height <= candidate.usable_height_mm:
            return candidate
    raise ValueError("Расчётная схема не помещается на A1 при принятом масштабе")


def calculated_plan_world_bounds(
    project: ProjectInput,
    scenario: ScenarioResult,
    verified_danger_zone_offset_m: float | None = None,
) -> tuple[float, float, float, float]:
    """Return the exact world envelope consumed by the site-plan primitive."""

    points: list[tuple[float, float]] = []
    for polygon in (
        project.site.boundary,
        project.site.building,
        project.site.unloading_zone,
        *project.site.storage_zones,
    ):
        points.extend(polygon or ())
    for zone in project.site.restricted_zones:
        points.extend(zone.polygon)
    if verified_danger_zone_offset_m is not None and project.site.building:
        points.extend(offset_polygon(project.site.building, verified_danger_zone_offset_m))
    points.extend(work_point.point for work_point in project.work_points)
    for placement in scenario.placements:
        radius = placement.jib_length_m or placement.max_radius_m
        points.extend(((placement.x - radius, placement.y - radius), (placement.x + radius, placement.y + radius)))
    if not points:
        return (0.0, 0.0, 100.0, 60.0)
    # Two metres of plot-space padding keeps circle strokes, labels and crane
    # symbols visibly inside the clipping rectangle at 1:200.
    return (
        min(point[0] for point in points) - 2.0,
        min(point[1] for point in points) - 2.0,
        max(point[0] for point in points) + 2.0,
        max(point[1] for point in points) + 2.0,
    )


def _sozr_world_bounds(scenario: ScenarioResult, crane_index: int | None) -> tuple[float, float, float, float]:
    if crane_index is None or not (0 <= crane_index < len(scenario.placements)):
        raise ValueError("Для листа СОЗР не назначен кран")
    sozr = scenario.placements[crane_index].sozr_plan
    if sozr is None:
        raise ValueError("Для листа СОЗР отсутствуют подтверждённые данные")
    points = [
        (sozr.crane_x - sozr.technical_radius_m, sozr.crane_y - sozr.technical_radius_m),
        (sozr.crane_x + sozr.technical_radius_m, sozr.crane_y + sozr.technical_radius_m),
    ]
    points.extend((point.x, point.y) for point in sozr.points)
    for contour in (*sozr.permanent_contours, *sozr.conditional_contours):
        points.extend(contour.points)
    for contour in sozr.admissible_contours:
        points.extend(contour)
    for route in sozr.critical_routes:
        points.extend(waypoint.point for waypoint in route.waypoints)
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _fitting_section_drawing(
    project: ProjectInput, scenario: ScenarioResult, designation: str, sheet_format: SheetFormat
) -> SectionDrawing | None:
    from .report import build_section_drawing

    transform = section_transform_contract(project, scenario, sheet_format.page_size)
    if not _section_anchors_fit(transform, project, scenario, sheet_format):
        return None
    drawing = build_section_drawing(project, scenario, designation, sheet_format.page_size, transform)
    return drawing if drawing.fits_frame() else None


def _plan_section(
    project: ProjectInput, scenario: ScenarioResult, designation: str
) -> tuple[SheetFormat, SectionDrawing]:
    elevations = _section_elevations(project, scenario)
    # Retain the nominal 1:200 vertical scale and minimum section sheet width.
    # All paper-space geometry and annotation sizes come from the drawing itself.
    elevation_span_m = max(elevations) - min(elevations)
    required = (0.0, 0.0, 500.0, max(180.0, elevation_span_m * 5.0))
    minimum = choose_sheet_format(required, 2.5)
    minimum_index = next(index for index, item in enumerate(_FORMATS) if item.name == minimum.name)
    for candidate in _FORMATS[minimum_index:]:
        drawing = _fitting_section_drawing(project, scenario, designation, candidate)
        if drawing is not None:
            return candidate, drawing
    raise ValueError("Расчётная схема разреза не помещается на A1 в принятой системе координат")


def _format_for_kind(
    kind: str,
    project: ProjectInput,
    scenario: ScenarioResult,
    crane_index: int | None = None,
    verified_danger_zone_offset_m: float | None = None,
) -> SheetFormat:
    if kind in {"site_plan", "sozr", "route_plan", "joint_work_plan"}:
        if kind in {"sozr", "route_plan"}:
            min_x, min_y, max_x, max_y = _sozr_world_bounds(scenario, crane_index)
        else:
            min_x, min_y, max_x, max_y = calculated_plan_world_bounds(
                project, scenario, verified_danger_zone_offset_m
            )
        # The main plan is issued at 1:200.  СОЗР sheets reserve a fixed
        # 170 mm band for their point table and may use 1:286 for the plan
        # viewport; labels and line weights remain at their paper sizes.
        plot_scale = 3.5 if kind in {"sozr", "route_plan"} else 5.0
        reserve = 170.0 if kind in {"sozr", "route_plan"} else 0.0
        required = (
            0.0,
            0.0,
            max(1.0, (max_x - min_x) * plot_scale) + reserve,
            max(1.0, (max_y - min_y) * plot_scale),
        )
        return choose_sheet_format(required, 2.5)
    return _FORMATS[0]


_RENDER_KINDS = {
    "SITE_PLAN": "site_plan",
    "SOZR_PLAN": "sozr",
    "VERTICAL_SECTION": "vertical_section",
    "ROUTE_PLAN": "route_plan",
    "JOINT_WORK_PLAN": "joint_work_plan",
    "JOINT_WORK_SCHEDULE": "joint_work_schedule",
    "LOAD_SCHEDULE": "load_schedule",
}


def plan_calculated_sheets(
    bundle: PPRKBundle,
    project: ProjectInput,
    scenario: ScenarioResult,
) -> tuple[CalculatedSheetPlan, ...]:
    """Expand graphical bundle references into deterministic physical sheets."""

    from .pprk_composer import effective_render_project
    project = effective_render_project(bundle, project)
    result: list[CalculatedSheetPlan] = []
    verified_danger_offset = (
        bundle.calculation_binding.verified_danger_zone_offset_m
        if bundle.calculation_binding is not None
        else None
    )
    for part in bundle.parts:
        if part.kind != "graphical":
            continue
        source = part.sheets[0]
        reference = source.sheet_id.removeprefix("drawing.")
        render_kind = _RENDER_KINDS.get(reference)
        if render_kind is None:
            raise ValueError(f"Неизвестная графическая ссылка {reference}: {source.sheet_id}")
        pending = dict(source.fields).get("pending_reason")
        if pending:
            if bundle.requested_status.value not in ("PRELIMINARY", "REVIEW"):
                raise ValueError(f"Для листа {source.designation} отсутствуют подтверждённые данные: {pending}")
            result.append(CalculatedSheetPlan(source.sheet_id, source.sheet_id, part.title, "pending",
                                              source.designation, "pending", _FORMATS[0], pending_reason=pending))
            continue
        section_drawing = None
        if render_kind in {"sozr", "route_plan"}:
            available = [index for index, placement in enumerate(scenario.placements) if placement.sozr_plan is not None]
            expansions = []
            for index in available:
                minimum = _format_for_kind(render_kind, project, scenario, index, verified_danger_offset)
                sheet_format, ranges = _sozr_layout(scenario.placements[index].sozr_plan, minimum)
                expansions.extend(("accepted", index, start, end, sheet_format) for start, end in ranges)
            if not expansions:
                expansions = [("accepted", None, 0, 0, _FORMATS[0])]
        elif render_kind == "vertical_section":
            sheet_format, section_drawing = _plan_section(project, scenario, source.designation)
            expansions = [("accepted", None, 0, 0, sheet_format)]
        elif render_kind == "load_schedule":
            sheet_format, ranges = _load_schedule_layout(bundle.active_loads)
            expansions = [("accepted", None, start, end, sheet_format) for start, end in ranges]
        else:
            expansions = [("accepted", None, 0, 0, _format_for_kind(render_kind, project, scenario, None, verified_danger_offset))]
        normalized_expansions = [
            row if len(row) == 5 else (*row, 0, 0, _format_for_kind(render_kind, project, scenario, row[1], verified_danger_offset))
            for row in expansions
        ]
        for expansion_index, (stage, crane_index, item_start, item_end, sheet_format) in enumerate(normalized_expansions, 1):
            suffix = f".{expansion_index}" if len(expansions) > 1 else ""
            stage_title = {
                "accepted": "",
            }[stage]
            title = part.title if not stage_title else f"{part.title} — {stage_title}"
            result.append(
                CalculatedSheetPlan(
                    sheet_id=f"{source.sheet_id}{suffix}",
                    source_sheet_id=source.sheet_id,
                    title=title,
                    render_kind=render_kind,
                    designation=f"{source.designation}{suffix}",
                    stage=stage,
                    sheet_format=sheet_format,
                    crane_index=crane_index,
                    item_start=item_start,
                    item_end=item_end,
                    section_drawing=section_drawing,
                    active_loads=bundle.active_loads,
                )
            )
    return tuple(result)


def expand_bundle_graphical_parts(
    bundle: PPRKBundle,
    plans: tuple[CalculatedSheetPlan, ...],
) -> PPRKBundle:
    """Replace logical graphical references by every emitted physical sheet."""

    plans_by_source: dict[str, list[CalculatedSheetPlan]] = {}
    for plan in plans:
        plans_by_source.setdefault(plan.source_sheet_id, []).append(plan)
    parts: list[PPRKDocumentPart] = []
    for part in bundle.parts:
        if part.kind != "graphical":
            parts.append(part)
            continue
        source_id = part.sheets[0].sheet_id
        physical = plans_by_source.get(source_id, [])
        parts.append(
            replace(
                part,
                sheets=tuple(
                    PPRKSheet(
                        plan.sheet_id,
                        plan.title,
                        "graphical",
                        designation=plan.designation,
                    )
                    for plan in physical
                ),
            )
        )
    contents = tuple(
        PPRKContentsEntry(
            sheet.sheet_id,
            part.part_id,
            sheet.title,
            sheet.designation or str(sheet.page_number or ""),
            part.kind,
        )
        for part in parts
        for sheet in part.sheets
    )
    return replace(bundle, parts=tuple(parts), contents=contents)


def bind_calculated_scenario(
    bundle: PPRKBundle,
    scenarios: list[ScenarioResult],
) -> ScenarioResult:
    """Bind a composed bundle to exactly one accepted legacy scenario."""

    binding = bundle.calculation_binding
    if binding is None:
        if len(scenarios) != 1:
            raise ValueError("Bundle без расчётной привязки требует ровно один сценарий")
        return scenarios[0]

    def matches(scenario: ScenarioResult) -> bool:
        if str(scenario.status).upper() in {"REJECTED", "BLOCKED", "INVALID"}:
            return False
        if binding.scenario_render_sha256:
            return scenario_render_sha256(scenario) == binding.scenario_render_sha256
        if len(scenario.placements) != len(binding.placements):
            return False
        for actual, expected in zip(scenario.placements, binding.placements):
            numeric_pairs = (
                (actual.x, expected.x_m),
                (actual.y, expected.y_m),
                (actual.max_radius_m, expected.max_radius_m),
                (actual.jib_length_m, expected.jib_length_m),
                (actual.required_hook_height_m, expected.required_hook_height_m),
            )
            if actual.crane_id != expected.legacy_configuration_reference or actual.model != expected.model:
                return False
            if any(not isclose(float(left), float(right), abs_tol=1e-7) for left, right in numeric_pairs):
                return False
            if expected.jib_level_m is not None and not isclose(float(actual.jib_level_m or 0.0), expected.jib_level_m, abs_tol=1e-7):
                return False
        return True

    matches_found = [scenario for scenario in scenarios if matches(scenario)]
    if len(matches_found) != 1:
        raise ValueError(f"Расчётная привязка bundle должна определять ровно один сценарий; найдено {len(matches_found)}")
    return matches_found[0]


def calculated_sheet_page_map(
    plans: tuple[CalculatedSheetPlan, ...],
    start_page: int,
) -> dict[str, int]:
    """Return actual page starts for stable graphical bundle targets."""

    result: dict[str, int] = {}
    for offset, plan in enumerate(plans):
        result.setdefault(plan.source_sheet_id, start_page + offset)
        result[plan.sheet_id] = start_page + offset
    return result


def _draw_load_schedule(canvas: "Canvas", plan: CalculatedSheetPlan, context: CalculatedSheetRenderContext) -> None:
    from .report import _font, _sheet_frame, _canvas_table

    project = context.project
    font = _font()
    width, height = canvas._pagesize
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#17365D"))
    canvas.setFont(font, 14)
    canvas.drawString(22 * mm, height - 14 * mm, "ГРУЗОВАЯ ВЕДОМОСТЬ И РАСЧЁТНЫЕ МАССЫ")
    rows = _load_schedule_rows(plan.active_loads, plan.item_start, plan.item_end)
    table_height = _canvas_table(canvas, rows, 22 * mm, height - 23 * mm, _LOAD_WIDTHS, font, 7)
    if table_height > height - 73 * mm + 0.01:
        raise ValueError("Грузовая ведомость не помещается в выбранный формат листа")
    _sheet_frame(canvas, project, "Грузовая ведомость", plan.designation)
    canvas.restoreState()
    canvas.showPage()


def draw_calculated_sheet(canvas, sheet, context):
    """Append canonical release identity to the same physical calculated page."""
    from . import report
    original_show = canvas.showPage
    page_number = canvas._pageNumber
    def identity():
        canvas.saveState()
        canvas.setFillColor(colors.black)
        canvas.setFont(report._font(), 6)
        text = (f"Вариант {context.scenario_index + 1}; протокол {context.protocol_run_id or 'НЕ ЗАПОЛНЕНО'}; "
                f"результат {context.protocol_result_sha256[:12] or 'НЕ ЗАПОЛНЕНО'}")
        canvas.drawString(22 * mm, sheet.sheet_format.page_size[1] - 18 * mm, text)
        canvas.restoreState()
    def finish_page():
        identity()
        original_show()
    canvas.showPage = finish_page
    try:
        _draw_calculated_sheet_content(canvas, sheet, context)
        if canvas._pageNumber == page_number:
            identity()
    finally:
        canvas.showPage = original_show


def _draw_calculated_sheet_content(
    canvas: "Canvas",
    sheet: CalculatedSheetPlan,
    context: CalculatedSheetRenderContext,
) -> None:
    """Draw one planned sheet by delegating to the established primitives."""

    from . import report
    from .sozr_report import draw_sozr_sheet

    canvas.setPageSize(sheet.sheet_format.page_size)
    scenario = context.scenario
    stage_label = ""
    if sheet.render_kind == "pending":
        report._sheet_frame(canvas, context.project, sheet.title, sheet.designation)
        height = sheet.sheet_format.page_size[1]
        canvas.setFont(report._font(), 16)
        canvas.drawString(25 * mm, height - 35 * mm, "ОЖИДАЕТ РАСЧЁТА")
        canvas.setFont(report._font(), 12)
        canvas.drawString(25 * mm, height - 48 * mm, sheet.pending_reason)
        return
    if sheet.render_kind == "site_plan":
        report._plan_page(
            canvas,
            context.project,
            scenario,
            sheet.designation,
            stage_label=stage_label,
            verified_danger_zone_offset_m=context.verified_danger_zone_offset_m,
            require_verified_danger_zone=context.require_verified_danger_zone,
        )
    elif sheet.render_kind == "vertical_section":
        drawing = sheet.section_drawing or _fitting_section_drawing(
            context.project, scenario, sheet.designation, sheet.sheet_format
        )
        if drawing is None:
            raise ValueError("Расчётная схема разреза не помещается в заданном формате")
        drawing.draw(canvas)
    elif sheet.render_kind in {"sozr", "route_plan"}:
        index = sheet.crane_index if sheet.crane_index is not None else 0
        if not (0 <= index < len(scenario.placements)) or scenario.placements[index].sozr_plan is None:
            raise ValueError(f"Для листа {sheet.sheet_id} отсутствуют подтвержденные данные СОЗР")
        placement = scenario.placements[index]
        title_prefix = "МАРШРУТЫ ПОДАЧИ И СОЗР" if sheet.render_kind == "route_plan" else "СОЗР"
        draw_sozr_sheet(
            canvas,
            context.project,
            placement,
            placement.sozr_plan,
            sheet.designation,
            title_prefix=title_prefix,
            point_start=sheet.item_start,
            point_end=sheet.item_end,
        )
    elif sheet.render_kind == "joint_work_plan":
        report._coordination_page(canvas, context.project, scenario, context.scenario_index + 1, sheet.designation)
    elif sheet.render_kind == "joint_work_schedule":
        if scenario.joint_plan is None:
            raise ValueError("График совместной работы требует подтвержденный план двух кранов")
        report._joint_work_schedule_page(canvas, context.project, scenario, context.scenario_index + 1, sheet.designation)
    elif sheet.render_kind == "load_schedule":
        _draw_load_schedule(canvas, sheet, context)
    else:
        raise ValueError(f"Неизвестный тип расчётного листа: {sheet.render_kind}")

