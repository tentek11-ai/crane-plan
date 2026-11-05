"""Strict catalog and rendering boundary for the standard PPRk explanatory note."""

from __future__ import annotations

import json
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from string import Formatter
from typing import Mapping, Sequence

from .pprk_models import TemplateOverride


DEFAULT_CATALOG_PATH = Path(__file__).parent / "assets" / "pprk" / "sections.json"
DEFAULT_REGISTRY_PATH = Path(__file__).parents[2] / "02_processed_data" / "regulations" / "regulation_registry.csv"
MISSING_VALUE_TEMPLATE = "⟦НЕ ЗАПОЛНЕНО: {name}⟧"
ALLOWED_ORIGIN_STATUSES = frozenset({"typical", "calculated", "user", "external"})


class TemplateCatalogError(ValueError):
    """The stored template catalog violates its declared schema."""


@dataclass(frozen=True)
class TemplateParagraph:
    paragraph_id: str
    version: str
    text: str
    origin_status: str
    review_date: str
    sheet_links: tuple[str, ...]
    appendix_links: tuple[str, ...]
    source_page: int | None = None

    @property
    def placeholders(self) -> tuple[str, ...]:
        return _placeholders(self.text)


@dataclass(frozen=True)
class TemplateSection:
    section_id: str
    title: str
    inclusion_condition: str
    required_variables: tuple[str, ...]
    normative_keys: tuple[str, ...]
    source_pages: tuple[int, ...]
    paragraphs: tuple[TemplateParagraph, ...]


@dataclass(frozen=True)
class OverrideConflict:
    paragraph_id: str
    expected_version: str
    override_version: str
    reason: str = "base_version_changed"


@dataclass(frozen=True)
class RenderedSection:
    section_id: str
    title: str
    text: str
    paragraphs: tuple[str, ...]
    missing_variables: tuple[str, ...]
    override_conflicts: tuple[OverrideConflict, ...]
    inclusion_condition: str
    normative_keys: tuple[str, ...]


def _placeholders(text: str) -> tuple[str, ...]:
    names: list[str] = []
    try:
        fields = Formatter().parse(text)
        for _literal, field_name, _format_spec, _conversion in fields:
            if field_name is None:
                continue
            if not field_name or any(mark in field_name for mark in (".", "[", "]")):
                raise TemplateCatalogError(f"unsupported placeholder: {field_name!r}")
            if field_name not in names:
                names.append(field_name)
    except ValueError as exc:
        raise TemplateCatalogError(f"invalid placeholder syntax: {exc}") from exc
    return tuple(names)


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise TemplateCatalogError(f"{field_name} must be a list of non-empty strings")
    return tuple(value)


