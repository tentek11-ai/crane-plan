"""Формирование комплектного предварительного ППРк в стиле реальных проектов."""
from __future__ import annotations

import io
from dataclasses import dataclass
from functools import partial
from operator import methodcaller
from datetime import datetime
from html import escape
from math import atan2, cos, hypot, pi, radians, sin
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Callable
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfgen.pathobject import PDFPathObject
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.utils import ImageReader, simpleSplit

from .geometry import distance_to_polygon, offset_polygon, polygon_bounds, polygon_centroid, normalize_angular_sector
from .models import ProjectInput, ScenarioResult
from .normative import NormativeInputError, danger_zone_offset_from_outer_edge
from .pdf_workspace import render_page
from .sozr_report import build_route_explanation, draw_sozr_sheet
from .tieins import horizontal_intersections

if TYPE_CHECKING:
    from .pprk_composer import PPRKBundle

NAVY = colors.HexColor("#17365D")
RED = colors.HexColor("#C00000")


def _sector_text(start, end, decimals=1):
    """Показать сектор в диапазоне 0–360°, разделив переход через ноль."""
    if start is None or end is None:
        return "не назначен"
    if end-start >= 359.999:
        return "0°…360°"
    raw_end=end; start=start%360; finish=end%360; fmt=f"{{:.{decimals}f}}°"
    if start<=finish and raw_end<=360:
        return f"{fmt.format(start)}…{fmt.format(finish)}"
    return f"{fmt.format(start)}…360°; 0°…{fmt.format(finish)}"


def _font() -> str:
    # ISOCP с кириллицей визуально соответствует чертёжному шрифту типа А/Б
    # по ГОСТ 2.304; Arial Narrow оставлен переносимым резервом.
    for path in (Path("C:/Windows/Fonts/isocpeur.ttf"), Path("C:/Windows/Fonts/ARIALN.TTF"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.exists():
            if "CranePlanGOST" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("CranePlanGOST", str(path)))
            return "CranePlanGOST"
    return "Helvetica"


def _table(rows, font, widths=None, size=8, header=True):
    cell_style=ParagraphStyle("TableCell",fontName=font,fontSize=size,leading=size+2,textColor=colors.black)
    data=[[value if hasattr(value,"wrap") else Paragraph(escape(str(value)).replace("\n","<br/>"),cell_style) for value in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), size),
        ("LEADING", (0, 0), (-1, -1), size + 2), ("GRID", (0, 0), (-1, -1), .45, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.black)]
    table.setStyle(TableStyle(commands))
    return table


def _stamp_left(page_width):
    return page_width - 190 * mm


def _project_stamp(canvas, project: ProjectInput, sheet_title: str, sheet_number: str = ""):
    font=_font(); width,_=canvas._pagesize; x=_stamp_left(width); y=5*mm; w=185*mm; h=40*mm
    canvas.setStrokeColor(colors.black); canvas.setLineWidth(.5)
    # Низ и правая сторона совпадают с рамкой листа: отдельной пересекающей рамки нет.
    canvas.line(x,y,x,y+h); canvas.line(x,y+h,x+w,y+h)
    for row in (8,16,24,32): canvas.line(x,y+row*mm,x+w,y+row*mm)
    canvas.line(x+65*mm,y,x+65*mm,y+24*mm); canvas.line(x+165*mm,y,x+165*mm,y+h)
    canvas.line(x+105*mm,y+24*mm,x+105*mm,y+h); canvas.line(x+135*mm,y+24*mm,x+135*mm,y+h)
    canvas.setFillColor(colors.black); canvas.setFont(font,5.6)
    canvas.drawString(x+2*mm,y+34.5*mm,(project.organization or "Организация ____________________")[:38])
    canvas.drawCentredString(x+120*mm,y+34.5*mm,"Стадия"); canvas.drawCentredString(x+150*mm,y+34.5*mm,"Лист")
    canvas.drawCentredString(x+175*mm,y+34.5*mm,"Листов")
    canvas.setFont(font,8); canvas.drawCentredString(x+120*mm,y+26.5*mm,project.project_stage or "ППРк")
    canvas.drawCentredString(x+150*mm,y+26.5*mm,str(sheet_number or "__")); canvas.drawCentredString(x+175*mm,y+26.5*mm,"__")
    canvas.setFont(font,5.4); canvas.drawString(x+2*mm,y+18.5*mm,(project.name or "Наименование объекта ____________________")[:48])
    canvas.drawString(x+67*mm,y+18.5*mm,(project.project_code or "Шифр проекта ____________________")[:48])
    canvas.setFont(font,6); canvas.drawString(x+67*mm,y+10.5*mm,sheet_title[:55])
    canvas.setFont(font,5.2); canvas.drawString(x+2*mm,y+10.5*mm,f"Разраб. {(project.author or '__________')[:18]}")
    canvas.drawString(x+2*mm,y+2.5*mm,f"Пров. {(project.checked_by or '__________')[:20]}")
    canvas.drawString(x+34*mm,y+2.5*mm,f"Утв. {(project.approved_by or '__________')[:20]}")


SHEET_FRAME_LINE_WIDTH = 0.7


def _sheet_frame_rect(width, height):
    return 20 * mm, 5 * mm, width - 25 * mm, height - 10 * mm


def _sheet_border(canvas):
    width,height=canvas._pagesize; canvas.setStrokeColor(colors.black); canvas.setLineWidth(SHEET_FRAME_LINE_WIDTH)
    canvas.rect(*_sheet_frame_rect(width, height))


def _sheet_frame(canvas, project: ProjectInput, sheet_title: str, sheet_number: str = ""):
    _sheet_border(canvas)
    _project_stamp(canvas,project,sheet_title,sheet_number)


def _page_frame(canvas, doc, project: ProjectInput):
    canvas.saveState(); _sheet_frame(canvas,project,"Пояснительная записка",str(doc.page)); canvas.restoreState()


def _draw_polygon(canvas, points, transform, stroke, fill=None, width=1.3):
    if not points: return
    path = canvas.beginPath(); x,y = transform(points[0]); path.moveTo(x,y)
    for point in points[1:]: x,y=transform(point); path.lineTo(x,y)
    path.close(); canvas.setStrokeColor(stroke); canvas.setLineWidth(width)
    if fill: canvas.setFillColor(fill)
    canvas.drawPath(path, stroke=1, fill=1 if fill else 0)


def _draw_lattice(canvas, start, end, width=3*mm, panels=8):
    """Плоская ферма стрелы/противострелы с раскосами."""
    x1,y1=start; x2,y2=end; length=max(hypot(x2-x1,y2-y1),1); nx=-(y2-y1)/length*width/2; ny=(x2-x1)/length*width/2
    a=(x1+nx,y1+ny); b=(x1-nx,y1-ny); c=(x2-nx,y2-ny); d=(x2+nx,y2+ny)
    canvas.line(*a,*d); canvas.line(*b,*c); canvas.line(*a,*b); canvas.line(*c,*d)
    last_top,last_bottom=a,b
    for index in range(1,panels+1):
        ratio=index/panels; cx=x1+(x2-x1)*ratio; cy=y1+(y2-y1)*ratio
        top=(cx+nx,cy+ny); bottom=(cx-nx,cy-ny)
        canvas.line(*top,*bottom)
        if index%2: canvas.line(*last_top,*bottom)
        else: canvas.line(*last_bottom,*top)
        last_top,last_bottom=top,bottom


def _draw_tower_crane_plan(canvas, center, target, reach, color, label):
    """Flat-top EC-B silhouette based on the manufacturer's arrangement."""
    x,y=center; tx,ty=target; length=max(hypot(tx-x,ty-y),1); ux=(tx-x)/length; uy=(ty-y)/length
    jib=max(22*mm,reach); counter=min(24*mm,jib*.28)
    canvas.setStrokeColor(color); canvas.setFillColor(colors.white); canvas.setLineWidth(.8)
    canvas.rect(x-3.4*mm,y-3.4*mm,6.8*mm,6.8*mm,stroke=1,fill=1); canvas.line(x-3.4*mm,y-3.4*mm,x+3.4*mm,y+3.4*mm); canvas.line(x-3.4*mm,y+3.4*mm,x+3.4*mm,y-3.4*mm)
    canvas.circle(x,y,4.4*mm,stroke=1,fill=0)
    _draw_lattice(canvas,(x,y),(x+ux*jib,y+uy*jib),3.2*mm,max(6,int(jib/(8*mm))))
    _draw_lattice(canvas,(x,y),(x-ux*counter,y-uy*counter),4*mm,4)
    # EC-B counterweight packet and machinery deck at the short counter-jib.
    canvas.setFillColor(color)
    for shift in (0,3*mm,6*mm):
        bx=x-ux*(counter+2*mm)-uy*shift/3; by=y-uy*(counter+2*mm)+ux*shift/3
        canvas.rect(bx-1.7*mm,by-1.7*mm,3.4*mm,3.4*mm,stroke=1,fill=1)
    cabin=(x+ux*5*mm-uy*4*mm,y+uy*5*mm+ux*4*mm); canvas.rect(cabin[0]-2*mm,cabin[1]-1.6*mm,4*mm,3.2*mm,stroke=1,fill=0)
    trolley=(x+ux*jib*.72,y+uy*jib*.72); canvas.rect(trolley[0]-1.2*mm,trolley[1]-1.2*mm,2.4*mm,2.4*mm,stroke=1,fill=0)
    canvas.setFont(_font(),7); canvas.drawString(x+5*mm,y+5*mm,label)


def _draw_sector_overlay(canvas, center, radius, placement, color, exclusion_inner_radius=0.0):
    """Разрешённый сектор, запретная дуга и блокировка подхода к соседней башне."""
    if placement.allowed_sector_start_deg is None or placement.allowed_sector_end_deg is None:
        return
    x,y=center
    start,end,extent=normalize_angular_sector(placement.allowed_sector_start_deg,placement.allowed_sector_end_deg)
    canvas.setStrokeColor(color); canvas.setLineWidth(2.2); canvas.setDash()
    if extent:
        canvas.arc(x-radius,y-radius,x+radius,y+radius,startAng=start,extent=extent)
    for angle in (start,end):
        rad=angle*pi/180; canvas.line(x,y,x+radius*cos(rad),y+radius*sin(rad))
    if extent<360.0:
        canvas.setStrokeColor(RED); canvas.setLineWidth(1.5); canvas.setDash(4,2)
        canvas.arc(x-radius,y-radius,x+radius,y+radius,startAng=end,extent=360-extent)
        canvas.setDash()
    if placement.tower_exclusion_start_deg is not None and placement.tower_exclusion_end_deg is not None:
        ex_start,ex_end,ex_extent=normalize_angular_sector(placement.tower_exclusion_start_deg,placement.tower_exclusion_end_deg)
        canvas.setStrokeColor(RED); canvas.setFillColor(colors.HexColor("#F8CECC")); canvas.setLineWidth(1.2); canvas.setDash(3,2)
        for angle in (ex_start,ex_end):
            rad=angle*pi/180; canvas.line(x+exclusion_inner_radius*cos(rad),y+exclusion_inner_radius*sin(rad),x+radius*cos(rad),y+radius*sin(rad))
        if ex_extent:
            canvas.arc(x-exclusion_inner_radius,y-exclusion_inner_radius,x+exclusion_inner_radius,y+exclusion_inner_radius,startAng=ex_start,extent=ex_extent)
            canvas.arc(x-radius,y-radius,x+radius,y+radius,startAng=ex_start,extent=ex_extent)
        canvas.setDash()


def _draw_tower_protection(canvas, center, radius, color):
    """Защитный габарит башни от оси, а не условная точка нулевого размера."""
    canvas.saveState(); canvas.setStrokeColor(color); canvas.setFillColor(colors.HexColor("#FFF2CC")); canvas.setLineWidth(1.0); canvas.setDash(2,2)
    if hasattr(canvas,"setFillAlpha"): canvas.setFillAlpha(.55)
    canvas.circle(center[0],center[1],radius,stroke=1,fill=1); canvas.setDash(); canvas.restoreState()


