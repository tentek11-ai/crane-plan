"""A4 front matter and explanatory-note renderer for a composed PPRk bundle.

This module is deliberately limited to document layout.  It consumes the
immutable bundle produced by :mod:`pprk_composer` and never derives or
recalculates engineering values.
"""

from __future__ import annotations

import io
import re
from html import escape
from pathlib import Path
from typing import Iterable, Mapping

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from .pprk_composer import PPRKBundle, PPRKSheet
from .pprk_models import ReleaseStatus


_SERVICE_ORDER = (
    "service.title",
    "service.approvals",
    "service.familiarization",
    "service.contents",
)
_PLACEHOLDER_PREFIX = "⟦НЕ ЗАПОЛНЕНО:"


class _SectionHeading(Paragraph):
    def __init__(self, section_id: str, text: str, style: ParagraphStyle):
        super().__init__(text, style)
        self.section_id = section_id


class _TrackingDocTemplate(SimpleDocTemplate):
    """Record actual PDF start pages for section headings after wrapping."""

    def __init__(self, *args, page_offset: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_offset = page_offset
        self.section_pages: dict[str, int] = {}

    def afterFlowable(self, flowable) -> None:  # noqa: N802 - ReportLab API
        if isinstance(flowable, _SectionHeading):
            self.section_pages.setdefault(flowable.section_id, self.page + self.page_offset)


def _font() -> str:
    for path in (
        Path("C:/Windows/Fonts/isocpeur.ttf"),
        Path("C:/Windows/Fonts/ARIALN.TTF"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
        if path.exists():
            if "CranePlanGOST" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("CranePlanGOST", str(path)))
            return "CranePlanGOST"
    return "Helvetica"


def _frame(canvas: Canvas, page_number: int, total_pages: int | None = None) -> None:
    width, height = A4
    canvas.saveState()
    canvas.setStrokeColor(colors.black)
    canvas.setLineWidth(0.55)
    canvas.rect(20 * mm, 5 * mm, width - 25 * mm, height - 10 * mm)
    canvas.line(20 * mm, 14 * mm, width - 5 * mm, 14 * mm)
    canvas.setFont(_font(), 7)
    canvas.drawString(22 * mm, 8 * mm, "ППРк")
    label = f"Лист {page_number}"
    if total_pages:
        label += f" из {total_pages}"
    canvas.drawRightString(width - 8 * mm, 8 * mm, label)
    canvas.restoreState()


def _field_text(value: object) -> tuple[str, bool]:
    text = "" if value is None else str(value).strip()
    if text.startswith(_PLACEHOLDER_PREFIX):
        text = text.removeprefix("⟦").removesuffix("⟧")
        return text, True
    return text or "____________________________", False


def _draw_wrapped(
    canvas: Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    *,
    font_size: float = 9,
    leading: float = 11,
    alignment: int = TA_LEFT,
    placeholder: bool = False,
) -> float:
    style = ParagraphStyle(
        "CanvasText",
        fontName=_font(),
        fontSize=font_size,
        leading=leading,
        alignment=alignment,
        textColor=colors.HexColor("#C00000") if placeholder else colors.black,
    )
    paragraph = Paragraph(escape(text).replace("\n", "<br/>"), style)
    _, height = paragraph.wrap(width, 70 * mm)
    paragraph.drawOn(canvas, x, y - height)
    return y - height


def _draw_cell_text(
    canvas: Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    font_size: float,
    alignment: int = TA_LEFT,
    placeholder: bool = False,
    min_font_size: float = 4.2,
) -> None:
    """Fit complete text into a bounded cell without slicing its value."""

    safe_text = escape(text).replace("\n", "<br/>")
    candidates: list[float] = []
    candidate = font_size
    while candidate > min_font_size:
        candidates.append(candidate)
        candidate -= 0.6
    candidates.append(min_font_size)
    for candidate in candidates:
        style = ParagraphStyle(
            "CellFit",
            fontName=_font(),
            fontSize=candidate,
            leading=candidate + 0.8,
            alignment=alignment,
            textColor=colors.HexColor("#C00000") if placeholder else colors.black,
        )
        paragraph = Paragraph(safe_text, style)
        _, wrapped_height = paragraph.wrap(max(1, width - 2.4 * mm), max(1, height - 1.4 * mm))
        if wrapped_height <= height - 1.4 * mm:
            paragraph.drawOn(
                canvas,
                x + 1.2 * mm,
                y + (height - wrapped_height) / 2,
            )
            return
    raise ValueError(f"Текст не помещается в ячейке: {text}")


def draw_title_page(
    canvas: Canvas,
    sheet: PPRKSheet,
    *,
    status: ReleaseStatus = ReleaseStatus.PRELIMINARY,
    page_number: int = 1,
    total_pages: int | None = None,
) -> None:
    """Draw the fixed A4 title sheet from bundle fields."""

    fields = dict(sheet.fields)
    width, height = A4
    _frame(canvas, page_number, total_pages)
    organization, organization_missing = _field_text(fields.get("organization"))
    _draw_cell_text(
        canvas,
        organization,
        35 * mm,
        height - 31 * mm,
        width - 70 * mm,
        13 * mm,
        font_size=9,
        alignment=TA_CENTER,
        placeholder=organization_missing,
    )
    canvas.setFont(_font(), 10)
    canvas.drawString(24 * mm, height - 42 * mm, "УТВЕРЖДАЮ")
    canvas.drawRightString(width - 24 * mm, height - 42 * mm, "СОГЛАСОВАНО")
    canvas.setFont(_font(), 15)
    canvas.drawCentredString(width / 2, height - 75 * mm, "ПРОЕКТ ПРОИЗВОДСТВА РАБОТ КРАНАМИ")
    status_labels = {
        ReleaseStatus.PRELIMINARY: "предварительная автоматизированная редакция",
        ReleaseStatus.REVIEW: "На проверку", ReleaseStatus.COORDINATION: "На согласование",
        ReleaseStatus.APPROVED: "Утверждён", ReleaseStatus.PRODUCTION: "В производство",
    }
    canvas.setFont(_font(), 10)
    canvas.drawCentredString(width / 2, height - 82 * mm, status_labels[status])
    title, title_missing = _field_text(fields.get("title"))
    _draw_cell_text(
        canvas,
        title,
        30 * mm,
        height - 108 * mm,
        width - 60 * mm,
        22 * mm,
        font_size=11,
        alignment=TA_CENTER,
        placeholder=title_missing,
        min_font_size=6.0,
    )
    rows = (
        ("Вид подъемного сооружения", "lifting_equipment_type"),
        ("Марка крана", "crane_model"),
        ("Конфигурация", "crane_configurations"),
        ("Объект", "object_name"),
        ("Адрес", "object_address"),
        ("Шифр проекта", "project_code"),
        ("Разработчик", "developer_position"),
        ("Ф.И.О. разработчика", "developer_name"),
        ("Дата разработчика", "developer_date"),
        ("Руководитель", "manager_position"),
        ("Ф.И.О. руководителя", "manager_name"),
        ("Дата руководителя", "manager_date"),
    )
    y = height - 112 * mm
    canvas.setLineWidth(0.35)
    for label, key in rows:
        row_height = 9 * mm
        canvas.rect(27 * mm, y - row_height, 55 * mm, row_height)
        canvas.rect(82 * mm, y - row_height, width - 109 * mm, row_height)
        _draw_cell_text(canvas, label, 27 * mm, y - row_height, 55 * mm, row_height, font_size=7.2)
        value, missing = _field_text(fields.get(key))
        _draw_cell_text(
            canvas,
            value,
            82 * mm,
            y - row_height,
            width - 109 * mm,
            row_height,
            font_size=7.2,
            placeholder=missing,
        )
        y -= row_height
    city, city_missing = _field_text(fields.get("issue_city"))
    year, year_missing = _field_text(fields.get("issue_year"))
    canvas.setFillColor(colors.HexColor("#C00000") if city_missing or year_missing else colors.black)
    canvas.setFont(_font(), 9)
    canvas.drawCentredString(width / 2, 23 * mm, f"{city}, {year}")
    issue_date, date_missing = _field_text(fields.get("issue_date"))
    canvas.setFillColor(colors.HexColor("#C00000") if date_missing else colors.black)
    canvas.setFont(_font(), 7)
    canvas.drawCentredString(width / 2, 18 * mm, f"Дата выпуска: {issue_date}")
    canvas.setFillColor(colors.black)
    canvas.showPage()


def draw_approval_page(
    canvas: Canvas,
    sheet: PPRKSheet,
    *,
    page_number: int = 2,
    total_pages: int | None = None,
) -> None:
    """Draw exactly eight approval cells, padding or truncating defensively."""

    width, height = A4
    _frame(canvas, page_number, total_pages)
    canvas.setFont(_font(), 14)
    canvas.drawCentredString(width / 2, height - 20 * mm, "ЛИСТ СОГЛАСОВАНИЙ")
    slots = list(sheet.approval_slots[:8])
    slots.extend(("", "", "", "", "") for _ in range(8 - len(slots)))
    left = 24 * mm
    top = height - 32 * mm
    cell_w = (width - 52 * mm) / 2
    cell_h = 58 * mm
    labels = ("Организация", "Должность", "Ф.И.О.", "Подпись", "Дата")
    for index, values in enumerate(slots):
        column = index % 2
        row = index // 2
        x = left + column * (cell_w + 4 * mm)
        y = top - (row + 1) * cell_h
        canvas.rect(x, y, cell_w, cell_h - 3 * mm)
        canvas.setFont(_font(), 8.5)
        role = sheet.approval_roles[index] if index < len(sheet.approval_roles) else ""
        role_label = {"CHECKER": " / ПРОВЕРИЛ", "APPROVER": " / УТВЕРДИЛ"}.get(role, "")
        canvas.drawCentredString(x + cell_w / 2, y + cell_h - 10 * mm, "СОГЛАСОВАНО" + role_label)
        for field_index, (label, raw_value) in enumerate(zip(labels, values)):
            field_y = y + cell_h - (24 + field_index * 8.0) * mm
            value, missing = _field_text(raw_value)
            _draw_cell_text(canvas, label, x + 2 * mm, field_y, 23 * mm, 8 * mm, font_size=6.0)
            _draw_cell_text(
                canvas,
                value,
                x + 25 * mm,
                field_y,
                cell_w - 27 * mm,
                8 * mm,
                font_size=6.0,
                placeholder=missing,
            )
    canvas.setFillColor(colors.black)
    canvas.showPage()


def draw_familiarization_page(
    canvas: Canvas,
    sheet: PPRKSheet | None = None,
    *,
    page_number: int = 3,
    total_pages: int | None = None,
) -> None:
    """Draw the mandatory personnel familiarization register."""

    width, height = A4
    _frame(canvas, page_number, total_pages)
    canvas.setFont(_font(), 13)
    canvas.drawCentredString(width / 2, height - 20 * mm, "ЛИСТ РЕГИСТРАЦИИ ОЗНАКОМЛЕНИЯ")
    columns = (18 * mm, 63 * mm, 48 * mm, 31 * mm)
    headers = ("Дата", "Фамилия и инициалы", "Должность", "Подпись")
    x0 = 24 * mm
    y_top = height - 34 * mm
    row_h = 12 * mm
    canvas.setFont(_font(), 7)
    x = x0
    for header, column_width in zip(headers, columns):
        canvas.rect(x, y_top - row_h, column_width, row_h)
        canvas.drawCentredString(x + column_width / 2, y_top - 7.5 * mm, header)
        x += column_width
    for row in range(18):
        x = x0
        y = y_top - (row + 2) * row_h
        for column_width in columns:
            canvas.rect(x, y, column_width, row_h)
            x += column_width
    canvas.showPage()


def _draw_contents_page(
    canvas: Canvas,
    bundle: PPRKBundle,
    *,
    page_number: int = 4,
    total_pages: int | None = None,
    page_overrides: Mapping[str, int | str] | None = None,
) -> None:
    width, height = A4
    _frame(canvas, page_number, total_pages)
    canvas.setFont(_font(), 14)
    canvas.drawCentredString(width / 2, height - 20 * mm, "СОСТАВ ПРОЕКТА")
    x0 = 24 * mm
    y = height - 34 * mm
    widths = (12 * mm, 117 * mm, 31 * mm)
    headers = ("№", "Наименование", "Лист")
    canvas.setFont(_font(), 7)
    x = x0
    for header, column_width in zip(headers, widths):
        canvas.rect(x, y - 10 * mm, column_width, 10 * mm)
        canvas.drawCentredString(x + column_width / 2, y - 6.5 * mm, header)
        x += column_width
    y -= 10 * mm
    available_height = y - 18 * mm
    row_count = max(1, len(bundle.contents))
    row_h = min(9 * mm, available_height / row_count)
    if row_h < 4.2 * mm:
        raise ValueError("Состав проекта не помещается на обязательном листе A4")
    canvas.setFont(_font(), max(5.0, min(7.0, row_h / mm - 0.7)))
    for index, entry in enumerate(bundle.contents, start=1):
        x = x0
        number = (page_overrides or {}).get(entry.target_id, entry.number)
        values = (str(index), entry.title, number)
        for value, column_width in zip(values, widths):
            canvas.rect(x, y - row_h, column_width, row_h)
            _draw_cell_text(
                canvas,
                str(value),
                x,
                y - row_h,
                column_width,
                row_h,
                font_size=max(5.0, min(7.0, row_h / mm - 0.7)),
                alignment=TA_CENTER if column_width != widths[1] else TA_LEFT,
            )
            x += column_width
        y -= row_h
    canvas.showPage()


def _paragraph_markup(text: str) -> str:
    result: list[str] = []
    position = 0
    for match in re.finditer(r"⟦НЕ ЗАПОЛНЕНО:\s*([^⟧]+)⟧", text):
        result.append(escape(text[position : match.start()]))
        marker = escape(f"НЕ ЗАПОЛНЕНО: {match.group(1).strip()}")
        result.append(f'<font color="#C00000">{marker}</font>')
        position = match.end()
    result.append(escape(text[position:]))
    return "".join(result)


def build_contents_page_map(
    bundle: PPRKBundle,
    rendered_note_pages: Mapping[str, int],
    *,
    rendered_page_count: int,
    pending_label: str = "ОЖИДАЕТ ВКЛЮЧЕНИЯ",
) -> dict[str, int | str]:
    """Map current rendered pages without fabricating future appendix pages."""

    result: dict[str, int | str] = {}
    part_by_id = {part.part_id: part for part in bundle.parts}
    for entry in bundle.contents:
        part = part_by_id[entry.part_id]
        if part.kind == "service":
            page = next(
                sheet.page_number
                for sheet in part.sheets
                if sheet.sheet_id == entry.target_id
            )
            if page is None or page > rendered_page_count:
                raise ValueError(f"Некорректный номер служебного листа: {entry.target_id}")
            result[entry.target_id] = page
        elif part.kind == "note":
            page = rendered_note_pages.get(entry.target_id)
            if page is None:
                sheet = next(sheet for sheet in part.sheets if sheet.sheet_id == entry.target_id)
                page = sheet.page_number
            if page is None or page > rendered_page_count:
                raise ValueError(f"Не определена фактическая страница раздела: {entry.target_id}")
            result[entry.target_id] = page
        elif part.kind == "graphical":
            result[entry.target_id] = entry.number if entry.number.startswith("ГЧ-") else pending_label
        else:
            result[entry.target_id] = pending_label
    return result


def build_explanatory_note_story(
    bundle: PPRKBundle,
    *,
    font_name: str | None = None,
    reference_overrides: Mapping[str, int | str] | None = None,
) -> list[object]:
    """Build Platypus flowables for every included explanatory-note part."""

    font = font_name or _font()
    title_style = ParagraphStyle(
        "PPRKNoteTitle",
        fontName=font,
        fontSize=15,
        leading=19,
        alignment=TA_CENTER,
        spaceAfter=8 * mm,
    )
    heading_style = ParagraphStyle(
        "PPRKNoteHeading",
        fontName=font,
        fontSize=11,
        leading=14,
        spaceBefore=2 * mm,
        spaceAfter=3 * mm,
    )
    body_style = ParagraphStyle(
        "PPRKNoteBody",
        fontName=font,
        fontSize=8.5,
        leading=11.5,
        alignment=TA_JUSTIFY,
        spaceAfter=2.2 * mm,
    )
    story: list[object] = [Paragraph("ПОЯСНИТЕЛЬНАЯ ЗАПИСКА", title_style)]
    note_parts = [part for part in bundle.parts if part.kind == "note"]
    for index, part in enumerate(note_parts):
        if index:
            story.append(PageBreak())
        story.append(_SectionHeading(part.part_id, escape(part.title), heading_style))
        paragraphs = [item.strip() for item in part.rendered_text.split("\n\n") if item.strip()]
        if not paragraphs:
            paragraphs = ["⟦НЕ ЗАПОЛНЕНО: section_text⟧"]
        for paragraph in paragraphs:
            story.append(Paragraph(_paragraph_markup(paragraph), body_style))
        reference_keys = tuple(
            dict.fromkeys(key for sheet in part.sheets for key in sheet.reference_keys)
        )
        if reference_keys and reference_overrides:
            graphical = [key for key in reference_keys if key.startswith("drawing.")]
            missing_graphical = [key for key in graphical if key not in reference_overrides]
            if missing_graphical:
                raise ValueError(f"Не определены физические страницы ссылок: {', '.join(missing_graphical)}")
            resolved = [str(reference_overrides[key]) for key in graphical]
            if resolved:
                story.append(Paragraph("Расчётные листы: " + "; ".join(resolved), body_style))
            external = [key for key in reference_keys if key.startswith(("appendix.", "external."))]
            if external:
                story.append(Paragraph(
                    "Приложения и внешние документы: "
                    + "; ".join(
                        str(reference_overrides.get(key, f"{key} — ОЖИДАЕТ ВКЛЮЧЕНИЯ"))
                        for key in external
                    ),
                    body_style,
                ))
        story.append(Spacer(1, 2 * mm))
    return story


def _merge_pages(dest: Path, sources: Iterable[Path]) -> None:
    writer = PdfWriter()
    for source in sources:
        for page in PdfReader(str(source)).pages:
            writer.add_page(page)
    with dest.open("wb") as stream:
        writer.write(stream)


def render_pprk_text_report(
    path: str | Path,
    bundle: PPRKBundle,
    *,
    author: str = "",
    page_overrides: Mapping[str, int | str] | None = None,
) -> Path:
    """Render service sheets and the full bundle-driven explanatory note."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    service_ids = tuple(part.part_id for part in bundle.parts[:4])
    if service_ids != _SERVICE_ORDER:
        raise ValueError("Первые четыре части ППРк имеют неверный состав или порядок")

    front_path = path.with_suffix(".front.tmp.pdf")
    note_path = path.with_suffix(".note.tmp.pdf")

    def note_frame(canvas: Canvas, document) -> None:
        _frame(canvas, document.page + 4)

    document = _TrackingDocTemplate(
        str(note_path),
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=12 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="ППРк — пояснительная записка",
        author=author or "",
        page_offset=4,
    )
    document.build(
        build_explanatory_note_story(bundle, reference_overrides=page_overrides),
        onFirstPage=note_frame,
        onLaterPages=note_frame,
    )
    rendered_page_count = 4 + len(PdfReader(str(note_path)).pages)
    contents_page_map = build_contents_page_map(
        bundle,
        document.section_pages,
        rendered_page_count=rendered_page_count,
    )
    if page_overrides:
        contents_page_map.update(page_overrides)
    service_sheets = [bundle.part(part_id).sheets[0] for part_id in _SERVICE_ORDER]
    front_buffer = io.BytesIO()
    front = Canvas(front_buffer, pagesize=A4)
    draw_title_page(front, service_sheets[0], status=bundle.effective_status, page_number=1)
    draw_approval_page(front, service_sheets[1], page_number=2)
    draw_familiarization_page(front, service_sheets[2], page_number=3)
    _draw_contents_page(
        front,
        bundle,
        page_number=4,
        page_overrides=contents_page_map,
    )
    front.save()
    front_buffer.seek(0)
    front_path.write_bytes(front_buffer.getvalue())
    try:
        _merge_pages(path, (front_path, note_path))
    finally:
        front_path.unlink(missing_ok=True)
        note_path.unlink(missing_ok=True)
    return path