def _review_date(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TemplateCatalogError(f"{field_name}: review_date is required")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise TemplateCatalogError(f"{field_name}: invalid review_date: {value!r}") from exc
    return value


def load_regulation_ids(path: str | Path = DEFAULT_REGISTRY_PATH) -> set[str]:
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
            rows = csv.DictReader(stream)
            ids = {str(row.get("rule_id", "")).strip() for row in rows}
    except OSError as exc:
        raise TemplateCatalogError(f"cannot load regulation registry: {exc}") from exc
    ids.discard("")
    if not ids:
        raise TemplateCatalogError("regulation registry is empty")
    return ids


def validate_catalog_regulations(
    catalog: Sequence[TemplateSection], registry_ids: set[str]
) -> tuple[str, ...]:
    used = {key for section in catalog for key in section.normative_keys}
    return tuple(sorted(used - registry_ids))


def load_template_catalog(
    path: str | Path = DEFAULT_CATALOG_PATH,
    *,
    regulation_ids: set[str] | None = None,
) -> tuple[TemplateSection, ...]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemplateCatalogError(f"cannot load template catalog: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise TemplateCatalogError("unsupported template catalog schema")
    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list):
        raise TemplateCatalogError("sections must be a list")

    section_ids: set[str] = set()
    paragraph_ids: set[str] = set()
    sections: list[TemplateSection] = []
    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            raise TemplateCatalogError("section must be an object")
        section_id = raw_section.get("id")
        title = raw_section.get("title")
        condition = raw_section.get("condition")
        origin_status = raw_section.get("origin_status")
        if not all(isinstance(item, str) and item for item in (section_id, title, condition)):
            raise TemplateCatalogError("section id, title and condition are required")
        if origin_status not in ALLOWED_ORIGIN_STATUSES:
            raise TemplateCatalogError(f"{section_id}: invalid origin_status: {origin_status!r}")
        review_date = _review_date(raw_section.get("review_date"), section_id)
        sheet_links = _string_list(raw_section.get("sheet_links", []), "sheet_links")
        appendix_links = _string_list(raw_section.get("appendix_links", []), "appendix_links")
        if section_id in section_ids:
            raise TemplateCatalogError(f"duplicate section id: {section_id}")
        section_ids.add(section_id)
        declared = _string_list(raw_section.get("required_variables", []), "required_variables")
        normative_keys = _string_list(raw_section.get("normative_keys", []), "normative_keys")
        source_pages_value = raw_section.get("source_pages")
        if not isinstance(source_pages_value, list) or not source_pages_value or not all(
            isinstance(item, int) and item > 0 for item in source_pages_value
        ):
            raise TemplateCatalogError(f"{section_id}: source_pages must contain positive integers")
        raw_paragraphs = raw_section.get("paragraphs")
        if not isinstance(raw_paragraphs, list) or not raw_paragraphs:
            raise TemplateCatalogError(f"{section_id}: paragraphs must not be empty")
        paragraphs: list[TemplateParagraph] = []
        for raw_paragraph in raw_paragraphs:
            if not isinstance(raw_paragraph, dict):
                raise TemplateCatalogError(f"{section_id}: paragraph must be an object")
            paragraph_id = raw_paragraph.get("id")
            version = raw_paragraph.get("version")
            text = raw_paragraph.get("text")
            if not all(isinstance(item, str) and item for item in (paragraph_id, version, text)):
                raise TemplateCatalogError(f"{section_id}: paragraph id, version and text are required")
            if paragraph_id in paragraph_ids:
                raise TemplateCatalogError(f"duplicate paragraph id: {paragraph_id}")
            paragraph_ids.add(paragraph_id)
            paragraph_origin = raw_paragraph.get("origin_status", origin_status)
            if paragraph_origin not in ALLOWED_ORIGIN_STATUSES:
                raise TemplateCatalogError(f"{paragraph_id}: invalid origin_status: {paragraph_origin!r}")
            source_page = raw_paragraph.get("source_page")
            if not isinstance(source_page, int) or source_page <= 0 or source_page not in source_pages_value:
                raise TemplateCatalogError(f"{paragraph_id}: source_page must belong to section source_pages")
            paragraph = TemplateParagraph(
                paragraph_id,
                version,
                text,
                paragraph_origin,
                _review_date(raw_paragraph.get("review_date", review_date), paragraph_id),
                _string_list(raw_paragraph.get("sheet_links", list(sheet_links)), "sheet_links"),
                _string_list(raw_paragraph.get("appendix_links", list(appendix_links)), "appendix_links"),
                source_page,
            )
            undeclared = set(paragraph.placeholders) - set(declared)
            if undeclared:
                raise TemplateCatalogError(
                    f"{paragraph_id}: undeclared placeholders: {', '.join(sorted(undeclared))}"
                )
            paragraphs.append(paragraph)
        sections.append(
            TemplateSection(
                section_id=section_id,
                title=title,
                inclusion_condition=condition,
                required_variables=declared,
                normative_keys=normative_keys,
                source_pages=tuple(source_pages_value),
                paragraphs=tuple(paragraphs),
            )
        )
    result = tuple(sections)
    resolved_ids = load_regulation_ids() if regulation_ids is None else regulation_ids
    dangling = validate_catalog_regulations(result, resolved_ids)
    if dangling:
        raise TemplateCatalogError(f"dangling normative keys: {', '.join(dangling)}")
    return result


def render_template_text(
    section_id: str,
    context: Mapping[str, object],
    overrides: Sequence[TemplateOverride],
    *,
    catalog: Sequence[TemplateSection] | None = None,
) -> RenderedSection:
    sections = tuple(catalog) if catalog is not None else load_template_catalog()
    section = next((item for item in sections if item.section_id == section_id), None)
    if section is None:
        raise TemplateCatalogError(f"unknown section: {section_id}")
    overrides_by_id: dict[str, list[TemplateOverride]] = {}
    for item in overrides:
        overrides_by_id.setdefault(item.paragraph_id, []).append(item)
    all_paragraph_ids = {paragraph.paragraph_id for item in sections for paragraph in item.paragraphs}
    missing = tuple(
        name for name in section.required_variables if name not in context or context[name] in (None, "")
    )
    values = {
        name: context.get(name) if context.get(name) not in (None, "") else MISSING_VALUE_TEMPLATE.format(name=name)
        for name in section.required_variables
    }
    rendered: list[str] = []
    conflicts: list[OverrideConflict] = [
        OverrideConflict(item.paragraph_id, "", item.base_version, "orphan_override")
        for item in overrides
        if item.paragraph_id not in all_paragraph_ids
    ]
    conflicts.extend(
        OverrideConflict(paragraph_id, "", items[-1].base_version, "duplicate_override")
        for paragraph_id, items in overrides_by_id.items()
        if len(items) > 1 and paragraph_id in all_paragraph_ids
    )
    for paragraph in section.paragraphs:
        text = paragraph.text
        candidates = overrides_by_id.get(paragraph.paragraph_id, [])
        override = candidates[0] if len(candidates) == 1 else None
        if override is not None:
            if override.base_version == paragraph.version:
                text = override.replacement_text
            else:
                conflicts.append(
                    OverrideConflict(
                        paragraph.paragraph_id,
                        paragraph.version,
                        override.base_version,
                        "base_version_changed",
                    )
                )
        undeclared = set(_placeholders(text)) - set(section.required_variables)
        if undeclared:
            raise TemplateCatalogError(
                f"{paragraph.paragraph_id}: override uses undeclared placeholders: {', '.join(sorted(undeclared))}"
            )
        rendered.append(text.format_map(values))
    return RenderedSection(
        section_id=section.section_id,
        title=section.title,
        text="\n\n".join(rendered),
        paragraphs=tuple(rendered),
        missing_variables=missing,
        override_conflicts=tuple(conflicts),
        inclusion_condition=section.inclusion_condition,
        normative_keys=section.normative_keys,
    )