def _draw_tower_crane_elevation(canvas, base_x, base_y, top_y, jib_half, color, label, direction=1):
    """Recognisable Liebherr EC-B flat-top crane elevation."""
    mast_w=7*mm; canvas.setStrokeColor(color); canvas.setFillColor(colors.white); canvas.setLineWidth(.8)
    canvas.rect(base_x-mast_w/2,base_y,mast_w,max(top_y-base_y,8*mm),stroke=1,fill=0)
    segments=max(2,int(max(top_y-base_y,8*mm)/(11*mm)))
    for index in range(segments):
        y1=base_y+(top_y-base_y)*index/segments; y2=base_y+(top_y-base_y)*(index+1)/segments
        canvas.line(base_x-mast_w/2,y1,base_x+mast_w/2,y2); canvas.line(base_x+mast_w/2,y1,base_x-mast_w/2,y2)
    # Cross base, climbing frame, slewing ring and machinery platform.
    canvas.rect(base_x-7*mm,base_y-2*mm,14*mm,2*mm,stroke=1,fill=0); canvas.line(base_x-7*mm,base_y-2*mm,base_x-3*mm,base_y+3*mm); canvas.line(base_x+7*mm,base_y-2*mm,base_x+3*mm,base_y+3*mm)
    canvas.rect(base_x-mast_w*.72,top_y-14*mm,mast_w*1.44,14*mm,stroke=1,fill=0); canvas.circle(base_x,top_y,2.2*mm,stroke=1,fill=0)
    main_end=base_x+direction*jib_half; counter_end=base_x-direction*jib_half*.31
    _draw_lattice(canvas,(base_x,top_y),(main_end,top_y),4*mm,max(7,int(jib_half/(7*mm))))
    _draw_lattice(canvas,(base_x,top_y),(counter_end,top_y),5*mm,5)
    # Counterweight packet, winch and cabin under the root - characteristic EC-B layout.
    for block in range(4):
        x=counter_end-direction*(block*2.2*mm); canvas.rect(x-1.1*mm,top_y-4.5*mm,2.2*mm,8*mm,stroke=1,fill=0)
    canvas.rect(base_x-direction*10*mm,top_y+2.2*mm,6*mm,2.5*mm,stroke=1,fill=0)
    cabin_x=base_x+direction*4.5*mm; path=canvas.beginPath(); path.moveTo(cabin_x,top_y-1*mm); path.lineTo(cabin_x+direction*7*mm,top_y-1*mm); path.lineTo(cabin_x+direction*6*mm,top_y-8*mm); path.lineTo(cabin_x,top_y-7*mm); path.close(); canvas.drawPath(path,stroke=1,fill=0)
    trolley_x=base_x+direction*jib_half*.78; canvas.rect(trolley_x-1.5*mm,top_y-3*mm,3*mm,3*mm,stroke=1,fill=0)
    canvas.line(trolley_x-1*mm,top_y-3*mm,trolley_x-1*mm,base_y+10*mm); canvas.line(trolley_x+1*mm,top_y-3*mm,trolley_x+1*mm,base_y+10*mm)
    canvas.rect(trolley_x-2*mm,base_y+7*mm,4*mm,3*mm,stroke=1,fill=0); canvas.line(trolley_x,base_y+7*mm,trolley_x,base_y+4*mm); canvas.arc(trolley_x-1.8*mm,base_y+1*mm,trolley_x+1.8*mm,base_y+5*mm,startAng=180,extent=250)
    canvas.setFillColor(color); canvas.setFont(_font(),7); canvas.drawString(base_x+7*mm,top_y+5*mm,label)


def _pdf_layout(source: Path, render_scale: float, left: float, bottom: float, draw_w: float, draw_h: float, crop_box=(0.0,0.0,1.0,1.0)):
    from pypdf import PdfReader
    page=PdfReader(str(source)).pages[0]
    x0,y0,x1,y1=crop_box
    pixel_w=float(page.mediabox.width)*render_scale*(x1-x0); pixel_h=float(page.mediabox.height)*render_scale*(y1-y0)
    scale=min(draw_w/pixel_w,draw_h/pixel_h)
    shown_w,shown_h=pixel_w*scale,pixel_h*scale
    return left+(draw_w-shown_w)/2,bottom+(draw_h-shown_h)/2,shown_w,shown_h,scale


def _merge_vector_background(overlay_page, source: Path, left: float, bottom: float, shown_w: float, shown_h: float):
    from pypdf import PdfReader, PdfWriter, Transformation
    src=PdfReader(str(source)).pages[0]
    if src.get("/Rotate",0): src.transfer_rotation_to_content()
    width,height=float(overlay_page.mediabox.width),float(overlay_page.mediabox.height)
    holder=PdfWriter(); result=holder.add_blank_page(width=width,height=height)
    transform=Transformation().scale(shown_w/float(src.mediabox.width),shown_h/float(src.mediabox.height)).translate(left,bottom)
    result.merge_transformed_page(src,transform,over=False)
    result.merge_page(overlay_page,over=True)
    return result


def _plan_page(
    canvas: Canvas,
    project: ProjectInput,
    scenario: ScenarioResult,
    number: int | str,
    draw_source: bool = True,
    stage_label: str = "",
    *,
    verified_danger_zone_offset_m: float | None = None,
    require_verified_danger_zone: bool = False,
) -> None:
    font=_font(); width,height=canvas._pagesize; canvas.saveState(); canvas.setFont(font,14); canvas.setFillColor(NAVY)
    stage_suffix=f". {stage_label}" if stage_label else ""
    identity = f"Лист {number}" if str(number).startswith("ГЧ-") else f"Вариант {number}"
    canvas.drawString(22*mm,height-13*mm,f"СТРОЙГЕНПЛАН. {identity}: расположение башенных кранов{stage_suffix}")
    left,bottom=22*mm,48*mm; draw_w,draw_h=width-29*mm,height-68*mm; transform=None
    source=Path(project.source_plan_pdf) if project.source_plan_pdf else None
    if source and source.exists() and project.plan_m_per_pixel>0:
        left,bottom,shown_w,shown_h,scale=_pdf_layout(source,project.plan_render_scale,left,bottom,draw_w,draw_h,project.plan_crop_box)
        if draw_source:
            image=render_page(source,0,project.plan_render_scale,project.plan_crop_box,project.plan_background_intensity)
            canvas.drawImage(ImageReader(image),left,bottom,shown_w,shown_h,preserveAspectRatio=True,mask="auto")
        def transform(point):
            px=project.plan_origin_x_px+point[0]/project.plan_m_per_pixel
            py=project.plan_origin_y_px-point[1]/project.plan_m_per_pixel
            return left+px*scale,bottom+(shown_h/scale-py)*scale
    else:
        # Use the same exact envelope as the format planner: crane radii and
        # remote СОЗР/route geometry must not be clipped outside the site.
        from .pprk_sheets import calculated_plan_world_bounds
        min_x,min_y,max_x,max_y=calculated_plan_world_bounds(project,scenario,verified_danger_zone_offset_m)
        scale=min(draw_w/max(1,max_x-min_x),draw_h/max(1,max_y-min_y))
        transform=lambda p:(left+(p[0]-min_x)*scale,bottom+(p[1]-min_y)*scale)
    _draw_polygon(canvas,project.site.boundary,transform,colors.black)
    _draw_polygon(canvas,project.site.building,transform,colors.HexColor("#0066CC"),colors.HexColor("#DCE6F1"),1.6)
    for zone in project.site.restricted_zones: _draw_polygon(canvas,zone,transform,RED,colors.HexColor("#FADBD8"),1.5)
    _draw_polygon(canvas,project.site.unloading_zone,transform,colors.HexColor("#E67E00"),colors.HexColor("#FDEBD0"),1.5)
    for zone in project.site.storage_zones: _draw_polygon(canvas,zone,transform,colors.HexColor("#7A1FA2"),colors.HexColor("#E8DAEF"),1.5)
    danger_offset = verified_danger_zone_offset_m
    if require_verified_danger_zone and danger_offset is None and project.work_points:
        raise ValueError("Для графического листа отсутствует подтверждённый вылет опасной зоны")
    if danger_offset is None and not require_verified_danger_zone:
        try:
            offsets=[danger_zone_offset_from_outer_edge(wp.level_m,project.loads[wp.load_index].largest_dimension_m) for wp in project.work_points if 0<=wp.load_index<len(project.loads)]
            danger_offset=max(offsets) if offsets else None
        except NormativeInputError:
            danger_offset=None
    if danger_offset is not None:
        canvas.setDash(5,3); _draw_polygon(canvas,offset_polygon(project.site.building,danger_offset),transform,colors.HexColor("#D00000"),None,1.0); canvas.setDash()
    visible_work_points = [
        (index, wp)
        for index, wp in enumerate(project.work_points, 1)
        if not stage_label
        or ("ВЫШЕ" in stage_label and wp.level_m > 0)
        or ("НИЖЕ" in stage_label and wp.level_m <= 0)
    ]
    for index,wp in visible_work_points:
        x,y=transform(wp.point); canvas.setFillColor(colors.HexColor("#009E73")); canvas.rect(x-1.5*mm,y-1.5*mm,3*mm,3*mm,stroke=0,fill=1)
        canvas.setFont(font,7); canvas.drawString(x+2*mm,y+2*mm,f"ТПГ-{index}")
    crane_colors=[colors.HexColor("#004C99"),colors.HexColor("#C05000")]
    building_target=transform(polygon_centroid(project.site.building))
    clip=canvas.beginPath(); clip.rect(left,bottom,draw_w,draw_h); canvas.saveState(); canvas.clipPath(clip,stroke=0,fill=0)
    if scenario.joint_plan and scenario.joint_plan.overlap_polygon:
        canvas.saveState()
        if hasattr(canvas,"setFillAlpha"): canvas.setFillAlpha(.22)
        _draw_polygon(canvas,scenario.joint_plan.overlap_polygon,transform,RED,colors.HexColor("#F8CECC"),1.0)
        canvas.restoreState()
    for index,placement in enumerate(scenario.placements,1):
        physical_radius=placement.jib_length_m or placement.max_radius_m
        x,y=transform((placement.x,placement.y)); rx,_=transform((placement.x+physical_radius,placement.y)); radius=abs(rx-x)
        color=crane_colors[(index-1)%len(crane_colors)]; canvas.setStrokeColor(color); canvas.setLineWidth(.9); canvas.setDash(6,3); canvas.circle(x,y,radius,stroke=1,fill=0); canvas.setDash()
        if placement.radial_limits_m:
            envelope=[(placement.x+limit*cos(radians(angle)),placement.y+limit*sin(radians(angle))) for angle,limit in placement.radial_limits_m]
            _draw_polygon(canvas,envelope,transform,color,None,1.6)
        if scenario.joint_plan:
            tower_edge,_=transform((placement.x+scenario.joint_plan.tower_protection_radius_m,placement.y)); _draw_tower_protection(canvas,(x,y),abs(tower_edge-x),color)
        inner=0.0
        if scenario.joint_plan and physical_radius>0:
            inner=radius*max(0.0,min(1.0,(scenario.joint_plan.axis_distance_m-(scenario.joint_plan.working_horizontal_clearance_m+scenario.joint_plan.tower_protection_radius_m))/physical_radius))
        _draw_sector_overlay(canvas,(x,y),radius,placement,color,inner)
        _draw_tower_crane_plan(canvas,(x,y),building_target,radius,color,f"К{index} {placement.model}; L={physical_radius:.1f} м")
    canvas.restoreState()
    canvas.setFillColor(colors.black); canvas.setFont(font,7)
    canvas.drawString(22*mm,52*mm,"Синий - здание; красный - запрет/опасная огибающая; оранжевый - разгрузка; фиолетовый - склад; ТПГ - точка подачи груза.")
    canvas.drawString(22*mm,48.5*mm,"Толстая дуга - разрешённый сектор; красная штриховая дуга - блокировка; розовая линза - зона взаимного доступа кранов.")
    if danger_offset is not None:
        canvas.drawString(22*mm,55.5*mm,f"Подтверждённый вылет опасной зоны от контура здания: {danger_offset:.2f} м.")
    canvas.drawRightString(width-7*mm,48.5*mm,"Эскиз спроецирован на загруженный план PDF")
    _sheet_frame(canvas,project,"Стройгенплан. Расстановка башенных кранов",str(number)); canvas.restoreState(); canvas.showPage()


class _SectionRecorder:
    """Collect the existing ReportLab primitives with their final paper coordinates."""

    def __init__(self, page_size):
        self._pagesize = page_size
        self.commands = []

    def __getattr__(self, name):
        if name not in {
            "line", "rect", "circle", "arc", "drawPath", "drawString", "drawRightString",
            "drawCentredString", "setDash", "setLineWidth", "setStrokeColor", "setFillColor",
            "setFont",
        }:
            raise AttributeError(name)

        def record(*args, **kwargs):
            self.commands.append(methodcaller(name, *args, **kwargs))

        return record

    def beginPath(self):
        return PDFPathObject()

    def table(self, rows, x, y_top, widths, font, size):
        table = _canvas_table_object(rows, widths, font, size)
        _, height = table.wrap(sum(widths), 1000 * mm)
        bottom = y_top - height
        self.commands.append(partial(table.drawOn, x=x, y=bottom))
        return bottom


def _section_ink_bounds(page_size, commands):
    """Measure recorded objects, including stroke widths and positioned text."""
    import pypdfium2 as pdfium

    packet = io.BytesIO()
    proof = Canvas(packet, pagesize=page_size)
    for command in commands:
        command(proof)
    proof.showPage()
    proof.save()
    with pdfium.PdfDocument(packet.getvalue()) as document:
        page = document[0]
        return [obj.get_bounds() for obj in page.get_objects(max_depth=1)]


@dataclass(frozen=True)
class SectionDrawing:
    """Final page-space commands used both for ink measurement and PDF output."""

    page_size: tuple[float, float]
    commands: tuple[Callable, ...]
    background_rect: tuple[float, float, float, float] | None
    background_image: Callable | None
    table_clears_inset: bool
    notes_fit: bool

    def draw(self, canvas, *, draw_source=True):
        if canvas._pagesize != self.page_size:
            raise ValueError("Размер листа разреза не соответствует проверенному формату")
        if not self.notes_fit:
            raise ValueError("Примечания разреза не помещаются с требуемым зазором")
        canvas.saveState()
        if self.background_rect is not None and draw_source:
            image = ImageReader(self.background_image())
            canvas.drawImage(image, *self.background_rect, preserveAspectRatio=True, mask="auto")
        for command in self.commands:
            command(canvas)
        canvas.restoreState()
        canvas.showPage()

    def fits_frame(self):
        """Measure the same vectors, positioned glyphs, table cells and stamp as output."""
        if not self.table_clears_inset or not self.notes_fit:
            return False
        width, height = self.page_size
        # PDFium's conservative path bounds include one line width around the
        # frame centreline. Allow 0.01 pt for PDF coordinate serialization.
        bleed = SHEET_FRAME_LINE_WIDTH + 0.01
        x, y, w, h = _sheet_frame_rect(width, height)

        def inside(bounds):
            left, bottom, right, top = bounds
            return x - bleed <= left <= right <= x + w + bleed and y - bleed <= bottom <= top <= y + h + bleed

        # The aspect-fitted crop can occupy at most this exact destination box.
        if self.background_rect is not None:
            left, bottom, image_width, image_height = self.background_rect
            if not inside((left, bottom, left + image_width, bottom + image_height)):
                return False

        return all(inside(bounds) for bounds in _section_ink_bounds(self.page_size, self.commands))


