"""Publish unchanged verified reference PNGs, with separate project evidence.

The slinging library is a complete 24-scheme board. Number selection refers to
that board; it never crops, repaints, annotates or resamples its pixels.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import io
from math import isfinite
import re

from PIL import Image
from reportlab.lib.pagesizes import A1, A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from .pprk_assets import ASSET_ROOT, PPRKAssetRecord, load_asset_manifest, safe_asset_path
from .pprk_composer import PPRKAssetIdentity, PPRKBundle, PPRKContentsEntry
from .pprk_models import CompletenessIssue, ReleaseStatus


_CATEGORIES = {
    "SLINGING_CARDS": "slinging", "STORAGE_SCHEMES": "storage",
    "SAFETY_SIGNS": "safety_signs", "HAND_SIGNALS": "hand_signals",
    "FENCING": "fencing", "PROTECTIVE_SCREENS": "protective_screens",
}
# Conservative names for unambiguous shapes actually present on the board.
# Ambiguous containers, pallets and long products require manual identification.
_SCHEMES = (
    (r"(?:щит\w*\s+опалуб\w*|опалубка)", 2),
    (r"арматура(?:\s+в\s+пучках)?", 1),
    (r"бадья(?:\s+для\s+бетона)?", 17),
)


@dataclass(frozen=True)
class AssetAppendix:
    sheet_id: str
    source_sheet_id: str
    title: str
    category: str
    asset_id: str = ""
    identity: PPRKAssetIdentity | None = None
    scheme_number: int | None = None
    fields: tuple[tuple[str, str], ...] = ()
    placeholder: str = ""
    issues: tuple[CompletenessIssue, ...] = ()
    page_number: int | None = None


@dataclass(frozen=True)
class AppendixRenderResult:
    sheet_id: str
    page_size: tuple[float, float]
    image_box: tuple[float, float, float, float] | None
    asset_id: str
    sha256: str
    issues: tuple[CompletenessIssue, ...]


def _missing(sheet_id: str, message: str) -> CompletenessIssue:
    return CompletenessIssue("PPRK_APPENDIX_REQUIRED", message, True, sheet_id)


def build_slinging_cards(bundle: PPRKBundle) -> tuple[AssetAppendix, ...]:
    """Select only active load cards from immutable bundle evidence."""
    try:
        source = bundle.sheet("appendix.SLINGING_CARDS")
    except KeyError:
        return ()
    identity = next((item for item in source.asset_identities if item.asset_id == "slinging"), None)
    if bundle.active_loads is None:
        message = "НЕ ЗАПОЛНЕНО: исходные данные активных грузов для строповки."
        return (AssetAppendix(source.sheet_id, source.sheet_id, "Карточки строповки", "slinging", placeholder=message, issues=(_missing(source.sheet_id, message),)),)
    cards = []
    for load in bundle.active_loads:
        if not load.active:
            continue
        sheet_id = f"{source.sheet_id}.load-{load.load_index + 1}"
        normalized = " ".join(load.name.casefold().replace("ё", "е").split())
        number = next((number for pattern, number in _SCHEMES if re.fullmatch(pattern, normalized)), None)
        issues = []
        placeholder = ""
        numeric = (*load.dimensions_m, load.load_kg, load.rigging_kg, load.total_kg)
        valid = len(load.dimensions_m) == 3 and all(type(value) in (float, int) and isfinite(value) and value >= 0 for value in numeric)
        valid = valid and all(value > 0 for value in load.dimensions_m) and load.total_kg == load.load_kg + load.rigging_kg
        if number is None:
            placeholder = f"НЕ ЗАПОЛНЕНО: проверенная схема строповки для груза «{load.name}»."
        elif not valid:
            placeholder = f"НЕ ЗАПОЛНЕНО: достоверные массы и габариты груза «{load.name}»."
        elif identity is None:
            placeholder = "НЕ ЗАПОЛНЕНО: проверенный ресурс схем строповки."
        if placeholder:
            issues.append(_missing(sheet_id, placeholder))
        if not load.confirmed or not load.operation_ids or load.warnings:
            issues.append(_missing(sheet_id, f"Груз «{load.name}»: требуются подтверждение и проверенная операция; " + "; ".join(load.warnings)))
        fields = (
            ("Груз", load.name),
            ("Масса груза, кг", str(load.load_kg)),
            ("Масса оснастки, кг", str(load.rigging_kg)),
            ("Полная поднимаемая масса, кг", str(load.total_kg)),
            ("Габариты Д × Ш × В, м", " × ".join(f"{value:g}" if type(value) in (float, int) and isfinite(value) else "НЕ ЗАПОЛНЕНО" for value in load.dimensions_m)),
            ("Схема на листе", str(number) if number else "НЕ ЗАПОЛНЕНО"),
            ("Строп / ветви", "; ".join(f"{key}: {value}" for key, value in load.sling_fields) or "НЕ ЗАПОЛНЕНО: уточнить по паспорту оснастки"),
            ("Подтверждение исходных данных", "ПОДТВЕРЖДЕНО" if load.confirmed else "НЕ ПОДТВЕРЖДЕНО"),
            ("Операции", ", ".join(load.operation_ids) or "НЕ ЗАПОЛНЕНО"),
            ("Предупреждения", "; ".join(load.warnings) or "Нет; соответствие оснастки конкретному грузу проверяет разработчик."),
        )
        cards.append(AssetAppendix(sheet_id, source.sheet_id, f"Строповка: {load.name}", "slinging", "slinging" if not placeholder else "", identity if not placeholder else None, number, fields, placeholder, tuple(issues)))
    return tuple(cards)


def _verified_bytes(appendix: AssetAppendix, assets) -> tuple[PPRKAssetRecord, bytes]:
    records = [record for record in assets if record.asset_id == appendix.asset_id]
    canonical = {record.asset_id: record for record in load_asset_manifest()}.get(appendix.asset_id)
    if len(records) != 1 or canonical is None or records[0] != canonical:
        raise ValueError(f"Ресурс {appendix.asset_id}: запись не соответствует авторитетному реестру")
    record = records[0]
    expected = PPRKAssetIdentity(record.asset_id, record.sha256, record.category, record.quality_status)
    if appendix.identity != expected or record.category != appendix.category or record.quality_status != "verified" or record.source_kind != "reference_clip":
        raise ValueError(f"Ресурс {record.asset_id}: неверные категория, статус или идентичность")
    try:
        data = safe_asset_path(ASSET_ROOT, record.file_name).read_bytes()
        if hashlib.sha256(data).hexdigest() != record.sha256:
            raise ValueError("SHA-256")
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.format != "PNG" or image.size != (record.pixel_width, record.pixel_height):
                raise ValueError("dimensions")
    except (OSError, ValueError) as exc:
        raise ValueError(f"Ресурс {record.asset_id}: отсутствует или изменён ({exc})") from exc
    return record, data


def plan_asset_appendices(bundle: PPRKBundle, assets) -> tuple[AssetAppendix, ...]:
    """Follow bundle order; only its applicable reference parts are published."""
    result = []
    for part in bundle.parts:
        if part.kind != "appendix":
            continue
        category = _CATEGORIES.get(part.part_id.removeprefix("appendix."))
        if not category:
            continue
        if category == "slinging":
            plans = build_slinging_cards(bundle)
        else:
            sheet = part.sheets[0]
            identity = next((item for item in sheet.asset_identities if item.asset_id == category), None)
            plans = (AssetAppendix(sheet.sheet_id, sheet.sheet_id, part.title, category, category, identity),)
        for plan in plans:
            record = None
            if plan.asset_id:
                try:
                    record, _ = _verified_bytes(plan, assets)
                    if category != "slinging":
                        plan = replace(plan, title=record.title)
                except (OSError, ValueError) as exc:
                    message = f"НЕ ЗАПОЛНЕНО: {exc}"
                    plan = replace(plan, asset_id="", placeholder=message, issues=(*plan.issues, _missing(plan.sheet_id, message)))
                    record = None
            _appendix_layout(plan, record)
            result.append(plan)
    return tuple(result)


def apply_appendix_completeness(bundle: PPRKBundle, plans: tuple[AssetAppendix, ...]) -> PPRKBundle:
    """Incomplete reference sheets can appear only in an explicitly preliminary edition."""
    issues = tuple(replace(issue, blocking=bundle.requested_status != ReleaseStatus.PRELIMINARY)
                   for plan in plans for issue in plan.issues)
    if not issues:
        return bundle
    return replace(bundle, completeness_issues=tuple(dict.fromkeys((*bundle.completeness_issues, *issues))),
                   production_allowed=False, effective_status=ReleaseStatus.PRELIMINARY)


def expand_bundle_appendices(bundle: PPRKBundle, plans: tuple[AssetAppendix, ...]) -> PPRKBundle:
    parts = []
    for part in bundle.parts:
        if part.kind == "appendix" and part.part_id.removeprefix("appendix.") in _CATEGORIES:
            selected = [plan for plan in plans if plan.source_sheet_id == part.part_id]
            if not selected:
                continue
            part = replace(part, sheets=tuple(replace(
                part.sheets[0], sheet_id=plan.sheet_id, title=plan.title,
                asset_identities=(plan.identity,) if plan.asset_id and plan.identity else (),
            ) for plan in selected))
        parts.append(part)
    contents = tuple(PPRKContentsEntry(sheet.sheet_id, part.part_id, sheet.title, sheet.designation or str(sheet.page_number or ""), part.kind) for part in parts for sheet in part.sheets)
    return replace(apply_appendix_completeness(bundle, plans), parts=tuple(parts), contents=contents)


def _appendix_layout(appendix, record):
    """Measure exactly the title, image destination and table used in printing."""
    from .report import _font, _table
    from html import escape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    page_size = A1 if appendix.category == "slinging" and record else A4
    width, height = page_size
    left, usable = 20 * mm, width - 35 * mm
    def wrapped_height(text, size, leading):
        paragraph = Paragraph(escape(text).replace("\n", "<br/>"),
                              ParagraphStyle("AppendixMeasure", fontName=_font(), fontSize=size, leading=leading))
        return paragraph.wrap(usable, 70 * mm)[1]
    top = height - 15 * mm - wrapped_height(appendix.title, 12, 15)
    image_box = None
    if record:
        # A1 keeps the full board readable near its original physical size.
        maximum_height = height - 180 * mm if appendix.fields else height - 50 * mm
        scale = min(usable / record.pixel_width, maximum_height / record.pixel_height)
        shown_w, shown_h = record.pixel_width * scale, record.pixel_height * scale
        bottom = top - 5 * mm - shown_h
        image_box = (left + (usable - shown_w) / 2, bottom, shown_w, shown_h)
        top = bottom - 7 * mm
    placeholder_top = top - 5 * mm
    if appendix.placeholder:
        top = placeholder_top - wrapped_height(appendix.placeholder, 9, 11) - 5 * mm
    table = None
    table_height = 0
    if appendix.fields:
        table = _table(appendix.fields, _font(), [usable * .35, usable * .65], 9, False)
        _, table_height = table.wrap(usable, height)
        if top - table_height < 18 * mm:
            raise ValueError(f"Таблица приложения {appendix.sheet_id} не помещается на листе")
    return page_size, image_box, placeholder_top, top - table_height, table


def draw_asset_appendix(canvas, appendix: AssetAppendix, assets) -> AppendixRenderResult:
    """Embed the exact decoded PNG pixels; all generated text is outside it."""
    from .report import _font
    from .pprk_text_report import _draw_wrapped
    record, data = _verified_bytes(appendix, assets) if appendix.asset_id else (None, None)
    page_size, image_box, placeholder_top, table_bottom, table = _appendix_layout(appendix, record)
    canvas.setPageSize(page_size)
    width, height = page_size
    left, usable = 20 * mm, width - 35 * mm
    _draw_wrapped(canvas, appendix.title, left, height - 15 * mm, usable, font_size=12, leading=15)
    if image_box:
        canvas.drawImage(ImageReader(io.BytesIO(data)), *image_box)
    if appendix.placeholder:
        _draw_wrapped(canvas, appendix.placeholder, left, placeholder_top, usable, placeholder=True)
    if table:
        table.drawOn(canvas, left, table_bottom)
    canvas.setFont(_font(), 8)
    canvas.drawRightString(width - 15 * mm, 10 * mm, f"ППРк / стр. {appendix.page_number or '—'}")
    canvas.showPage()
    return AppendixRenderResult(appendix.sheet_id, page_size, image_box, appendix.asset_id, record.sha256 if record else "", appendix.issues)
