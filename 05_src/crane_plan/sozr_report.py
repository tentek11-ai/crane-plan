"""Dedicated SOZR drawing sheets and route diagnostics for the PPRk report."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle

from .models import Placement, ProjectInput, SOZRPlan, SOZRRestrictionClass


def _font() -> str:
    for path in (Path("C:/Windows/Fonts/isocpeur.ttf"), Path("C:/Windows/Fonts/ARIALN.TTF"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.exists():
            if "CranePlanSOZR" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("CranePlanSOZR", str(path)))
            return "CranePlanSOZR"
    return "Helvetica"


def build_sozr_table_rows(plan: SOZRPlan, point_start: int = 0, point_end: int | None = None) -> list[list[str]]:
    rows = [["Точка", "X, м", "Y, м", "Угол, °", "Вылет, м", "Тип", "H зоны, м", "Условие"]]
    for point in plan.points[point_start:point_end]:
        kind = "постоянная" if point.restriction_class is SOZRRestrictionClass.PERMANENT else "условная"
        rows.append([
            point.label, f"{point.x:.2f}", f"{point.y:.2f}", f"{point.bearing_deg:.2f}",
            f"{point.radius_m:.2f}", kind, f"{point.zone_height_m:.2f}", point.condition,
        ])
    return rows


_SOZR_WIDTHS = [12*mm,13*mm,13*mm,14*mm,15*mm,20*mm,18*mm,48*mm]


def build_sozr_table(plan: SOZRPlan, point_start: int = 0, point_end: int | None = None) -> Table:
    font = _font()
    rows = build_sozr_table_rows(plan, point_start, point_end)
    style=ParagraphStyle("SOZRCell",fontName=font,fontSize=5.2,leading=6.2)
    table=Table([[Paragraph(str(value),style) for value in row] for row in rows],colWidths=_SOZR_WIDTHS,repeatRows=1)
    table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.black),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E8E8E8")),("VALIGN",(0,0),(-1,-1),"TOP"),("FONTNAME",(0,0),(-1,-1),font)]))
    return table


def measure_sozr_table_height(plan: SOZRPlan, point_start: int = 0, point_end: int | None = None) -> float:
    table = build_sozr_table(plan, point_start, point_end)
    _, table_h = table.wrap(sum(_SOZR_WIDTHS), 1000*mm)
    return table_h


def _failure_text(failure) -> str:
    numbers = []
    if failure.actual_m is not None:
        numbers.append(f"фактически {failure.actual_m:g} м")
    if failure.required_m is not None:
        numbers.append(f"требуется {failure.required_m:g} м")
    detail = f" ({'; '.join(numbers)})" if numbers else ""
    zone = f", зона {failure.zone_id}" if failure.zone_id else ""
    return f"{failure.code.value}: {failure.message}{zone}{detail}"


def build_route_explanation(result) -> list[str]:
    lines: list[str] = []
    for route in getattr(result, "routes", ()): 
        accepted = [item for item in route.alternatives if item.accepted]
        chosen = min(accepted, key=lambda item: (-item.min_clearance_m, item.path_length_m), default=None)
        if chosen:
            lines.append(
                f"Операция {route.operation_id}: выбрана цепочка {chosen.kind}; "
                f"длина {chosen.path_length_m:g} м; минимальный запас {chosen.min_clearance_m:g} м."
            )
        for alternative in route.alternatives:
            if alternative.accepted:
                continue
            if alternative.failures:
                for failure in alternative.failures:
                    lines.append(f"Отклонена альтернатива {alternative.kind}: {_failure_text(failure)}.")
            else:
                lines.append(f"Отклонена альтернатива {alternative.kind}: безопасный маршрут не подтверждён.")
    for failure in getattr(result, "route_failures", ()):
        lines.append(f"Отказ построения цепочки: {_failure_text(failure)}.")
    for acceptance in getattr(result, "warning_acceptances", ()):
        text = f"Предупреждение {acceptance.warning_id} принято для хеша {acceptance.input_sha256[:12]}"
        if acceptance.comment:
            text += f": {acceptance.comment}"
        lines.append(text + ".")
    return lines


def _polygon(canvas, points, transform, color, fill=False, dash=None) -> None:
    if len(points) < 2:
        return
    path = canvas.beginPath()
    x, y = transform(points[0]); path.moveTo(x, y)
    for point in points[1:]:
        x, y = transform(point); path.lineTo(x, y)
    path.close()
    canvas.setStrokeColor(color); canvas.setFillColor(color); canvas.setLineWidth(1.2)
    if dash: canvas.setDash(*dash)
    if fill and hasattr(canvas, "setFillAlpha"): canvas.setFillAlpha(.18)
    canvas.drawPath(path, stroke=1, fill=1 if fill else 0)
    if fill and hasattr(canvas, "setFillAlpha"): canvas.setFillAlpha(1)
    canvas.setDash()


def draw_sozr_sheet(
    canvas,
    project: ProjectInput,
    placement: Placement,
    sozr_plan: SOZRPlan,
    sheet_number: int | str,
    *,
    title_prefix: str = "СОЗР",
    point_start: int = 0,
    point_end: int | None = None,
) -> None:
    font = _font(); width, height = canvas._pagesize
    canvas.saveState()
    canvas.setFont(font, 14); canvas.setFillColor(colors.HexColor("#17365D"))
    canvas.drawString(20*mm, height-14*mm, f"{title_prefix}. {sozr_plan.crane_id} {placement.model}. Координаты точек ограничения")
    all_points=[(sozr_plan.crane_x-sozr_plan.technical_radius_m,sozr_plan.crane_y-sozr_plan.technical_radius_m),(sozr_plan.crane_x+sozr_plan.technical_radius_m,sozr_plan.crane_y+sozr_plan.technical_radius_m)]
    all_points.extend((point.x, point.y) for point in sozr_plan.points)
    for contour in sozr_plan.permanent_contours+sozr_plan.conditional_contours: all_points.extend(contour.points)
    for contour in sozr_plan.admissible_contours: all_points.extend(contour)
    for route in sozr_plan.critical_routes: all_points.extend(waypoint.point for waypoint in route.waypoints)
    min_x=min(point[0] for point in all_points); max_x=max(point[0] for point in all_points)
    min_y=min(point[1] for point in all_points); max_y=max(point[1] for point in all_points)
    # Keep the point table at paper size and give larger formats a genuinely
    # larger drawing viewport rather than blank paper.
    drawing=(20*mm,70*mm,max(225*mm,width-195*mm),height-92*mm)
    scale=min(drawing[2]/max(max_x-min_x,1),drawing[3]/max(max_y-min_y,1))
    def transform(point):
        return (drawing[0]+(point[0]-min_x)*scale,drawing[1]+(point[1]-min_y)*scale)
    cx,cy=transform((sozr_plan.crane_x,sozr_plan.crane_y)); edge,_=transform((sozr_plan.crane_x+sozr_plan.technical_radius_m,sozr_plan.crane_y))
    for contour in sozr_plan.admissible_contours:
        _polygon(canvas,contour,transform,colors.HexColor("#7EC8E3"),True)
    canvas.setStrokeColor(colors.HexColor("#4F81BD")); canvas.setLineWidth(1); canvas.setDash(6,3); canvas.circle(cx,cy,abs(edge-cx),stroke=1,fill=0); canvas.setDash()
    canvas.setFillColor(colors.HexColor("#17365D")); canvas.circle(cx,cy,2*mm,stroke=1,fill=1); canvas.setFont(font,7); canvas.drawString(cx+3*mm,cy+3*mm,sozr_plan.crane_id)
    for contour in sozr_plan.permanent_contours: _polygon(canvas,contour.points,transform,colors.HexColor("#C00000"),True)
    for contour in sozr_plan.conditional_contours: _polygon(canvas,contour.points,transform,colors.HexColor("#E67E00"),True,(3,2))
    for route in sozr_plan.critical_routes:
        coords=[transform(waypoint.point) for waypoint in route.waypoints]
        if len(coords)>=2:
            canvas.setStrokeColor(colors.HexColor("#00A6D6")); canvas.setLineWidth(1.8)
            for start,end in zip(coords,coords[1:]): canvas.line(*start,*end)
    for point in sozr_plan.points:
        x,y=transform((point.x,point.y)); canvas.setFillColor(colors.white); canvas.setStrokeColor(colors.black); canvas.circle(x,y,2*mm,stroke=1,fill=1); canvas.setFillColor(colors.black); canvas.setFont(font,6); canvas.drawString(x+2.5*mm,y+1*mm,point.label)

    table=build_sozr_table(sozr_plan,point_start,point_end)
    _,table_h=table.wrap(153*mm,height)
    if table_h > height-92*mm+0.01:
        raise ValueError("Таблица СОЗР не помещается в выбранный формат листа")
    table.drawOn(canvas,drawing[0]+drawing[2]+7*mm,height-22*mm-table_h)
    canvas.setFillColor(colors.HexColor("#C00000")); canvas.setFont(font,7)
    caveat="Графическая СОЗР не является готовой настройкой прибора. Эксперт переносит точки в координатную защиту, налаживает и проверяет её по паспорту крана."
    canvas.drawString(20*mm,58*mm,caveat[:150]); canvas.drawString(20*mm,53*mm,caveat[150:])
    canvas.setStrokeColor(colors.black); canvas.rect(15*mm,5*mm,width-20*mm,height-10*mm)
    canvas.setFillColor(colors.black); canvas.setFont(font,6); canvas.drawRightString(width-18*mm,10*mm,f"Лист {sheet_number}; {project.project_code or 'шифр не задан'}")
    canvas.restoreState(); canvas.showPage()