def _section_notes(canvas, font, notes):
    """Fit complete notes into a free interval beside the stamp on either section."""
    # The footer sits inside the frame and below the calibrated source/inset.
    # One extra point covers glyph side bearings and PDF coordinate rounding.
    gap = 3 * mm + 1
    left = 22 * mm
    right = _stamp_left(canvas._pagesize[0]) - gap
    bottom, top = 6 * mm, 20 * mm
    blocked = sorted(
        (x0 - gap, x1 + gap)
        for x0, y0, x1, y1 in _section_ink_bounds(canvas._pagesize, canvas.commands)
        if y0 < top + gap and y1 > bottom - gap and x1 + gap > left and x0 - gap < right
    )
    size, leading = 7, 4 * mm
    for start, end in [*blocked, (right, right)]:
        width = start - left
        if width > 0:
            lines = [(color, line) for color, note in notes for line in simpleSplit(note, font, size, width)]
            baseline = 8 * mm + (len(lines) - 1) * leading
            if baseline + size <= top and all(pdfmetrics.stringWidth(line, font, size) <= width for _, line in lines):
                canvas.setFont(font, size)
                for color, line in lines:
                    canvas.setFillColor(color)
                    canvas.drawString(left, baseline, line)
                    baseline -= leading
                return True
        left = max(left, end)
    return False


def _joint_vertical_geometry(scenario):
    from math import isfinite, isclose
    joint = scenario.joint_plan
    if joint is None or len(scenario.placements) != 2:
        raise ValueError("Для совместной работы требуется подтверждённая геометрия двух кранов")
    levels = [p.jib_level_m for p in scenario.placements]
    if any(type(value) not in (int, float) or not isfinite(value) for value in levels):
        raise ValueError("Отсутствуют подтверждённые отметки осей стрел")
    separation = abs(levels[1] - levels[0])
    if (type(joint.vertical_separation_m) not in (int, float)
            or not isfinite(joint.vertical_separation_m) or joint.vertical_separation_m < 0):
        raise ValueError("Разность отметок стрел должна быть конечной и неотрицательной")
    if not isclose(separation, joint.vertical_separation_m, abs_tol=.001, rel_tol=0):
        raise ValueError("Разность отметок осей стрел не соответствует графику совместной работы")
    if (type(joint.jib_structural_height_m) not in (int, float)
            or not isfinite(joint.jib_structural_height_m) or joint.jib_structural_height_m < 0):
        raise ValueError("Конструктивная высота стрелы должна быть конечной и неотрицательной")
    minimum = joint.minimum_vertical_clearance_m
    if type(minimum) not in (int, float) or not isfinite(minimum) or minimum < 1.0:
        raise ValueError("Минимальный вертикальный зазор должен быть конечным и не менее 1 м")
    required = joint.jib_structural_height_m + minimum
    if separation < required and not isclose(separation, required, abs_tol=1e-12, rel_tol=0):
        raise ValueError("Недостаточный вертикальный зазор между стрелами")
    higher = 1 if levels[0] > levels[1] else 2
    if type(joint.higher_crane_index) is not int or joint.higher_crane_index != higher:
        raise ValueError("Верхний кран не соответствует фактическому порядку отметок стрел")
    if type(joint.priority_crane_index) is not int or joint.priority_crane_index not in (1, 2):
        raise ValueError("Неверный приоритет кранов в графике совместной работы")
    return separation, separation - joint.jib_structural_height_m


def build_section_drawing(project, scenario, number, page_size, transform_contract, stage_label=""):
    canvas = _SectionRecorder(page_size)
    font = _font()
    width, height = page_size
    canvas.setFont(font,14); canvas.setFillColor(NAVY)
    stage_suffix=f". {stage_label}" if stage_label else ""
    identity = f"Лист {number}" if str(number).startswith("ГЧ-") else f"Вариант {number}"
    canvas.drawString(22*mm,height-13*mm,f"ВЫСОТНАЯ ПРИВЯЗКА. {identity}{stage_suffix}")
    calibrated = transform_contract.calibrated
    background_rect = background_image = None
    if calibrated:
        background_rect = (transform_contract.left, transform_contract.bottom,
                           transform_contract.shown_width, transform_contract.shown_height)
        background_image = partial(render_page, Path(project.source_section_pdf), 0, project.section_render_scale,
                                   tuple(project.section_crop_box), project.section_background_intensity)
    cv_height=transform_contract.height_point
    section_transform=transform_contract.point
    ox,oy=cv_height(0); px,py=cv_height(project.parapet_m-project.pit_bottom_m)
    building_height=project.parapet_m-project.pit_bottom_m
    building_x=ox+25*mm
    if project.section_building_contour:
        _draw_polygon(canvas,project.section_building_contour,section_transform,colors.HexColor("#0066CC"),colors.HexColor("#EAF3F8"),1.5)
        transformed=[section_transform(point) for point in project.section_building_contour]; building_x=sum(x for x,_ in transformed)/len(transformed)
        min_h=min(point[0] for point in project.section_building_contour); max_h=max(point[0] for point in project.section_building_contour)
        for floor in range(1,project.floors):
            level=building_height*floor/project.floors; x1,y=section_transform((min_h,level)); x2,_=section_transform((max_h,level))
            canvas.setStrokeColor(colors.HexColor("#8EA9C1")); canvas.setLineWidth(.35); canvas.line(x1,y,x2,y)
            if floor%max(1,project.floors//10)==0: canvas.setFont(font,5.5); canvas.setFillColor(colors.HexColor("#5B748A")); canvas.drawString(x2+1*mm,y,f"эт. {floor}")
    else:
        # Без обведённого контура показываем здание отдельной условной
        # вертикалью, не совмещая её с башней второго крана.
        building_x=width*.56
        canvas.setStrokeColor(colors.HexColor("#0066CC")); canvas.setLineWidth(3); canvas.line(building_x,oy,building_x,py)
        canvas.setLineWidth(.5)
        for floor in range(1,max(project.floors,1)):
            _,floor_y=cv_height(building_height*floor/max(project.floors,1))
            canvas.line(building_x-18*mm,floor_y,building_x+18*mm,floor_y)
    canvas.setFont(font,8); canvas.setFillColor(colors.HexColor("#0066CC")); canvas.drawString(building_x+3*mm,py,f"Верх парапета {project.parapet_m:g} м")
    canvas.setFillColor(colors.black); canvas.drawString(building_x+3*mm,oy,f"Низ котлована {project.pit_bottom_m:g} м")
    display_positions={index: ox for index in range(len(scenario.placements))}
    jib_scale=1.0*mm
    if project.section_building_contour:
        building_canvas_x=[section_transform(point)[0] for point in project.section_building_contour]
        min_building_x,max_building_x=min(building_canvas_x),max(building_canvas_x)
        horizontal_scale=abs(section_transform((1.0,0.0))[0]-section_transform((0.0,0.0))[0]) or mm
        for placement_index,placement in enumerate(scenario.placements):
            offset=max(2*mm,distance_to_polygon((placement.x,placement.y),project.site.building)*horizontal_scale)
            display_positions[placement_index]=(min_building_x-offset if placement_index%2==0 else max_building_x+offset)
    elif scenario.joint_plan and len(scenario.placements)>=2:
        higher=scenario.joint_plan.higher_crane_index-1; lower=1-higher
        separation=max(36*mm,min(90*mm,scenario.joint_plan.axis_distance_m*jib_scale))
        display_positions[lower]=ox-separation/2
        display_positions[higher]=ox+separation/2
    schedule_rows=[["Кран / прист.","Отметка","Этаж","Секц.","H крана","Тяга"]]
    for index,placement in enumerate(scenario.placements,1):
        jib_level=placement.jib_level_m if placement.jib_level_m is not None else placement.required_hook_height_m
        _,ty=cv_height(jib_level); color=[colors.HexColor("#004C99"),colors.HexColor("#C05000")][(index-1)%2]
        base_x=display_positions[index-1]
        jib_visual=max(15*mm,min(70*mm,(placement.jib_length_m or placement.max_radius_m)*jib_scale))
        direction=1 if building_x>=base_x else -1
        _draw_tower_crane_elevation(canvas,base_x,oy,ty,jib_visual,color,f"К{index} {placement.model}; L={placement.jib_length_m:.1f}; H={jib_level:.1f}; Hтр≥{placement.required_hook_height_m:.1f} м",direction)
        if placement.max_free_standing_height_m:
            _,free_y=cv_height(placement.max_free_standing_height_m); canvas.setStrokeColor(color); canvas.setDash(3,2); canvas.line(base_x-8*mm,free_y,base_x+8*mm,free_y); canvas.setDash(); canvas.setFont(font,5.5); canvas.setFillColor(color); canvas.drawString(base_x+9*mm,free_y,f"Hсв={placement.max_free_standing_height_m:.1f}")
        for stage_index,level in enumerate(placement.tie_in_levels_m):
            _,tie_y=cv_height(level); target_x=building_x
            intersections=horizontal_intersections(project.section_building_contour,level)
            if intersections:
                targets=[section_transform((value,level))[0] for value in intersections]; target_x=min(targets,key=lambda value:abs(value-base_x))
            canvas.setStrokeColor(colors.HexColor("#7A1FA2")); canvas.setLineWidth(2.0); canvas.line(base_x,tie_y,target_x,tie_y)
            canvas.circle(base_x,tie_y,1.3*mm,stroke=1,fill=0); canvas.circle(target_x,tie_y,1.3*mm,stroke=1,fill=0)
            sections=placement.tie_in_stage_sections[stage_index]; floor=placement.tie_nearest_floors[stage_index]
            canvas.setFont(font,5.7); canvas.setFillColor(colors.HexColor("#7A1FA2")); tie_label=f"П{stage_index+1} +{sections} секц.; {level:.1f} м"
            if target_x>=base_x: canvas.drawString(target_x+2*mm,tie_y+1.5*mm,tie_label)
            else: canvas.drawRightString(target_x-2*mm,tie_y+1.5*mm,tie_label)
            schedule_rows.append([f"К{index}/П{stage_index+1}",f"{level:.1f}",str(floor),str(sections),f"{placement.accepted_crane_height_m:.1f}",f"{project.tie_length_m:.1f}/{placement.required_tie_length_m:.1f}"])
    table_clears_inset = True
    if len(schedule_rows)>1:
        table_widths=[15*mm,13*mm,10*mm,10*mm,15*mm,20*mm]
        table_bottom = canvas.table(schedule_rows,width-sum(table_widths)-9*mm,height-20*mm,table_widths,font,5.2)
        # Small plan inset: pair of ties at the specified angle, directed to the building.
        cx,cy=width-48*mm,72*mm; ray=20*mm; half=radians(project.tie_angle_deg/2)
        table_clears_inset = table_bottom >= cy + max(15 * mm, abs(ray * sin(half))) + 1 * mm
        canvas.setStrokeColor(colors.HexColor("#7A1FA2")); canvas.setLineWidth(1.2); canvas.rect(cx-3*mm,cy-3*mm,6*mm,6*mm)
        for angle in (-half,half): canvas.line(cx,cy,cx+ray*cos(angle),cy+ray*sin(angle))
        canvas.setStrokeColor(colors.HexColor("#0066CC")); canvas.line(cx+ray*cos(half)+3*mm,cy-15*mm,cx+ray*cos(half)+3*mm,cy+15*mm)
        canvas.setFillColor(colors.black); canvas.setFont(font,5.5); canvas.drawCentredString(cx+8*mm,cy-19*mm,f"План: две тяги {project.tie_length_m:.1f} м; угол {project.tie_angle_deg:.0f}°")
    notes = []
    if scenario.joint_plan:
        canvas.setFillColor(RED); canvas.setFont(font,7)
        joint = scenario.joint_plan
        separation, clearance = _joint_vertical_geometry(scenario)
        joint_note = (f"Разность осей стрел {separation:.1f} м = "
                      f"высота конструкции {joint.jib_structural_height_m:.1f} м + свободный зазор {clearance:.1f} м (не менее {joint.minimum_vertical_clearance_m:.1f} м).")
        notes.append((RED, joint_note))
        if len(scenario.placements)>=2:
            higher_index=joint.higher_crane_index-1; lower_index=1-higher_index
            low=scenario.placements[lower_index].jib_level_m; high=scenario.placements[higher_index].jib_level_m
            _,yl=cv_height(low+joint.jib_structural_height_m/2); _,yh=cv_height(high-joint.jib_structural_height_m/2); dim_x=px+88*mm
            canvas.setStrokeColor(RED); canvas.setLineWidth(.7); canvas.line(dim_x,yl,dim_x,yh); canvas.line(dim_x-2*mm,yl,dim_x+2*mm,yl); canvas.line(dim_x-2*mm,yh,dim_x+2*mm,yh)
            canvas.drawString(dim_x+3*mm,(yl+yh)/2,f"чистый зазор {clearance:.1f} м")
    canvas.setFillColor(colors.black); canvas.setFont(font,7)
    note="Привязка выполнена по двум точкам PDF-разреза. Схема пристёжек предварительная; узлы и нагрузки - отдельный проект." if calibrated else "Разрез не откалиброван: показана расчётная схема без привязки к исходному PDF."
    passport_note = "Проверить по паспорту крана и проекту пристёжек"
    notes.extend(((colors.black, note), (colors.black, passport_note)))
    _project_stamp(canvas,project,"Высотная привязка башенного крана",str(number))
    notes_fit = _section_notes(canvas, font, notes)
    _sheet_border(canvas)
    return SectionDrawing(page_size, tuple(canvas.commands), background_rect, background_image, table_clears_inset, notes_fit)


def _section_page(canvas: Canvas, project: ProjectInput, scenario: ScenarioResult, number: int | str,
                  draw_source: bool = True, stage_label: str = "") -> None:
    from .pprk_sheets import section_transform_contract

    transform = section_transform_contract(project, scenario, canvas._pagesize)
    drawing = build_section_drawing(project, scenario, number, canvas._pagesize, transform, stage_label)
    drawing.draw(canvas, draw_source=draw_source)


def _wrapped(canvas, text, x, y, width_chars=55, leading=3.5*mm, max_lines=4):
    words=text.split(); lines=[]; current=""
    for word in words:
        test=(current+" "+word).strip()
        if len(test)>width_chars and current: lines.append(current); current=word
        else: current=test
    if current: lines.append(current)
    for index,line in enumerate(lines[:max_lines]): canvas.drawString(x,y-index*leading,line)


def _canvas_table_object(rows, widths, font, size=6.2, header=True):
    style=ParagraphStyle("CanvasCell",fontName=font,fontSize=size,leading=size+1,alignment=TA_CENTER,textColor=colors.black)
    data=[[Paragraph(str(value),style) for value in row] for row in rows]
    table=Table(data,colWidths=widths,repeatRows=1 if header else 0)
    commands=[("FONTNAME",(0,0),(-1,-1),font),("GRID",(0,0),(-1,-1),.45,colors.black),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]
    if header: commands.append(("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E8E8E8")))
    table.setStyle(TableStyle(commands))
    return table


