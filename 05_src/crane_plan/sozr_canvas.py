"""Pure Canvas primitives and a thin Tk renderer for a SOZR plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import Point, SOZRPlan


@dataclass(frozen=True)
class SOZRCanvasStyle:
    technical_color: str = "#4fc3f7"
    admissible_color: str = "#173e52"
    permanent_color: str = "#e53945"
    conditional_color: str = "#ff9d2e"
    route_color: str = "#56d6ff"
    point_color: str = "#ffffff"
    technical_width: int = 2
    restriction_width: int = 3
    route_width: int = 3
    technical_dash: tuple[int, int] = (8, 5)


@dataclass(frozen=True)
class CanvasPrimitive:
    kind: str
    layer: str
    coords: tuple[float, ...]
    color: str
    width: int = 1
    fill: str = ""
    dash: tuple[int, ...] = ()
    label: str = ""


def _flat(points: tuple[Point, ...], transform: Callable[[Point], Point]) -> tuple[float, ...]:
    return tuple(value for point in points for value in transform(point))


def build_sozr_canvas_primitives(
    plan: SOZRPlan,
    transform: Callable[[Point], Point],
    style: SOZRCanvasStyle | None = None,
) -> list[CanvasPrimitive]:
    style = style or SOZRCanvasStyle()
    center = (plan.crane_x, plan.crane_y)
    radius = plan.technical_radius_m
    left_top = transform((center[0] - radius, center[1] - radius))
    right_bottom = transform((center[0] + radius, center[1] + radius))
    bounds = (left_top[0], left_top[1], right_bottom[0], right_bottom[1])
    result = [
        CanvasPrimitive("polygon", "admissible", _flat(contour, transform), style.admissible_color, fill=style.admissible_color)
        for contour in plan.admissible_contours
    ]
    if not result:
        result.append(CanvasPrimitive("ellipse", "admissible", bounds, style.admissible_color))
    for contour in plan.permanent_contours:
        result.append(CanvasPrimitive(
            "polygon", "permanent", _flat(contour.points, transform), style.permanent_color,
            style.restriction_width, fill=style.permanent_color,
        ))
    for contour in plan.conditional_contours:
        result.append(CanvasPrimitive(
            "polygon", "conditional", _flat(contour.points, transform), style.conditional_color,
            style.restriction_width, fill=style.conditional_color, label=f"H={contour.zone_height_m:g} м",
        ))
    for route in plan.critical_routes:
        points = tuple(waypoint.point for waypoint in route.waypoints)
        if len(points) >= 2:
            result.append(CanvasPrimitive(
                "polyline", "route", _flat(points, transform), style.route_color,
                style.route_width, label=route.operation_id,
            ))
    for point in plan.points:
        x, y = transform((point.x, point.y))
        result.append(CanvasPrimitive(
            "point", "restriction_point", (x, y), style.point_color, 2, label=point.label,
        ))
    result.append(CanvasPrimitive(
        "ellipse", "technical_circle", bounds, style.technical_color,
        style.technical_width, dash=style.technical_dash,
        label=f"{plan.crane_id} R={radius:g} м",
    ))
    return result


def draw_sozr_canvas(canvas, primitives: list[CanvasPrimitive], tag: str = "sozr") -> None:
    """Render already transformed primitives; this function computes no geometry."""
    canvas.delete(tag)
    for item in primitives:
        tags = (tag, f"sozr_{item.layer}")
        if item.kind == "ellipse":
            canvas.create_oval(*item.coords, outline=item.color, fill=item.fill, stipple="gray25" if item.fill else "", width=item.width, dash=item.dash, tags=tags)
        elif item.kind == "polygon":
            canvas.create_polygon(*item.coords, outline=item.color, fill=item.fill, stipple="gray25", width=item.width, tags=tags)
        elif item.kind == "polyline":
            canvas.create_line(*item.coords, fill=item.color, width=item.width, arrow="last", tags=tags)
        elif item.kind == "point":
            x, y = item.coords
            canvas.create_oval(x - 4, y - 4, x + 4, y + 4, outline=item.color, fill=item.color, tags=tags)
        if item.label:
            if item.kind == "ellipse":
                x, y = item.coords[0] + 6, item.coords[1] + 6
            elif item.kind == "point":
                x, y = item.coords[0] + 7, item.coords[1] - 7
            else:
                xs=item.coords[0::2]; ys=item.coords[1::2]; x=sum(xs)/len(xs); y=sum(ys)/len(ys)
            canvas.create_text(x,y,text=item.label,fill=item.color,anchor="nw",tags=tags)