def _canvas_table_height(rows, widths, font, size=6.2, header=True):
    table=_canvas_table_object(rows,widths,font,size,header)
    _,height=table.wrap(sum(widths),1000*mm)
    return height


def _canvas_table(canvas, rows, x, y_top, widths, font, size=6.2, header=True):
    table=_canvas_table_object(rows,widths,font,size,header)
    _,height=table.wrap(sum(widths),1000*mm); table.drawOn(canvas,x,y_top-height); return height


def _sling_type(name: str) -> tuple[str,str]:
    low=name.lower()
    if "арматур" in low: return "Двухточечная строповка пакета", "Два петлевых стропа или траверса; применять оттяжки."
    if "опалуб" in low: return "Четырёхветвевая схема за штатные точки", "Проверить замки пакета и исключить свободные элементы."
    if "газоблок" in low or "поддон" in low: return "Поддон в сертифицированной таре", "Обязательны ограждение/сетка от выпадения блоков."
    if "бадь" in low or "бетон" in low: return "За штатные цапфы или проушины бадьи", "Затвор закрыт; нахождение под бадьёй запрещено."
    if "фасад" in low: return "Пакет с траверсой и двумя поясами", "Защитить кромки и исключить прогиб элементов."
    if "контейнер" in low or "раствор" in low: return "Четырёхветвевая схема за проушины", "Проверить запорные устройства и отсутствие налипания."
    return "Симметричная четырёхветвевая схема", "Точки зацепки и оснастку подтвердить изготовителем груза."


def _draw_sling_card(canvas, project: ProjectInput, load, x, y, w, h, number):
    font=_font(); canvas.setStrokeColor(colors.black); canvas.setLineWidth(.5); canvas.rect(x,y,w,h)
    canvas.setFont(font,9); canvas.setFillColor(NAVY); canvas.drawString(x+4*mm,y+h-6*mm,f"{number}. {load.name}")
    diagram_cx=x+38*mm; hook_y=y+h-17*mm; load_y=y+18*mm; load_w=min(52*mm,max(30*mm,load.length_m/max(load.length_m,load.width_m)*52*mm))
    canvas.setStrokeColor(colors.black); canvas.setLineWidth(1.2); canvas.circle(diagram_cx,hook_y,2.2*mm,stroke=1,fill=0)
    title,note=_sling_type(load.name); use_spreader=("арматур" in load.name.lower() or "фасад" in load.name.lower())
    if use_spreader:
        canvas.line(diagram_cx,hook_y-2*mm,diagram_cx,hook_y-9*mm); canvas.line(diagram_cx-21*mm,hook_y-9*mm,diagram_cx+21*mm,hook_y-9*mm)
        canvas.line(diagram_cx-18*mm,hook_y-9*mm,diagram_cx-load_w/2+3*mm,load_y+12*mm); canvas.line(diagram_cx+18*mm,hook_y-9*mm,diagram_cx+load_w/2-3*mm,load_y+12*mm)
    else:
        canvas.line(diagram_cx-1*mm,hook_y-2*mm,diagram_cx-load_w/2+3*mm,load_y+12*mm); canvas.line(diagram_cx+1*mm,hook_y-2*mm,diagram_cx+load_w/2-3*mm,load_y+12*mm)
        canvas.line(diagram_cx,hook_y-2*mm,diagram_cx-10*mm,load_y+12*mm); canvas.line(diagram_cx,hook_y-2*mm,diagram_cx+10*mm,load_y+12*mm)
    low=load.name.lower(); canvas.setFillColor(colors.HexColor("#F4F4F4")); canvas.rect(diagram_cx-load_w/2,load_y,load_w,12*mm,stroke=1,fill=1)
    if "газоблок" in low or "поддон" in low or "кирпич" in low:
        canvas.line(diagram_cx-load_w/2,load_y,diagram_cx+load_w/2,load_y+12*mm); canvas.line(diagram_cx+load_w/2,load_y,diagram_cx-load_w/2,load_y+12*mm)
        for offset in (-load_w/4,0,load_w/4): canvas.line(diagram_cx+offset,load_y,diagram_cx+offset,load_y+12*mm)
        canvas.line(diagram_cx-load_w/2,load_y+6*mm,diagram_cx+load_w/2,load_y+6*mm)
    elif "арматур" in low:
        for offset in (-4,-2,0,2,4): canvas.line(diagram_cx-load_w/2+2*mm,load_y+(6+offset/2)*mm,diagram_cx+load_w/2-2*mm,load_y+(6+offset/2)*mm)
    elif "опалуб" in low or "фанер" in low:
        for offset in (-load_w/3,0,load_w/3): canvas.line(diagram_cx+offset,load_y,diagram_cx+offset,load_y+12*mm)
        canvas.line(diagram_cx-load_w/2,load_y,diagram_cx+load_w/2,load_y+12*mm); canvas.line(diagram_cx+load_w/2,load_y,diagram_cx-load_w/2,load_y+12*mm)
    elif "бадь" in low or "бетон" in low:
        canvas.line(diagram_cx-load_w/3,load_y,diagram_cx-load_w/5,load_y-7*mm); canvas.line(diagram_cx+load_w/3,load_y,diagram_cx+load_w/5,load_y-7*mm); canvas.line(diagram_cx-load_w/5,load_y-7*mm,diagram_cx+load_w/5,load_y-7*mm)
    canvas.setFillColor(colors.black); canvas.setFont(font,7)
    canvas.drawCentredString(diagram_cx,load_y+4.5*mm,f"Q={load.total_kg:.0f} кг")
    tx=x+72*mm; canvas.setFont(font,7.5); canvas.setFillColor(NAVY); _wrapped(canvas,title,tx,y+h-18*mm,45,3.7*mm,3)
    canvas.setFillColor(colors.black); canvas.setFont(font,6.5); _wrapped(canvas,note,tx,y+h-34*mm,48,3.3*mm,4)
    _wrapped(canvas,"Марку, количество ветвей, угол, точки зацепки и грузоподъёмность оснастки утвердить отдельной картой строповки.",tx,y+h-51*mm,51,3.1*mm,4)


def _slinging_page(canvas: Canvas, project: ProjectInput, loads, page_number: int, sheet_number: int):
    font=_font(); width,height=landscape(A3); canvas.saveState(); canvas.setFillColor(NAVY); canvas.setFont(font,14)
    canvas.drawString(22*mm,height-14*mm,f"ТИПОВЫЕ СХЕМЫ СТРОПОВКИ. ТАБЛИЦА МАСС ГРУЗОВ. Лист {page_number}")
    positions=[(22*mm,195*mm),(155*mm,195*mm),(22*mm,124*mm),(155*mm,124*mm),(22*mm,53*mm),(155*mm,53*mm)]
    for index,(load,pos) in enumerate(zip(loads,positions),1): _draw_sling_card(canvas,project,load,*pos,128*mm,66*mm,(page_number-1)*6+index)
    table_x=290*mm; canvas.setFillColor(NAVY); canvas.setFont(font,10); canvas.drawString(table_x,257*mm,"ТАБЛИЦА МАСС ГРУЗОВ")
    mass_rows=[["№","Наименование элемента","Элемент, кг","Оснастка, кг","Всего, кг","Схема","Подъёмов"]]
    for index,load in enumerate(loads,1):
        mass_rows.append([str((page_number-1)*6+index),load.name,f"{load.load_kg:g}",f"{load.rigging_kg:g}",f"{load.total_kg:g}",str((page_number-1)*6+index),str(load.lifts)])
    used=_canvas_table(canvas,mass_rows,table_x,253*mm,[7*mm,40*mm,16*mm,16*mm,16*mm,12*mm,14*mm],font,5.8)
    rigging_y=249*mm-used; canvas.setFont(font,10); canvas.setFillColor(NAVY); canvas.drawString(table_x,rigging_y,"ВЕДОМОСТЬ ГРУЗОЗАХВАТНЫХ ПРИСПОСОБЛЕНИЙ")
    rig_rows=[["Тип","Наименование","Кол-во","Подтверждение"]]
    for index,load in enumerate(loads,1):
        title,_=_sling_type(load.name); rig_rows.append([str((page_number-1)*6+index),title,"1 компл.","Паспорт / бирка"])
    _canvas_table(canvas,rig_rows,table_x,rigging_y-4*mm,[10*mm,61*mm,18*mm,32*mm],font,5.8)
    canvas.setFont(font,6.2); canvas.setFillColor(RED); _wrapped(canvas,"Работы выполнять только по утверждённым схемам. Массу груза, марку стропа, число ветвей, угол между ветвями, точки зацепки и грузоподъёмность оснастки подтвердить до подъёма.",290*mm,73*mm,82,3.4*mm,6)
    _sheet_frame(canvas,project,"Схемы строповки. Таблица масс грузов",str(sheet_number)); canvas.restoreState(); canvas.showPage()


def _arrow(canvas,x1,y1,x2,y2):
    from math import atan2,cos,sin,pi
    canvas.line(x1,y1,x2,y2); angle=atan2(y2-y1,x2-x1)
    for delta in (.8,-.8): canvas.line(x2,y2,x2-5*mm*cos(angle+delta),y2-5*mm*sin(angle+delta))


def _logistics_page(canvas: Canvas, project: ProjectInput, sheet_number: int):
    font=_font(); width,height=landscape(A4); canvas.saveState(); canvas.setFont(font,14); canvas.setFillColor(NAVY)
    canvas.drawString(22*mm,height-13*mm,"ТЕХНОЛОГИЧЕСКАЯ СХЕМА: РАЗГРУЗКА - СКЛАД - ПОДАЧА")
    boxes=[("Грузовой автомобиль","Подача по команде"),("Зона разгрузки","Строповка и контрольный подъём 200-300 мм"),("Зона складирования","Устойчивое размещение по видам материалов"),("Точка подачи на здании","Приём груза обученным персоналом")]
    x_positions=[22,87,152,217]
    for (title,note),xm in zip(boxes,x_positions):
        x=xm*mm; y=95*mm; canvas.setFillColor(colors.HexColor("#E7EEF6")); canvas.setStrokeColor(NAVY); canvas.rect(x,y,58*mm,42*mm,stroke=1,fill=1)
        canvas.setFillColor(NAVY); canvas.setFont(font,9); canvas.drawCentredString(x+29*mm,y+32*mm,title)
        canvas.setFillColor(colors.black); canvas.setFont(font,6.5); _wrapped(canvas,note,x+4*mm,y+23*mm,40,3.3*mm,5)
    canvas.setStrokeColor(colors.HexColor("#008040")); canvas.setLineWidth(2)
    for a,b in zip(x_positions,x_positions[1:]): _arrow(canvas,(a+58)*mm,116*mm,b*mm,116*mm)
    notes=["1. Водитель покидает кабину/опасную зону по принятой схеме.","2. Стропальщик проверяет массу, маркировку и исправность тары.","3. После натяжения выполняется пробный подъём на 200-300 мм.","4. Пронос над людьми, бытовыми помещениями и действующими проездами запрещён.","5. Путь груза назначается внутри границ площадки и контролируемой опасной зоны."]
    canvas.setFont(font,8); canvas.setFillColor(colors.black)
    for i,note in enumerate(notes): canvas.drawString(22*mm,(78-i*8)*mm,note)
    _sheet_frame(canvas,project,"Схема разгрузки, складирования и подачи",str(sheet_number)); canvas.restoreState(); canvas.showPage()


def _installation_page(canvas: Canvas, project: ProjectInput, sheet_number: int):
    font=_font(); width,height=landscape(A4); canvas.saveState(); canvas.setFont(font,14); canvas.setFillColor(NAVY)
    canvas.drawString(22*mm,height-13*mm,"ТЕХНОЛОГИЧЕСКАЯ СХЕМА ПОДЪЁМА И МОНТАЖА ЭЛЕМЕНТА")
    steps=[("1","Осмотр груза и оснастки"),("2","Строповка по утверждённой карте"),("3","Пробный подъём 200-300 мм"),("4","Перемещение с оттяжками"),("5","Наведение и временное закрепление"),("6","Расстроповка после устойчивого закрепления")]
    for index,(num,label) in enumerate(steps):
        col=index%3; row=index//3; x=(22+col*89)*mm; y=(118-row*63)*mm
        canvas.setFillColor(colors.HexColor("#F3F6F9")); canvas.setStrokeColor(NAVY); canvas.roundRect(x,y,82*mm,48*mm,3*mm,stroke=1,fill=1)
        canvas.setFillColor(NAVY); canvas.circle(x+10*mm,y+34*mm,6*mm,stroke=1,fill=0); canvas.setFont(font,11); canvas.drawCentredString(x+10*mm,y+31*mm,num)
        canvas.setFont(font,8); _wrapped(canvas,label,x+20*mm,y+37*mm,36,4*mm,4)
        if index<5:
            nx=(22+((index+1)%3)*89)*mm if (index+1)%3 else 0
            if col<2: canvas.setStrokeColor(colors.HexColor("#008040")); _arrow(canvas,x+82*mm,y+24*mm,x+88*mm,y+24*mm)
    canvas.setFont(font,7); canvas.setFillColor(RED); canvas.drawString(22*mm,49*mm,"Запрещается исправлять положение стропов на весу, находиться под грузом и расстроповывать незакреплённый элемент.")
    _sheet_frame(canvas,project,"Последовательность подъёма и монтажа",str(sheet_number)); canvas.restoreState(); canvas.showPage()


def _coordination_page(canvas: Canvas, project: ProjectInput, scenario: ScenarioResult | None, variant_number: int, sheet_number: int):
    font=_font(); width,height=landscape(A3); canvas.saveState(); canvas.setFont(font,14); canvas.setFillColor(NAVY)
    canvas.drawString(22*mm,height-13*mm,f"СХЕМА СОВМЕСТНОЙ РАБОТЫ ДВУХ БАШЕННЫХ КРАНОВ. ВАРИАНТ {variant_number}")
    if scenario is None or len(scenario.placements)<2 or not scenario.joint_plan:
        canvas.setFillColor(colors.black); canvas.setFont(font,11)
        canvas.drawString(25*mm,height-40*mm,"В выбранных вариантах совместная работа двух кранов не применяется.")
        canvas.setFont(font,8); canvas.drawString(25*mm,height-52*mm,"Лист сохранён в составе ППРк как резерв для последующей корректировки.")
        _sheet_frame(canvas,project,"Совместная работа двух кранов",str(sheet_number)); canvas.restoreState(); canvas.showPage(); return
    joint=scenario.joint_plan; placements=scenario.placements[:2]
    draw_left,draw_bottom,draw_w,draw_h=22*mm,48*mm,260*mm,height-68*mm
    xs=[]; ys=[]
    for p in placements:
        radius=p.jib_length_m or p.max_radius_m; xs.extend([p.x-radius,p.x+radius]); ys.extend([p.y-radius,p.y+radius])
    for poly in (project.site.boundary,project.site.building):
        if poly:
            b=polygon_bounds(poly); xs.extend([b[0],b[2]]); ys.extend([b[1],b[3]])
    min_x,max_x=min(xs),max(xs); min_y,max_y=min(ys),max(ys); pad=2.0
    scale=min(draw_w/max(1,max_x-min_x+2*pad),draw_h/max(1,max_y-min_y+2*pad))
    transform=lambda p:(draw_left+(p[0]-min_x+pad)*scale,draw_bottom+(p[1]-min_y+pad)*scale)
    _draw_polygon(canvas,project.site.boundary,transform,colors.black,None,1.1)
    _draw_polygon(canvas,project.site.building,transform,colors.HexColor("#0066CC"),colors.HexColor("#DCE6F1"),1.6)
    if joint.overlap_polygon:
        canvas.saveState()
        if hasattr(canvas,"setFillAlpha"): canvas.setFillAlpha(.3)
        _draw_polygon(canvas,joint.overlap_polygon,transform,RED,colors.HexColor("#F8CECC"),1.2)
        canvas.restoreState()
    crane_colors=[colors.HexColor("#004C99"),colors.HexColor("#C05000")]
    target=transform(polygon_centroid(project.site.building))
    for index,p in enumerate(placements,1):
        center=transform((p.x,p.y)); physical=p.jib_length_m or p.max_radius_m
        edge=transform((p.x+physical,p.y)); radius=abs(edge[0]-center[0]); color=crane_colors[index-1]
        canvas.setStrokeColor(color); canvas.setLineWidth(.9); canvas.setDash(5,3); canvas.circle(*center,radius,stroke=1,fill=0); canvas.setDash()
        tower_edge=transform((p.x+joint.tower_protection_radius_m,p.y)); _draw_tower_protection(canvas,center,abs(tower_edge[0]-center[0]),color)
        _draw_sector_overlay(canvas,center,radius,p,color)
        _draw_tower_crane_plan(canvas,center,target,radius,color,f"К{index}: {p.model}")
    table_x=292*mm; table_y=height-27*mm
    separation, clearance = _joint_vertical_geometry(scenario)
    rows=[["Параметр","Расчётное значение"],["Расстояние между осями",f"{joint.axis_distance_m:.1f} м"],["Рабочий горизонтальный разрыв",f"не менее {joint.working_horizontal_clearance_m:.1f} м"],["Разведение осей стрел",f"{separation:.1f} м = {joint.jib_structural_height_m:.1f} + {clearance:.1f}; зазор ≥{joint.minimum_vertical_clearance_m:.1f} м"],["Стоянка: горизонталь / вертикаль",f"{joint.parking_horizontal_clearance_m:.1f} / 1.0 м"],["Защитный габарит башен",f"{joint.tower_protection_radius_m:.1f} + {joint.tower_protection_radius_m:.1f} = {joint.combined_tower_envelope_m:.1f} м"],["Площадь общей зоны",f"{joint.overlap_area_m2:.1f} м²"],["Приоритет / верхний кран",f"К{joint.priority_crane_index} / К{joint.higher_crane_index}"]]
    for index,p in enumerate(placements,1):
        sector=_sector_text(p.allowed_sector_start_deg,p.allowed_sector_end_deg)
        rows.extend([[f"К{index}: длина стрелы",f"{p.jib_length_m:.1f} м (шаг 5 м)"],[f"К{index}: уровень стрелы",f"{p.jib_level_m:.1f} м"],[f"К{index}: разрешённый сектор",sector],[f"К{index}: точек контура",str(len(p.assigned_contour_points))]])
    table_h=_canvas_table(canvas,rows,table_x,table_y,[54*mm,63*mm],font,7)
    canvas.setFillColor(NAVY); canvas.setFont(font,9); canvas.drawString(table_x,table_y-table_h-8*mm,"ЛОГИКА БЛОКИРОВОК И ОЧЕРЁДНОСТИ")
    canvas.setFillColor(colors.black); canvas.setFont(font,7)
    lower_index=2 if joint.higher_crane_index==1 else 1
    notes=[
        f"К{joint.higher_crane_index} имеет приоритет входа в общую зону; К{lower_index} ожидает вне общей зоны.",
        f"Стрела нижнего К{lower_index} укорочена до расчётной монтажной длины с шагом 5 м.",
        "В общей зоне одновременно допускается только один перемещаемый груз.",
        "Координатная защита блокирует запрещённые секторы и сближение менее 5 м.",
        "После окончания работ стрелы ставятся в назначенные стояночные положения.",
        "Машинисты работают по одному радиоканалу и командам ответственного специалиста.",
    ]
    y=table_y-table_h-15*mm
    for note in notes:
        _wrapped(canvas,"• "+note,table_x,y,72,4*mm,3); y-=9*mm
    canvas.setFillColor(RED); canvas.setFont(font,7)
    _wrapped(canvas,"ПРЕДВАРИТЕЛЬНАЯ СХЕМА. Значения не являются настройкой ограничителей без проверки паспортов, башенных комбинаций, фактической геометрии и наладки координатной защиты.",table_x,58*mm,72,4*mm,4)
    canvas.setFillColor(colors.black); canvas.setFont(font,7)
    canvas.drawString(22*mm,48.5*mm,"Розовая линза — противоколлизионная зона; толстые дуги — разрешённые секторы; красные штриховые дуги — заблокированные направления.")
    _sheet_frame(canvas,project,"Совместная работа. Сектора и противоколлизионная защита",str(sheet_number)); canvas.restoreState(); canvas.showPage()


def _draw_joint_phase_panel(canvas, project: ProjectInput, scenario: ScenarioResult, x, y, w, h, phase: int):
    """Миниатюра стадии, развивающая четырёхкадровую схему из исходного ППРк."""
    joint=scenario.joint_plan; placements=scenario.placements[:2]; colors_by_crane=[colors.HexColor("#004C99"),colors.HexColor("#C05000")]
    canvas.setStrokeColor(colors.black); canvas.setFillColor(colors.white); canvas.setLineWidth(.6); canvas.setDash(); canvas.rect(x,y,w,h,stroke=1,fill=1)
    xs=[]; ys=[]
    for p in placements:
        radius=p.jib_length_m or p.max_radius_m; xs.extend([p.x-radius,p.x+radius]); ys.extend([p.y-radius,p.y+radius])
    if project.site.building:
        b=polygon_bounds(project.site.building); xs.extend([b[0],b[2]]); ys.extend([b[1],b[3]])
    scale=min((w-8*mm)/max(1,max(xs)-min(xs)),(h-18*mm)/max(1,max(ys)-min(ys)))
    min_x,max_x=min(xs),max(xs); min_y,max_y=min(ys),max(ys)
    transform=lambda p:(x+4*mm+(p[0]-min_x)*scale,y+4*mm+(p[1]-min_y)*scale)
    _draw_polygon(canvas,project.site.building,transform,colors.HexColor("#4F81BD"),colors.HexColor("#DCE6F1"),.8)
    if joint and joint.overlap_polygon:
        canvas.saveState(); canvas.setFillColor(colors.HexColor("#F8CECC"));
        if hasattr(canvas,"setFillAlpha"): canvas.setFillAlpha(.25 if phase in (1,4) else .5)
        _draw_polygon(canvas,joint.overlap_polygon,transform,RED,colors.HexColor("#F8CECC"),.6); canvas.restoreState()
    higher=(joint.higher_crane_index-1) if joint else 1; lower=1-higher
    active={1:lower,2:None,3:higher,4:None}[phase]
    for index,p in enumerate(placements):
        center=transform((p.x,p.y)); edge=transform((p.x+(p.jib_length_m or p.max_radius_m),p.y)); radius=abs(edge[0]-center[0]); color=colors_by_crane[index]
        canvas.setStrokeColor(color if active==index else colors.grey); canvas.setLineWidth(2 if active==index else .6); canvas.setDash(3,2); canvas.circle(*center,radius,stroke=1,fill=0); canvas.setDash()
        tower_edge=transform((p.x+joint.tower_protection_radius_m,p.y)); _draw_tower_protection(canvas,center,abs(tower_edge[0]-center[0]),color)
        canvas.setFillColor(color); canvas.setFont(_font(),6); canvas.drawString(center[0]+2*mm,center[1]+2*mm,f"К{index+1}")
    canvas.setFillColor(NAVY); canvas.setFont(_font(),7.5); canvas.drawString(x+3*mm,y+h-6*mm,f"ЭТАП {phase}")
    label=[f"К{lower+1} работает; К{higher+1} ожидает",f"К{lower+1} освобождает общую зону",f"К{higher+1} работает; К{lower+1} заблокирован",f"Передача разрешения К{higher+1} -> К{lower+1}"][phase-1]
    canvas.setFillColor(colors.black); canvas.setFont(_font(),6.2); canvas.drawString(x+18*mm,y+h-6*mm,label)


def _joint_work_schedule_page(canvas: Canvas, project: ProjectInput, scenario: ScenarioResult, variant_number: int, sheet_number: int):
    font=_font(); width,height=landscape(A3); joint=scenario.joint_plan; canvas.saveState(); canvas.setFillColor(NAVY); canvas.setFont(font,14)
    higher=joint.higher_crane_index; lower=2 if higher==1 else 1
    canvas.drawString(22*mm,height-13*mm,f"ГРАФИК СОВМЕСТНОЙ РАБОТЫ К1 И К2. ВАРИАНТ {variant_number}")
    rows=[
        ["Участник / система","Этап 1","Этап 2","Этап 3","Этап 4"],
        [f"Кран К{lower}",f"РАБОТА в секторе К{lower}","ВЫХОД из общей зоны","СТОП / блокировка","ОЖИДАНИЕ разрешения"],
        [f"Кран К{higher}","ОЖИДАНИЕ вне общей зоны","ОЖИДАНИЕ подтверждения","РАБОТА в общей зоне","ВЫХОД из общей зоны"],
        ["Ответственный специалист","Контролирует радиоканал","Подтверждает «зона свободна»",f"Разрешает работу К{higher}",f"Подтверждает и разрешает К{lower}"],
        ["Координатная защита",f"Сектор К{lower} открыт","Оба входа заблокированы",f"Сектор К{higher} открыт","Оба входа заблокированы"],
    ]
    style=ParagraphStyle("ScheduleCell",fontName=font,fontSize=6.7,leading=8,alignment=TA_CENTER)
    data=[[Paragraph(str(value),style) for value in row] for row in rows]
    table=Table(data,colWidths=[55*mm,80*mm,80*mm,80*mm,80*mm],rowHeights=[10*mm,14*mm,14*mm,17*mm,14*mm])
    table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.55,colors.black),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#D9EAF7")),("BACKGROUND",(1,1),(1,1),colors.HexColor("#D9EAD3")),("BACKGROUND",(3,2),(3,2),colors.HexColor("#FCE5CD")),("BACKGROUND",(2,4),(2,4),colors.HexColor("#F4CCCC")),("BACKGROUND",(4,4),(4,4),colors.HexColor("#F4CCCC"))]))
    table.wrapOn(canvas,375*mm,80*mm); table.drawOn(canvas,22*mm,height-92*mm)
    canvas.setFillColor(colors.black); canvas.setFont(font,7); canvas.drawString(22*mm,height-97*mm,"t0");
    for index,label in enumerate(("t1: команда на выход","t2: зона свободна",f"t3: К{higher} закончил","t4: новый цикл"),1): canvas.drawString((75+80*(index-1))*mm,height-97*mm,label)
    panel_y=87*mm; panel_w=91*mm; panel_h=93*mm
    for phase in range(1,5): _draw_joint_phase_panel(canvas,project,scenario,(22+(phase-1)*94)*mm,panel_y,panel_w,panel_h,phase)
    canvas.setFillColor(colors.black); canvas.setFont(font,7)
    separation, clearance = _joint_vertical_geometry(scenario)
    notes=[
        f"Высотное разделение: оси стрел {separation:.1f} м = конструктивная высота стрелы {joint.jib_structural_height_m:.1f} м + чистый зазор {clearance:.1f} м (не менее {joint.minimum_vertical_clearance_m:.1f} м).",
        f"У каждой башни показан защитный габарит {joint.tower_protection_radius_m:.1f} м от оси; суммарно для пары 2+2 = {joint.combined_tower_envelope_m:.1f} м.",
        "Переход между этапами выполняется только после голосового подтверждения ответственного специалиста; время этапов определяется фактическим производственным циклом.",
        "График сформирован по принципу четырёх последовательных схем совместной работы из загруженного ППРк; уставки уточняются при наладке координатной защиты.",
    ]
    for index,note in enumerate(notes): canvas.drawString(22*mm,(76-index*6)*mm,"• "+note)
    canvas.setFillColor(RED); canvas.drawString(22*mm,50*mm,"Одновременное нахождение двух перемещаемых грузов в общей зоне запрещено.")
    _sheet_frame(canvas,project,"График совместной работы К1 и К2",str(sheet_number)); canvas.restoreState(); canvas.showPage()


def _restamp_page_numbers(path: Path) -> None:
    """После отбора и перестановки листов поставить фактические Лист/Листов."""
    from pypdf import PdfReader, PdfWriter
    reader=PdfReader(str(path)); total=len(reader.pages); writer=PdfWriter(); font=_font()
    for number,page in enumerate(reader.pages,1):
        width,height=float(page.mediabox.width),float(page.mediabox.height); packet=io.BytesIO(); overlay=Canvas(packet,pagesize=(width,height))
        x=width-190*mm; y=5*mm; overlay.setFillColor(colors.white)
        overlay.rect(x+135.5*mm,y+24.5*mm,29*mm,7*mm,stroke=0,fill=1); overlay.rect(x+165.5*mm,y+24.5*mm,19*mm,7*mm,stroke=0,fill=1)
        overlay.setFillColor(colors.black); overlay.setFont(font,8)
        overlay.drawCentredString(x+150*mm,y+26.5*mm,str(number)); overlay.drawCentredString(x+175*mm,y+26.5*mm,str(total))
        overlay.save(); packet.seek(0); writer.add_page(page); writer.pages[-1].merge_page(PdfReader(packet).pages[0])
    temporary=path.with_suffix(".restamped.pdf")
    with temporary.open("wb") as stream: writer.write(stream)
    temporary.replace(path)


def _apply_document_status(path: Path, text: str, *, reference_page_start: int | None = None) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(path))
    writer = PdfWriter()
    font = _font()
    for page_number, page in enumerate(reader.pages, 1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        packet = io.BytesIO()
        overlay = Canvas(packet, pagesize=(width, height))
        if reference_page_start is not None and page_number >= reference_page_start:
            from .pprk_text_report import _draw_cell_text
            # Reserve the right footer for the physical page number. Reference
            # images start above 18 mm; this bounded status cell ends at 13 mm.
            _draw_cell_text(overlay, text, 20 * mm, 5 * mm, width - 75 * mm, 8 * mm,
                            font_size=10, placeholder=True)
            overlay.save()
            packet.seek(0)
            writer.add_page(page)
            writer.pages[-1].merge_page(PdfReader(packet).pages[0])
            continue
        overlay.saveState()
        try:
            overlay.setFillAlpha(0.2)
        except AttributeError:
            pass
        overlay.setFillColor(RED)
        overlay.setFont(font, min(23, max(12, width / 45)))
        overlay.translate(width / 2, height / 2)
        overlay.rotate(32)
        overlay.drawCentredString(0, 0, text)
        overlay.restoreState()
        overlay.save()
        packet.seek(0)
        writer.add_page(page)
        writer.pages[-1].merge_page(PdfReader(packet).pages[0])
    temporary = path.with_suffix(".status.pdf")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(path)


def _render_bundle_report(path, project, scenarios, selected_pages, document_status, bundle, external_page_overrides=None):
    from dataclasses import replace
    from .pprk_assets import load_asset_manifest
    from .pprk_appendices import draw_asset_appendix, expand_bundle_appendices, plan_asset_appendices
    from .pprk_text_report import render_pprk_text_report
    from .pprk_sheets import (
        CalculatedSheetRenderContext,
        bind_calculated_scenario,
        calculated_sheet_page_map,
        draw_calculated_sheet,
        expand_bundle_graphical_parts,
        plan_calculated_sheets,
    )

    if selected_pages is not None:
        raise ValueError("Состав и порядок bundle-ППРк фиксированы; выбор отдельных листов недопустим")
    has_graphics = any(part.kind == "graphical" for part in bundle.parts)
    if has_graphics:
        if not scenarios:
            raise ValueError("Для расчётных графических листов отсутствует сценарий")
        scenario = bind_calculated_scenario(bundle, scenarios)
        plans = plan_calculated_sheets(bundle, project, scenario)
        rendered_bundle = expand_bundle_graphical_parts(bundle, plans)
    else:
        scenario = None
        plans = ()
        rendered_bundle = bundle
    assets = load_asset_manifest()
    appendices = plan_asset_appendices(rendered_bundle, assets)
    rendered_bundle = expand_bundle_appendices(rendered_bundle, appendices)
    appendix_blockers = [issue for issue in rendered_bundle.completeness_issues
                         if issue.code == "PPRK_APPENDIX_REQUIRED" and issue.blocking]
    if appendix_blockers:
        raise ValueError("Приложения ППРк требуют предварительной редакции: " + "; ".join(issue.message for issue in appendix_blockers))
    if external_page_overrides is not None:
        # Final assembly replaces page 4 with paginated physical contents.
        # Keep this provisional leaf independent of the original entry count.
        rendered_bundle = replace(rendered_bundle, contents=())
    omitted_appendices = {
        part.part_id: "НЕ ПРИМЕНИМО: нет активных грузов"
        for part in bundle.parts
        if part.part_id == "appendix.SLINGING_CARDS" and bundle.active_loads == ()
    }
    render_pprk_text_report(path, rendered_bundle, author=project.author or "", page_overrides=None if plans else {**omitted_appendices, **(external_page_overrides or {})})
    if plans or appendices:
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        text_page_count = len(PdfReader(str(path)).pages)
        designation_by_id = {plan.sheet_id: plan.designation for plan in plans}
        for plan in plans:
            designation_by_id.setdefault(plan.source_sheet_id, plan.designation)
        for _ in range(4):
            page_map = calculated_sheet_page_map(plans, text_page_count + 1)
            overrides = {**omitted_appendices, **(external_page_overrides or {}), **{
                sheet_id: f"{designation_by_id[sheet_id]} / стр. {page}"
                for sheet_id, page in page_map.items()
                if sheet_id in designation_by_id
            }}
            for index, appendix in enumerate(appendices, text_page_count + len(plans) + 1):
                overrides[appendix.sheet_id] = f"стр. {index}"
                overrides.setdefault(appendix.source_sheet_id, f"стр. {index}")
            render_pprk_text_report(
                path,
                rendered_bundle,
                author=project.author or "",
                page_overrides=overrides,
            )
            updated_count = len(PdfReader(str(path)).pages)
            if updated_count == text_page_count:
                break
            text_page_count = updated_count
        else:
            raise ValueError("Карта страниц ППРк не стабилизировалась")
        text_pages = PdfReader(str(path)).pages
        for page in text_pages:
            writer.add_page(page)
        if any(page_map[plan.sheet_id] != len(text_pages) + index for index, plan in enumerate(plans, 1)):
            raise ValueError("Нарушена карта физических графических листов")
        binding = bundle.calculation_binding
        render_context = CalculatedSheetRenderContext(
            project,
            scenario,
            verified_danger_zone_offset_m=(binding.verified_danger_zone_offset_m if binding else None),
            require_verified_danger_zone=bool(binding and binding.scenario_render_sha256),
            scenario_index=binding.scenario_index if binding else 0,
            protocol_run_id=binding.protocol_run_id if binding else "",
            protocol_result_sha256=binding.protocol_result_sha256 if binding else "",
        )
        for plan in plans:
            packet = io.BytesIO()
            sheet_canvas = Canvas(packet, pagesize=plan.sheet_format.page_size)
            draw_calculated_sheet(sheet_canvas, plan, render_context)
            sheet_canvas.save()
            packet.seek(0)
            generated = PdfReader(packet)
            if len(generated.pages) != 1:
                raise ValueError(f"Лист {plan.sheet_id} должен формировать ровно одну страницу")
            writer.add_page(generated.pages[0])
        for index, appendix in enumerate(appendices, len(text_pages) + len(plans) + 1):
            packet = io.BytesIO()
            appendix_canvas = Canvas(packet)
            draw_asset_appendix(appendix_canvas, replace(appendix, page_number=index), assets)
            appendix_canvas.save()
            packet.seek(0)
            generated = PdfReader(packet)
            if len(generated.pages) != 1:
                raise ValueError(f"Приложение {appendix.sheet_id} должно формировать ровно одну страницу")
            writer.add_page(generated.pages[0])
        temporary = path.with_suffix(".calculated.tmp.pdf")
        with temporary.open("wb") as stream:
            writer.write(stream)
        temporary.replace(path)
    if document_status:
        _apply_document_status(path, document_status, reference_page_start=(len(text_pages) + len(plans) + 1) if appendices else None)
    return path



def generate_report(
    path: str | Path,
    project: ProjectInput,
    scenarios: list[ScenarioResult],
    selected_pages: list[int] | None = None,
    *,
    document_status: str | None = None,
    bundle: "PPRKBundle | None" = None,
) -> Path:
    """Publish only a scanned PDF; preserve legacy API and prior destinations."""
    from tempfile import TemporaryDirectory
    from .pprk_release_validation import validate_release_inputs, validate_release_pdf, snapshot_underlays
    validate_release_inputs(project, scenarios, bundle)
    checked_scenarios = scenarios
    if bundle is not None:
        from .pprk_sheets import bind_calculated_scenario
        checked_scenarios = ([bind_calculated_scenario(bundle, scenarios)]
                             if any(part.kind == "graphical" for part in bundle.parts) else [])
    for scenario in checked_scenarios:
        if scenario.joint_plan is not None:
            _joint_vertical_geometry(scenario)
    from .pprk_merge import _aliases
    output = Path(path)
    for source in (project.source_plan_pdf, project.source_section_pdf):
        if source and _aliases(Path(source), output):
            raise ValueError("Выходной PDF совпадает с исходной подложкой")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Use the local temp root to avoid deep GUI-report paths on Windows. Neither
    # planning nor raster/vector rendering may reopen the mutable source paths.
    with TemporaryDirectory(prefix=".pprk-underlays-") as snapshots:
        rendering_project = snapshot_underlays(project, snapshots)
        if bundle is not None:
            return _generate_report(output, rendering_project, scenarios, selected_pages,
                                    document_status=document_status, bundle=bundle)
        with TemporaryDirectory(dir=output.parent, prefix=".pprk-legacy-") as directory:
            staged = Path(directory) / "report.pdf"
            _generate_report(staged, rendering_project, scenarios, selected_pages, document_status=document_status)
            validate_release_pdf(staged)
            staged.replace(output)
    return output


def _generate_report(
    path: str | Path,
    project: ProjectInput,
    scenarios: list[ScenarioResult],
    selected_pages: list[int] | None = None,
    *,
    document_status: str | None = None,
    bundle: "PPRKBundle | None" = None,
) -> Path:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if bundle is not None:
        from .pprk_composer import effective_render_project
        from .pprk_release_validation import validate_release_inputs
        validate_release_inputs(project, bundle, scenarios)
        project = effective_render_project(bundle, project)
        from .pprk_merge import PPRKMergeError, assemble_pprk_report, external_document_issues
        from .pprk_models import CompletenessIssue, ReleaseStatus
        if bundle.requested_status in (ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION):
            blockers = [i for i in bundle.completeness_issues if i.blocking]
            if bundle.effective_status != bundle.requested_status or blockers:
                raise PPRKMergeError(blockers or (CompletenessIssue("PPRK_STATUS_BLOCKED", "Запрошенный статус недоступен"),))
        external_blockers = tuple(
            issue for issue in external_document_issues(bundle) if issue.blocking
        )
        if bundle.requested_status == ReleaseStatus.PRODUCTION and external_blockers:
            raise PPRKMergeError(external_blockers)
        assemble_pprk_report(
            path, project, bundle,
            lambda main, prepared, overrides: _render_bundle_report(
                main, project, scenarios, selected_pages, document_status, prepared, overrides,
            ),
            document_status=document_status,
        )
        return path
    font=_font(); styles=getSampleStyleSheet()
    for style in styles.byName.values(): style.fontName=font
    title=ParagraphStyle("PPRKTitle",parent=styles["Title"],fontName=font,fontSize=17,leading=21,textColor=colors.black,alignment=TA_CENTER,spaceAfter=8*mm)
    h1=ParagraphStyle("PPRKH1",parent=styles["Heading1"],fontName=font,fontSize=13,leading=16,textColor=colors.black,spaceBefore=2*mm,spaceAfter=4*mm)
    h2=ParagraphStyle("PPRKH2",parent=styles["Heading2"],fontName=font,fontSize=10,leading=13,textColor=colors.black,spaceBefore=3*mm,spaceAfter=1.5*mm)
    body=ParagraphStyle("PPRKBody",parent=styles["Normal"],fontName=font,fontSize=8.5,leading=12,alignment=TA_JUSTIFY,spaceAfter=2*mm)
    small=ParagraphStyle("PPRKSmall",parent=body,fontSize=7.5,leading=10,alignment=TA_LEFT)
    blank="____________________________"; author=project.author.strip() or blank; email=project.email.strip() or blank
    story=[Spacer(1,12*mm),Paragraph("ПРОЕКТ ПРОИЗВОДСТВА РАБОТ КРАНАМИ",title),
        Paragraph("предварительная автоматизированная редакция",ParagraphStyle("Sub",parent=body,alignment=TA_CENTER,fontSize=10)),Spacer(1,8*mm),
        _table([["Объект",project.name or blank],["Местонахождение",project.city or blank],["Организация",project.organization or blank],["Шифр / стадия",f"{project.project_code or blank} / {project.project_stage or 'ППРк'}"],["Разработчик ППРк",author],["Проверил",project.checked_by or blank],["Утвердил",project.approved_by or blank],["Контактный e-mail",email],["Год",str(project.year)]],font,[48*mm,122*mm],9,False),
        Spacer(1,20*mm),_table([["Разработал","________________","____________","__________"],["Проверил","________________","____________","__________"],["Утвердил","________________","____________","__________"]],font,[35*mm,55*mm,40*mm,40*mm],8,False),
        Spacer(1,12*mm),Paragraph("Подписи, должности, организация, шифр проекта и согласования заполняются разработчиком до выпуска документа в производство.",small),PageBreak()]
    sheets=[("Пояснительная записка","Исходные данные, технология, организация и безопасность"),("Сравнение вариантов","До трёх вариантов размещения"),("Стройгенплан","Эскиз поверх исходного PDF-плана"),("Листы СОЗР","Точки ограничения, условные и постоянные вырезы по каждому крану"),("Высотная привязка","Требуемая высота крюка и отметки"),("Грузовая ведомость","Массы, габариты, оснастка и количество подъёмов"),("Схемы строповки","Типовые схемы для каждого груза"),("Опасные зоны","Границы работы и перемещения грузов"),("Разгрузка, складирование и подача","Технологическая схема материального потока"),("Подъём и монтаж элемента","Последовательность безопасной операции"),("Совместная работа кранов","Зоны и организационные ограничения"),("Требования охраны труда и промышленной безопасности","Обязательные организационные меры"),("Контрольные листы","Проверка исходных данных и готовности"),("Лист регистрации изменений","Заполняется при корректировках")]
    story += [Paragraph("ВЕДОМОСТЬ СОСТАВА ППРк",h1),_table([["№","Наименование","Содержание"]]+[[str(i),a,b] for i,(a,b) in enumerate(sheets,1)],font,[10*mm,65*mm,95*mm]),PageBreak()]
    story += [Paragraph("1. ОБЩИЕ ДАННЫЕ И ОБЛАСТЬ ПРИМЕНЕНИЯ",h1),Paragraph(f"ППРк разработан для объекта «{project.name or 'наименование не заполнено'}» в городе {project.city or 'не указан'}. Несущая система - монолитный железобетон; перегородки - газобетонные блоки; наружная облицовка - вентилируемый фасад.",body),Paragraph("Документ определяет предварительное размещение башенных кранов, проверку охвата, грузовысотных параметров, опасных зон и организацию типовых подъёмов. Расчёт фундамента крана, монтаж и демонтаж крана, проект пристёжек, фасадные люльки и специальные подъёмы разрабатываются отдельно.",body),Paragraph("Исходные документы",h2),_table([["Документ","Статус"],["Векторный PDF-план",Path(project.source_plan_pdf).name if project.source_plan_pdf else "Не приложен"],["PDF-разрез",Path(project.source_section_pdf).name if project.source_section_pdf else "Не приложен"],["Паспорт конкретного крана","Подлежит приложению перед утверждением"],["ПОС / календарный график","Подлежит сверке"],["Геология и решение по основанию","Отдельный расчёт"]],font,[75*mm,95*mm]),Paragraph("Высотные исходные данные",h2),Paragraph(f"Отметка низа котлована: {project.pit_bottom_m:g} м. Отметка верха парапета: {project.parapet_m:g} м. Расчётная высота: {project.parapet_m-project.pit_bottom_m:g} м. Этажей: {project.floors}. Пристёжки: {'допускаются' if project.tie_ins_possible else 'не допускаются'}. Принятая длина парных тяг: {project.tie_length_m:g} м, угол между ними: {project.tie_angle_deg:g}°.",body),Paragraph("Схема пристёжек является предварительной компоновкой. Расчёт тяг, закладных деталей, соединений, нагрузок на башню крана и несущие конструкции здания выполняется отдельным проектом пристёжек по паспорту фактически установленного крана.",body),PageBreak()]
    story += [Paragraph("2. СРАВНЕНИЕ ВАРИАНТОВ И ПРИНЯТОЕ РЕШЕНИЕ",h1)]
    rows=[["№","Статус","Краны","Модели","Срок, кал. дн.","Стоимость, руб.","Условия / ограничения"]]
    for index,s in enumerate(scenarios,1): rows.append([str(index),s.status,str(len(s.placements)),", ".join(p.model for p in s.placements) or "-",f"{s.calendar_days:.2f}" if s.calendar_days is not None else "-",f"{s.estimated_cost:,.0f}" if s.estimated_cost is not None else "не рассчитана","; ".join(s.warnings+s.reasons) or "Нет"])
    story += [_table(rows,font,[8*mm,20*mm,11*mm,29*mm,19*mm,23*mm,60*mm],6.6),Spacer(1,4*mm),Paragraph(f"Режим: {project.hours_per_day:g} ч/сут; коэффициент использования: {project.utilization:g}; приоритет - {'стоимость/минимум кранов' if project.priority=='cost' else 'скорость'}. Стоимость {'рассчитана по введённой суточной ставке' if project.commercial_offer_present else 'не рассчитывается: коммерческое предложение не введено'}.",body)]
    balance_rows=[["Вар.","Активных подъёмов","Учтено","Загрузка кранов, ч"]]
    for index,s in enumerate(scenarios,1): balance_rows.append([str(index),str(s.total_active_lifts),str(s.accounted_lifts),", ".join(f"К{i+1}: {hours:.1f}" for i,hours in enumerate(s.crane_work_hours)) or "-"])
    story += [Spacer(1,3*mm),Paragraph("Баланс подъёмов",h2),_table(balance_rows,font,[15*mm,42*mm,30*mm,80*mm],7)]
    for i,s in enumerate(scenarios,1):
        story.append(Paragraph(f"Вариант {i}",h2))
        for j,p in enumerate(s.placements,1):
            sector=(f"; разрешённый сектор {_sector_text(p.allowed_sector_start_deg,p.allowed_sector_end_deg)}" if p.allowed_sector_start_deg is not None else "")
            story.append(Paragraph(f"К{j} {p.model}: X={p.x:.1f} м, Y={p.y:.1f} м; рабочий вылет {p.max_radius_m:.1f} м; длина стрелы {(p.jib_length_m or p.max_radius_m):.1f} м; требуемая высота крюка {p.required_hook_height_m:.1f} м; предварительный уровень стрелы {(p.jib_level_m or p.required_hook_height_m):.1f} м{sector}.",body))
        if s.joint_plan:
            jp=s.joint_plan
            story.append(Paragraph(f"Совместная работа: расстояние между осями {jp.axis_distance_m:.1f} м; площадь пересечения рабочих окружностей {jp.overlap_area_m2:.1f} м²; рабочий горизонтальный разрыв не менее {jp.working_horizontal_clearance_m:.1f} м; защитный габарит каждой башни {jp.tower_protection_radius_m:.1f} м от оси (для пары {jp.combined_tower_envelope_m:.1f} м); разведение осей стрел {jp.vertical_separation_m:.1f} м, включая конструктивную высоту стрелы {jp.jib_structural_height_m:.1f} м и чистый зазор 1.0 м; приоритет К{jp.priority_crane_index}.",body))
        if s.selection_audit:
            story.append(Paragraph("Журнал подбора моделей",h2))
            for line in s.selection_audit: story.append(Paragraph("• "+line,small))
        route_notes=build_route_explanation(SimpleNamespace(routes=s.routes,route_failures=s.route_failures,warning_acceptances=project.warning_acceptances))
        if route_notes:
            story.append(Paragraph("Маршруты подачи и принятые предупреждения",h2))
            for line in route_notes: story.append(Paragraph("• "+line,small))
    story.append(Paragraph("Алгоритм выбора положения крана",h2))
    algorithm_steps=[
        "Граница площадки покрывается регулярной сеткой с шагом 2 м. Каждая узловая точка рассматривается как возможная ось вращения крана.",
        "Исключаются точки вне площадки, внутри здания, в запретных зонах и за пределами введённого диапазона расстояний от здания.",
        "Контур здания дискретизируется контрольными точками с шагом не более 5 м. Вариант с одним краном допускается только при покрытии всех точек подачи грузов и всего контура здания.",
        "Для каждой точки подачи проверяется назначенный пользователем груз: вылет, паспортная грузоподъёмность Q(R), требуемая высота крюка Hкр = Hточки + 2,3 + Hгруза + 1,5 и опасная зона. Активные грузы без отдельной точки консервативно проверяются на всех нанесённых точках подачи и полностью учитываются в балансе подъёмов.",
        "Если один кран не покрывает весь контур, перебираются пары допустимых позиций. Пара принимается, когда объединение зон двух кранов покрывает весь контур и все точки подачи, а расстояние между осями не менее 5 м.",
        "Для принятой пары точки контура и подачи распределяются между кранами по минимальному вылету. По азимутам назначенных точек определяется минимальный разрешённый сектор поворота с технологическим запасом 10°.",
        "Для каждого крана подбирается минимальная монтажная длина стрелы с шагом 5 м, покрывающая его точки, контур и логистические зоны. Общая противоколлизионная зона строится по этим фактическим длинам.",
        "Нижним назначается кран, стрела которого заканчивается до защитного коридора соседней башни: расстояние между осями минус 5 м рабочего зазора и 2 м габарита башни. Верхний кран назначается приоритетным; оси стрел разводятся на 3 м.",
        "Рабочий цикл разделён на четыре стадии: работа нижнего крана, освобождение общей зоны, работа приоритетного верхнего крана и передача разрешения обратно нижнему.",
        "Допустимые варианты ранжируются по числу кранов, календарной продолжительности, рабочему вылету и приоритету модели. При приоритете цены штраф за второй кран существенно выше; при приоритете скорости допускается преимущество параллельной работы.",
    ]
    for step_index,item in enumerate(algorithm_steps,1): story.append(Paragraph(f"{step_index}. {item}",small))
    story.append(PageBreak())
    story += [Paragraph("3. ХАРАКТЕРИСТИКИ КРАНОВ И ВЫСОТНАЯ ПРИВЯЗКА",h1)]
    crane_rows=[["Вар.","Кран","Модель","X, м","Y, м","R, м","L стрелы, м","H крюка, м","H стрелы, м","Сектор"]]
    for i,s in enumerate(scenarios,1):
        for j,p in enumerate(s.placements,1):
            sector=_sector_text(p.allowed_sector_start_deg,p.allowed_sector_end_deg,0) if p.allowed_sector_start_deg is not None else "—"
            crane_rows.append([str(i),f"К{j}",p.model,f"{p.x:.1f}",f"{p.y:.1f}",f"{p.max_radius_m:.1f}",f"{p.jib_length_m:.1f}",f"{p.required_hook_height_m:.1f}",f"{(p.jib_level_m or p.required_hook_height_m):.1f}",sector])
    story += [_table(crane_rows,font,[8*mm,9*mm,27*mm,13*mm,13*mm,13*mm,18*mm,20*mm,25*mm,25*mm],7),Spacer(1,4*mm),Paragraph("Требуемая высота крюка определяется по отметке точки подачи груза на здание, высоте груза, высоте строповки и безопасному зазору. Окончательная башенная комбинация, балласт, анкеровка и уровни пристёжек принимаются только по паспорту и руководству изготовителя конкретного крана.",body),Paragraph("Высотная схема на загруженном разрезе проверяется ответственным специалистом. Автоматическая численная привязка не заменяет проект пристёжек и расчёт башенной системы.",body),PageBreak()]
    story += [Paragraph("4. ГРУЗОВАЯ ВЕДОМОСТЬ И ТИПОВЫЕ ПОДЪЁМЫ",h1)]
    load_rows=[["№","Груз","Груз, кг","Оснастка, кг","Итого, кг","Габарит Д×Ш×В, м","Подъёмов"]]
    active_loads=[load for load in project.loads if load.active]
    for i,load in enumerate(active_loads,1): load_rows.append([str(i),load.name,f"{load.load_kg:g}",f"{load.rigging_kg:g}",f"{load.total_kg:g}",f"{load.length_m:g}×{load.width_m:g}×{load.height_m:g}",str(load.lifts)])
    story += [_table(load_rows,font,[8*mm,45*mm,23*mm,23*mm,23*mm,34*mm,18*mm],7.5),Spacer(1,3*mm),Paragraph("Перед производством работ массы и габариты сверяются с паспортами, накладными и фактической оснасткой. Для груза, отсутствующего в ведомости, разрабатывается и утверждается отдельная схема строповки; подъём неизвестного по массе груза запрещается.",body),PageBreak()]
    joint_details=[]
    for i,s in enumerate(scenarios,1):
        if s.joint_plan:
            jp=s.joint_plan; joint_details.append(f"Для варианта {i}: оси {jp.axis_distance_m:.1f} м; общая зона {jp.overlap_area_m2:.1f} м²; К{jp.priority_crane_index} имеет приоритет; одновременно в общей зоне допускается один груз.")
    sections=[
        ("5. ПОДГОТОВИТЕЛЬНЫЕ МЕРОПРИЯТИЯ",[
            "Оформить разрешительную документацию и назначить ответственных специалистов.",
            "Проверить основание, пути, заземление, ограждения, освещение, связь и знаки безопасности.",
            "Сверить фактические препятствия, ЛЭП, действующие кабели, деревья, охранные зоны, проезды и соседние здания с планом; до начала работ выполнить предусмотренный проектом вынос или защиту коммуникаций.",
            "Обеспечить монтажную площадку и подъезд; монтаж и демонтаж выполнять по отдельному проекту.",
        ]),
        ("6. ОРГАНИЗАЦИЯ РАЗГРУЗКИ, СКЛАДИРОВАНИЯ И ПОДАЧИ",[
            "Автотранспорт принимается в выделенной зоне разгрузки по команде ответственного лица; работа крана над кабиной запрещается.",
            "После строповки люди покидают кузов и опасную зону; выполняется контрольный подъём на 200-300 мм.",
            "Материал передаётся на обозначенную площадку складирования, затем - к точке подачи груза на здание.",
            "Арматура, опалубка и иные материалы складируются устойчиво по типу, с прокладками и проходами; высота штабеля подтверждается технологической картой.",
            "Проходы, проезды, пожарные подъезды и доступ к инженерным сетям не загромождаются.",
        ]),
        ("7. ОПАСНЫЕ ЗОНЫ И ОГРАНИЧЕНИЯ",[
            "Опасная зона определяется от крайнего положения груза с учётом его максимального габарита и нормативного расстояния возможного отлёта.",
            "Груз не должен проноситься за границей строительной площадки. Выход расчётной зоны требует отдельного решения и повторной проверки.",
            "При допустимости защитных ограждений на монтажном горизонте их конструкция оформляется отдельным техническим решением.",
            "Ограничители поворота и вылета настраиваются по утверждённому стройгенплану и проверяются перед работой.",
            "Места стоянки автотранспорта и складирования назначаются за пределами путей движения противовеса и контролируемой зоны, если паспортом или ППРк не установлено иное.",
        ]),
        ("8. СОВМЕСТНАЯ РАБОТА КРАНОВ",[
            "При применении двух кранов назначается единый порядок взаимодействия и приоритет операций.",
            "В рабочем режиме выдерживается горизонтальный разрыв не менее 5 м между кранами, стрелами, перемещаемыми грузами и конструкциями. Для графического защитного габарита принято по 2 м от оси каждой башни, суммарно 2+2=4 м.",
            "Оси стрел разводятся не менее чем на 3 м: конструктивная высота стрелы 2 м плюс чистый вертикальный зазор 1 м.",
            "На стоянке принимаются разрывы не менее 2 м по горизонтали и 1 м по вертикали.",
            "Координатная защита блокирует запрещённые секторы и одновременный вход двух грузов в общую зону; машинисты используют единый радиоканал.",
            "График содержит четыре стадии: работа нижнего крана, освобождение общей зоны, работа приоритетного верхнего крана и передача разрешения обратно нижнему.",
        ]+joint_details),
        ("9. ОХРАНА ТРУДА И ПРОМЫШЛЕННАЯ БЕЗОПАСНОСТЬ",[
            "К работе допускается аттестованный и проинструктированный персонал.",
            "Применяются только исправные и освидетельствованные грузозахватные приспособления с маркировкой.",
            "Запрещаются подъём людей, подтаскивание груза, освобождение защемлённых стропов краном, нахождение людей под грузом и работа при неисправных приборах безопасности.",
            "Работа прекращается при ветре выше паспортного значения, грозе, тумане, снегопаде или недостаточной видимости.",
            "Должны быть определены сигналы, радиоканал, аварийная остановка и порядок действий при штормовом предупреждении.",
        ]),
    ]
    for heading,bullets in sections:
        story.append(Paragraph(heading,h1))
        for item in bullets: story.append(Paragraph("• "+item,body))
        story.append(Spacer(1,2*mm))
    story.append(PageBreak())
    checklist=["Исходный план и масштаб проверены","Границы площадки и здания подтверждены","Запретные и охранные зоны нанесены","Точки подачи грузов и монтажные горизонты подтверждены","Массы, габариты и оснастка подтверждены","Паспортная грузовая характеристика сверена","Основание и фундамент крана рассчитаны","Монтаж/демонтаж разработаны отдельным проектом","Ограничители и опасные зоны назначены","Персонал, связь, знаки и ограждения обеспечены"]
    story += [Paragraph("10. КОНТРОЛЬНЫЙ ЛИСТ ГОТОВНОСТИ",h1),_table([["№","Проверка","Отметка","Ответственный / дата"]]+[[str(i),x,"□","________________"] for i,x in enumerate(checklist,1)],font,[10*mm,100*mm,18*mm,42*mm],8),PageBreak(),Paragraph("11. НОРМАТИВНЫЕ И ЭКСПЛУАТАЦИОННЫЕ ДОКУМЕНТЫ",h1)]
    norms=["ФНП для ОПО, на которых используются подъёмные сооружения, приказ Ростехнадзора № 461.","Правила по охране труда при строительстве, реконструкции и ремонте, приказ Минтруда России № 883н.","СП 48.13330.2019 «Организация строительства» с действующими изменениями.","Паспорт и руководство по эксплуатации конкретного экземпляра крана.","Проект основания, проект монтажа/демонтажа и проект пристёжек - при их применимости."]
    for item in norms: story.append(Paragraph("• "+item,body))
    story += [Spacer(1,5*mm),Paragraph("12. ЛИСТ РЕГИСТРАЦИИ ИЗМЕНЕНИЙ",h1),_table([["Изм.","Листы","Содержание изменения","Основание","Подпись","Дата"]]+[["","","","","",""] for _ in range(8)],font,[13*mm,22*mm,65*mm,30*mm,20*mm,20*mm],8),Spacer(1,4*mm),Paragraph(f"Документ сформирован {datetime.now():%d.%m.%Y %H:%M}.",small)]
    doc=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=25*mm,rightMargin=10*mm,topMargin=16*mm,bottomMargin=50*mm,title=f"ППРк - {project.name}",author=project.author or "")
    page_callback=lambda canvas,doc:_page_frame(canvas,doc,project)
    doc.build(story,onFirstPage=page_callback,onLaterPages=page_callback)
    if scenarios:
        from pypdf import PdfReader,PdfWriter
        base=PdfReader(str(path)); writer=PdfWriter()
        for page in base.pages: writer.add_page(page)
        for index,scenario in enumerate(scenarios,1):
            plan_source=Path(project.source_plan_pdf) if project.source_plan_pdf else None; plan_vector=bool(plan_source and plan_source.exists() and project.plan_m_per_pixel>0 and tuple(project.plan_crop_box)==(0.0,0.0,1.0,1.0) and project.plan_background_intensity>=1.0)
            packet=io.BytesIO(); canvas=Canvas(packet,pagesize=landscape(A4)); _plan_page(canvas,project,scenario,index,draw_source=not plan_vector); canvas.save(); packet.seek(0); plan_page=PdfReader(packet).pages[0]
            if plan_vector:
                pw,ph=landscape(A4); left,bottom,shown_w,shown_h,_=_pdf_layout(plan_source,project.plan_render_scale,22*mm,48*mm,pw-29*mm,ph-68*mm,project.plan_crop_box)
                plan_page=_merge_vector_background(plan_page,plan_source,left,bottom,shown_w,shown_h)
            writer.add_page(plan_page)
            for placement in scenario.placements:
                if placement.sozr_plan is not None:
                    packet=io.BytesIO(); canvas=Canvas(packet,pagesize=landscape(A3)); draw_sozr_sheet(canvas,project,placement,placement.sozr_plan,len(writer.pages)+1); canvas.save(); packet.seek(0); writer.add_page(PdfReader(packet).pages[0])
            section_source=Path(project.source_section_pdf) if project.source_section_pdf else None; section_vector=bool(section_source and section_source.exists() and project.section_m_per_pixel>0 and tuple(project.section_crop_box)==(0.0,0.0,1.0,1.0) and project.section_background_intensity>=1.0)
            packet=io.BytesIO(); canvas=Canvas(packet,pagesize=landscape(A3)); _section_page(canvas,project,scenario,index,draw_source=not section_vector); canvas.save(); packet.seek(0); section_page=PdfReader(packet).pages[0]
            if section_vector:
                pw,ph=landscape(A3); left,bottom,shown_w,shown_h,_=_pdf_layout(section_source,project.section_render_scale,22*mm,48*mm,pw-29*mm,ph-68*mm,project.section_crop_box)
                section_page=_merge_vector_background(section_page,section_source,left,bottom,shown_w,shown_h)
            writer.add_page(section_page)
        active_loads=[load for load in project.loads if load.active]
        for page_index,start in enumerate(range(0,len(active_loads),6),1):
            packet=io.BytesIO(); canvas=Canvas(packet,pagesize=landscape(A3)); _slinging_page(canvas,project,active_loads[start:start+6],page_index,len(writer.pages)+1); canvas.save(); packet.seek(0); writer.add_page(PdfReader(packet).pages[0])
        packet=io.BytesIO(); canvas=Canvas(packet,pagesize=landscape(A4)); _logistics_page(canvas,project,len(writer.pages)+1); canvas.save(); packet.seek(0); writer.add_page(PdfReader(packet).pages[0])
        packet=io.BytesIO(); canvas=Canvas(packet,pagesize=landscape(A4)); _installation_page(canvas,project,len(writer.pages)+1); canvas.save(); packet.seek(0); writer.add_page(PdfReader(packet).pages[0])
        joint_scenarios=[(index,s) for index,s in enumerate(scenarios,1) if s.joint_plan]
        if not joint_scenarios: joint_scenarios=[(1,None)]
        for variant_number,joint_scenario in joint_scenarios:
            packet=io.BytesIO(); canvas=Canvas(packet,pagesize=landscape(A3)); _coordination_page(canvas,project,joint_scenario,variant_number,len(writer.pages)+1); canvas.save(); packet.seek(0); writer.add_page(PdfReader(packet).pages[0])
            if joint_scenario is not None:
                packet=io.BytesIO(); canvas=Canvas(packet,pagesize=landscape(A3)); _joint_work_schedule_page(canvas,project,joint_scenario,variant_number,len(writer.pages)+1); canvas.save(); packet.seek(0); writer.add_page(PdfReader(packet).pages[0])
        with path.open("wb") as stream: writer.write(stream)
    if selected_pages is not None:
        from pypdf import PdfReader,PdfWriter
        reader=PdfReader(str(path)); page_count=len(reader.pages)
        if not selected_pages:
            raise ValueError("Для итогового ППРк должен быть выбран хотя бы один лист")
        if len(set(selected_pages))!=len(selected_pages) or any(index<0 or index>=page_count for index in selected_pages):
            raise ValueError("Некорректный состав или порядок листов ППРк")
        selected_writer=PdfWriter()
        for index in selected_pages: selected_writer.add_page(reader.pages[index])
        selected_path=path.with_name(path.stem+"_selected.pdf")
        with selected_path.open("wb") as stream: selected_writer.write(stream)
        selected_path.replace(path)
    _restamp_page_numbers(path)
    if document_status:
        _apply_document_status(path, document_status)
    return path

