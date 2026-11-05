"""Deterministic composition and completeness checks for a full PPRk bundle.

The composer does not perform engineering calculations.  It selects already
verified context values, standard template sections and approved reference
assets, then assigns stable document identities and independent numbering
sequences for explanatory pages and graphical sheets.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re
import unicodedata
from datetime import date
from typing import Mapping, Sequence

from .pprk_assets import ASSET_ROOT, PPRKAssetRecord, load_asset_manifest, safe_asset_path
from .pprk_context import PPRKActiveLoad, PPRKContext
from .pprk_models import (
    CompletenessIssue,
    PPRKReleaseConfig,
    ReleaseStatus,
    meaningful_evidence_text,
)
from .pprk_regulations import PPRKRegulation, load_release_regulations
from .pprk_templates import (
    MISSING_VALUE_TEMPLATE,
    RenderedSection,
    TemplateSection,
    render_template_text,
)


@dataclass(frozen=True)
class PPRKAssetIdentity:
    asset_id: str
    sha256: str
    category: str
    quality_status: str


@dataclass(frozen=True)
class PPRKSheet:
    sheet_id: str
    title: str
    kind: str
    page_number: int | None = None
    designation: str = ""
    section_id: str = ""
    fields: tuple[tuple[str, str], ...] = ()
    approval_slots: tuple[tuple[str, str, str, str, str], ...] = ()
    asset_identities: tuple[PPRKAssetIdentity, ...] = ()
    reference_keys: tuple[str, ...] = ()
    approval_roles: tuple[str, ...] = ()

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(item.asset_id for item in self.asset_identities)


@dataclass(frozen=True)
class PPRKDocumentPart:
    part_id: str
    title: str
    kind: str
    sheets: tuple[PPRKSheet, ...]
    rendered_text: str = ""
    include_reason: str = ""


@dataclass(frozen=True)
class PPRKContentsEntry:
    target_id: str
    part_id: str
    title: str
    number: str
    kind: str


@dataclass(frozen=True)
class PPRKPlacementBinding:
    legacy_configuration_reference: str
    model: str
    x_m: float
    y_m: float
    max_radius_m: float
    jib_length_m: float
    required_hook_height_m: float
    jib_level_m: float | None


@dataclass(frozen=True)
class PPRKCalculationBinding:
    protocol_input_sha256: str
    protocol_result_sha256: str
    placements: tuple[PPRKPlacementBinding, ...]
    scenario_render_sha256: str = ""
    scenario_render_snapshot: str = ""
    verified_danger_zone_offset_m: float | None = None
    scenario_index: int = 0
    protocol_run_id: str = ""


@dataclass(frozen=True)
class PPRKRenderRequisites:
    organization: str
    project_code: str
    author: str
    checked_by: str
    approved_by: str
    issue_date: str


@dataclass(frozen=True)
class PPRKBundle:
    parts: tuple[PPRKDocumentPart, ...]
    contents: tuple[PPRKContentsEntry, ...]
    included_section_ids: tuple[str, ...]
    inclusion_reasons: tuple[tuple[str, str], ...]
    exclusion_reasons: tuple[tuple[str, str], ...]
    completeness_issues: tuple[CompletenessIssue, ...]
    requested_status: ReleaseStatus
    effective_status: ReleaseStatus
    production_allowed: bool
    preliminary_available: bool = True
    calculation_binding: PPRKCalculationBinding | None = None
    active_loads: tuple[PPRKActiveLoad, ...] | None = None
    regulations: tuple[PPRKRegulation, ...] = ()
    render_requisites: PPRKRenderRequisites | None = None
    required_external_document_ids: tuple[str, ...] = ()

    def part(self, part_id: str) -> PPRKDocumentPart:
        for item in self.parts:
            if item.part_id == part_id:
                return item
        raise KeyError(part_id)

    def sheet(self, sheet_id: str) -> PPRKSheet:
        for part in self.parts:
            for sheet in part.sheets:
                if sheet.sheet_id == sheet_id:
                    return sheet
        raise KeyError(sheet_id)


def check_completeness(bundle: PPRKBundle) -> tuple[CompletenessIssue, ...]:
    """Return the immutable issue register used to gate final production status."""

    return bundle.completeness_issues


def effective_render_project(bundle, project):
    """Isolate all legacy drawing primitives behind the frozen release card."""
    from copy import deepcopy
    snapshot = deepcopy(project)
    requisites = bundle.render_requisites
    if requisites is not None:
        for name in ("organization", "project_code", "author", "checked_by", "approved_by"):
            setattr(snapshot, name, getattr(requisites, name))
    return snapshot


def _calculation_binding(context: PPRKContext) -> PPRKCalculationBinding | None:
    # Synthetic/legacy contexts predate trace binding.  Production contexts
    # created by ``build_pprk_context`` always carry crane traces.
    if not context.traces:
        return None
    legacy = tuple(context.values.get("legacy_configuration_references", ()) or ())
    models = tuple(context.values.get("crane_models", ()) or ())
    placements: list[PPRKPlacementBinding] = []
    for index, crane_id in enumerate(context.crane_ids):
        def traced(field_id: str, *, optional: bool = False):
            try:
                return context.trace(field_id, crane_id=crane_id).value
            except KeyError:
                if optional:
                    return None
                raise ValueError(f"Для привязки расчётного сценария отсутствует трасса {field_id}: {crane_id}")

        jib_level = traced("crane.jib_level_m", optional=True)
        placements.append(
            PPRKPlacementBinding(
                str(legacy[index]) if index < len(legacy) else "",
                str(models[index]) if index < len(models) else "",
                float(traced("crane.x_m")),
                float(traced("crane.y_m")),
                float(traced("crane.max_radius_m")),
                float(traced("crane.jib_length_m")),
                float(traced("crane.required_hook_height_m")),
                float(jib_level) if jib_level is not None else None,
            )
        )
    return PPRKCalculationBinding(
        context.protocol_input_sha256,
        context.protocol_result_sha256,
        tuple(placements),
        context.scenario_render_sha256,
        context.scenario_render_snapshot,
        (
            float(context.values["verified_danger_zone_offset_m"])
            if context.values.get("verified_danger_zone_offset_m") is not None
            else None
        ),
        context.scenario_index,
        context.protocol_run_id,
    )


def _is_present(value: object) -> bool:
    return value not in (None, "", (), [], {})


def _condition_met(condition: str, values: Mapping[str, object]) -> bool:
    if condition == "always":
        return True
    if condition == "has_load_longer_than_3m":
        value = values.get("max_load_length_m")
        return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 3.0
    if condition == "has_concrete_bucket":
        if _is_present(values.get("bucket_volume_m3")):
            return True
        return any(
            token in str(name).casefold()
            for name in values.get("active_loads", ()) or ()
            for token in ("бадь", "бетон")
        )
    if condition == "has_receiving_platforms":
        return _is_present(values.get("receiving_platform_ids"))
    if condition == "has_opening_delivery":
        return _is_present(values.get("opening_ids"))
    if condition == "has_joint_operations":
        count = values.get("crane_count", 0)
        return (isinstance(count, (int, float)) and count > 1) or _is_present(
            values.get("joint_work_schedule")
        )
    return False


def _clean_approval_field(value: object) -> str:
    if not isinstance(value, str):
        return ""
    without_controls = "".join(
        character
        for character in value
        if unicodedata.category(character) not in {"Cc", "Cf"}
    )
    return " ".join(without_controls.replace("\u00a0", " ").split())


def _approval_rows(config: PPRKReleaseConfig) -> tuple[tuple[str, str, str, str, str], ...]:
    rows = [
        tuple(
            _clean_approval_field(value)
            for value in (
                slot.organization,
                slot.position,
                slot.full_name,
                slot.signature,
                slot.date,
            )
        )
        for slot in config.approvals[:8]
    ]
    rows.extend(("", "", "", "", "") for _ in range(8 - len(rows)))
    return tuple(rows)


def _approval_role(slot):
    aliases = {"checker": "CHECKER", "проверил": "CHECKER", "проверяющий": "CHECKER",
               "approver": "APPROVER", "утвердил": "APPROVER", "утверждающий": "APPROVER"}
    return aliases.get(_clean_approval_field(slot.role or slot.position).casefold(), "")


def _with_page_numbers(parts: Sequence[PPRKDocumentPart]) -> tuple[PPRKDocumentPart, ...]:
    page = 1
    graphical = 1
    result: list[PPRKDocumentPart] = []
    for part in parts:
        sheets: list[PPRKSheet] = []
        for sheet in part.sheets:
            if part.kind == "graphical":
                sheets.append(replace(sheet, page_number=None, designation=f"ГЧ-{graphical:02d}"))
                graphical += 1
            else:
                sheets.append(replace(sheet, page_number=page))
                page += 1
        result.append(replace(part, sheets=tuple(sheets)))
    return tuple(result)


_ASSET_APPENDIX_MAP = {
    "SLINGING_CARDS": "slinging",
    "STORAGE_SCHEMES": "storage",
    "SAFETY_SIGNS": "safety_signs",
    "HAND_SIGNALS": "hand_signals",
    "FENCING": "fencing",
    "PROTECTIVE_SCREENS": "protective_screens",
}

_STATUS_ORDER = (
    ReleaseStatus.PRELIMINARY,
    ReleaseStatus.REVIEW,
    ReleaseStatus.COORDINATION,
    ReleaseStatus.APPROVED,
    ReleaseStatus.PRODUCTION,
)
_TECHNICAL_SCOPE = frozenset(
    (ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION)
)
_APPROVAL_SCOPE = frozenset((ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION))
_EXTERNAL_SCOPE = _TECHNICAL_SCOPE


def _effective_status(
    requested: ReleaseStatus, blocked_statuses: frozenset[ReleaseStatus]
) -> ReleaseStatus:
    requested_index = _STATUS_ORDER.index(requested)
    for candidate in reversed(_STATUS_ORDER[: requested_index + 1]):
        if candidate not in blocked_statuses:
            return candidate
    return ReleaseStatus.PRELIMINARY


def compose_pprk(
    context: PPRKContext,
    templates: Sequence[TemplateSection],
    assets: Sequence[PPRKAssetRecord],
    config: PPRKReleaseConfig,
) -> PPRKBundle:
    """Compose an immutable PPRk bundle from existing verified inputs."""

    values = dict(context.values)
    values.setdefault("object_name", context.object_name)
    values.setdefault("object_address", context.object_address)
    requested_status = ReleaseStatus(config.status)
    issues: list[CompletenessIssue] = []
    issue_scopes: list[frozenset[ReleaseStatus]] = []
    issue_keys: set[tuple[str, str, str]] = set()

    def issue(
        code: str,
        message: str,
        field_id: str,
        *,
        scope: frozenset[ReleaseStatus] = _TECHNICAL_SCOPE,
    ) -> None:
        key = (code, field_id, message)
        if key not in issue_keys:
            issues.append(
                CompletenessIssue(code, message, requested_status in scope, field_id)
            )
            issue_scopes.append(scope)
            issue_keys.add(key)

    for context_issue in context.completeness_issues:
        issue(context_issue.code, context_issue.message, context_issue.field_id)

    object_address = str(config.object_address or context.object_address).strip()
    if not object_address:
        object_address = MISSING_VALUE_TEMPLATE.format(name="object_address")
        issue("PPRK_ADDRESS_REQUIRED", "Не заполнен адрес объекта.", "object_address")
    values["object_address"] = object_address
    values["object_name"] = str(values.get("object_name") or context.object_name)

    crane_model = str(values.get("crane_model") or "").strip()
    configurations_value = values.get("crane_configurations", ())
    if isinstance(configurations_value, str):
        crane_configurations = configurations_value.strip()
    else:
        crane_configurations = "; ".join(str(item) for item in configurations_value or ())
    try:
        issue_date = date.fromisoformat(config.issue_date)
    except (TypeError, ValueError):
        issue_date = None
    title_fields = (
        ("title", config.title),
        ("lifting_equipment_type", config.lifting_equipment_type),
        ("crane_model", crane_model),
        ("crane_configurations", crane_configurations),
        ("approval_marks", "УТВЕРЖДАЮ / СОГЛАСОВАНО"),
        ("object_name", str(values["object_name"])),
        ("object_address", object_address),
        ("organization", config.developer_organization or context.organization),
        ("project_code", config.project_code or context.project_code),
        ("developer_position", config.developer_position),
        ("developer_name", config.developer_name),
        ("developer_date", config.developer_date),
        ("manager_position", config.manager_position),
        ("manager_name", config.manager_name),
        ("manager_date", config.manager_date),
        ("issue_city", config.issue_city),
        ("issue_year", str(issue_date.year) if issue_date else ("" if config.issue_year is None else str(config.issue_year))),
        ("issue_date", issue_date.isoformat() if issue_date else ""),
    )
    for field_name, field_value in title_fields:
        if field_name != "approval_marks" and not str(field_value).strip():
            issue(
                "PPRK_TITLE_FIELD_REQUIRED",
                f"Не заполнено обязательное поле титульного листа: {field_name}.",
                f"title/{field_name}",
            )

    service_parts = [
        PPRKDocumentPart(
            "service.title",
            "Титульный лист",
            "service",
            (
                PPRKSheet(
                    "service.title",
                    "Титульный лист",
                    "service",
                    fields=title_fields,
                ),
            ),
            include_reason="required",
        ),
        PPRKDocumentPart(
            "service.approvals",
            "Лист согласований",
            "service",
            (
                PPRKSheet(
                    "service.approvals",
                    "Лист согласований",
                    "service",
                    approval_slots=_approval_rows(config),
                    approval_roles=tuple(_approval_role(slot) for slot in config.approvals[:8]),
                ),
            ),
            include_reason="required",
        ),
        PPRKDocumentPart(
            "service.familiarization",
            "Лист регистрации ознакомления",
            "service",
            (PPRKSheet("service.familiarization", "Лист регистрации ознакомления", "service"),),
            include_reason="required",
        ),
        PPRKDocumentPart(
            "service.contents",
            "Состав проекта",
            "service",
            (PPRKSheet("service.contents", "Состав проекта", "service"),),
            include_reason="required",
        ),
    ]

    approval_rows = _approval_rows(config)
    if len(config.approvals) != 8:
        issue(
            "PPRK_APPROVAL_COUNT_INVALID",
            "Лист согласований нормализован до восьми блоков; исходное количество некорректно.",
            "approvals",
            scope=_APPROVAL_SCOPE,
        )
    if any(not all(row) for row in approval_rows):
        issue(
            "PPRK_APPROVALS_INCOMPLETE",
            "Лист согласований содержит незаполненные обязательные поля.",
            "approvals",
            scope=_APPROVAL_SCOPE,
        )
    role_names = {}
    for role in ("CHECKER", "APPROVER"):
        matching = [slot for slot in config.approvals[:8] if _approval_role(slot) == role]
        valid = len(matching) == 1 and meaningful_evidence_text(matching[0].full_name)
        role_names[role] = _clean_approval_field(matching[0].full_name) if valid else ""
        if not valid:
            issue("PPRK_APPROVAL_ROLE_REQUIRED", f"Укажите одного подписанта с явной ролью {role}.",
                  f"approvals/{role}", scope=_APPROVAL_SCOPE)

    manual_include = set(config.included_section_ids)
    manual_exclude = set(config.excluded_section_ids)
    known_section_ids = {section.section_id for section in templates}
    for unknown_id in sorted((manual_include | manual_exclude) - known_section_ids):
        issue(
            "PPRK_UNKNOWN_SECTION_ID",
            f"В настройках выпуска указан неизвестный раздел: {unknown_id}.",
            f"sections/{unknown_id}",
        )
    included_sections: list[TemplateSection] = []
    inclusion_reasons: list[tuple[str, str]] = []
    exclusion_reasons: list[tuple[str, str]] = []
    rendered_sections: dict[str, RenderedSection] = {}
    for section in templates:
        condition_applies = _condition_met(section.inclusion_condition, values)
        required_now = section.inclusion_condition == "always" or condition_applies
        if section.section_id in manual_exclude and required_now:
            issue(
                "PPRK_REQUIRED_SECTION_EXCLUSION",
                f"Обязательный раздел «{section.title}» нельзя исключить без экспертного решения.",
                f"sections/{section.section_id}",
            )
            reason = "required:no_expert_decision"
            included = True
        elif section.section_id in manual_exclude:
            exclusion_reasons.append((section.section_id, "manual_exclude:not_applicable"))
            included = False
            reason = ""
        elif condition_applies:
            included = True
            reason = "required:always" if section.inclusion_condition == "always" else f"condition:{section.inclusion_condition}"
        elif section.section_id in manual_include:
            included = True
            reason = "manual_include"
        else:
            included = False
            reason = ""
            exclusion_reasons.append((section.section_id, f"condition_not_met:{section.inclusion_condition}"))
        if not included:
            continue
        included_sections.append(section)
        inclusion_reasons.append((section.section_id, reason))
        rendered = render_template_text(
            section.section_id,
            values,
            config.overrides,
            catalog=templates,
        )
        rendered_sections[section.section_id] = rendered
        for variable in rendered.missing_variables:
            issue(
                "PPRK_TEMPLATE_VALUE_REQUIRED",
                f"Для раздела «{section.title}» не заполнено значение {variable}.",
                f"sections/{section.section_id}/{variable}",
            )
        for conflict in rendered.override_conflicts:
            issue(
                "PPRK_OVERRIDE_CONFLICT",
                f"Ручная правка {conflict.paragraph_id} требует разрешения конфликта: {conflict.reason}.",
                f"overrides/{conflict.paragraph_id}",
            )

    required_regulations = {key for section in included_sections for key in section.normative_keys}
    registry = {record.rule_id: record for record in load_release_regulations()}
    regulations = tuple(registry[key] for key in sorted(required_regulations) if key in registry)
    if issue_date is None:
        issue("PPRK_ISSUE_DATE_REQUIRED", "Укажите точную дату выпуска для проверки действия нормативов.", "title/issue_date")
    elif config.issue_year is not None and config.issue_year != issue_date.year:
        issue("PPRK_ISSUE_YEAR_MISMATCH", "Год титула не соответствует точной дате выпуска; титул использует год даты.", "title/issue_year")
    for key in sorted(required_regulations - registry.keys()):
        issue("PPRK_REGULATION_REQUIRED", f"Нет нормативного документа {key} в реестре.", f"regulations/{key}")
    for record in regulations:
        if not record.verified:
            issue("PPRK_REGULATION_UNVERIFIED", f"{record.rule_id}: нормативный статус не проверен ({record.verification_status}).", f"regulations/{record.rule_id}")
        if issue_date and ((record.valid_until and issue_date > date.fromisoformat(record.valid_until))
                           or (record.valid_from and issue_date < date.fromisoformat(record.valid_from))):
            issue("PPRK_REGULATION_EXPIRED", f"{record.rule_id}: документ не действует на дату выпуска {config.issue_date}.", f"regulations/{record.rule_id}")

    try:
        canonical_assets = {asset.asset_id: asset for asset in load_asset_manifest()}
    except (OSError, ValueError, TypeError):
        canonical_assets = {}
        issue(
            "PPRK_ASSET_LIBRARY_INVALID",
            "Не удалось прочитать авторитетный реестр типовых приложений.",
            "assets/manifest",
        )
    valid_assets: dict[str, PPRKAssetIdentity] = {}
    for asset in assets:
        valid = True
        canonical = canonical_assets.get(asset.asset_id)
        if canonical is None or asset != canonical:
            valid = False
        if (
            not re.fullmatch(r"[0-9a-f]{64}", str(asset.sha256))
            or asset.quality_status != "verified"
            or not asset.category
        ):
            valid = False
        expected_category = asset.asset_id if asset.asset_id in set(_ASSET_APPENDIX_MAP.values()) else None
        if expected_category is not None and asset.category != expected_category:
            valid = False
        if asset.asset_id in valid_assets:
            valid = False
        try:
            asset_path = safe_asset_path(ASSET_ROOT, asset.file_name)
            if (
                not asset_path.is_file()
                or hashlib.sha256(asset_path.read_bytes()).hexdigest() != asset.sha256
            ):
                valid = False
        except (OSError, ValueError):
            valid = False
        if not valid:
            issue(
                "PPRK_ASSET_INVALID",
                f"Ресурс {asset.asset_id} не прошел проверку идентичности и статуса.",
                f"assets/{asset.asset_id}",
            )
            continue
        approved = canonical_assets[asset.asset_id]
        valid_assets[asset.asset_id] = PPRKAssetIdentity(
            approved.asset_id,
            approved.sha256,
            approved.category,
            approved.quality_status,
        )
    section_parts: list[PPRKDocumentPart] = []
    sheet_link_order: list[str] = []
    appendix_link_order: list[str] = []
    tie_levels = values.get("tie_levels_m", ()) or ()
    external_by_id = {document.document_id: document for document in config.external_documents}
    tie_document = external_by_id.get("tie_in_project")
    tie_document_ready = bool(
        tie_document
        and tie_document.present
        and tie_document.verification_status == "VERIFIED"
        and re.fullmatch(r"[0-9a-f]{64}", tie_document.verified_sha256)
    )
    mandatory = {"crane_passport": "Паспорт крана и грузовая характеристика",
                 "foundation_project": "Проект фундамента крана",
                 "erection_project": "Проект монтажа и демонтажа крана"}
    screen_required = "PROTECTIVE_SCREEN" in (values.get("verified_mitigation_types", ()) or ())
    if screen_required:
        mandatory["protective_screen_project"] = "Проект и расчёт защитного экрана"
    for document_id, title in mandatory.items():
        document = external_by_id.get(document_id)
        if not (document and document.present and document.verification_status == "VERIFIED"
                and re.fullmatch(r"[0-9a-f]{64}", document.verified_sha256)):
            issue("PPRK_EXTERNAL_DOCUMENT_REQUIRED", f"Требуется проверенный обязательный документ: {title}.",
                  f"external_documents/{document_id}", scope=_EXTERNAL_SCOPE)
    if tie_levels and not tie_document_ready:
        issue(
            "PPRK_TIE_PROJECT_REQUIRED",
            "Для окончательного выпуска требуется проверенный внешний проект крепления крана к зданию.",
            "external_documents/tie_in_project",
            scope=_EXTERNAL_SCOPE,
        )
    for document in config.external_documents:
        if document.required and (not document.present or document.verification_status != "VERIFIED"
                                  or not re.fullmatch(r"[0-9a-f]{64}", document.verified_sha256)):
            issue(
                "PPRK_EXTERNAL_DOCUMENT_REQUIRED",
                f"Обязательный внешний документ «{document.title}» отсутствует или не проверен.",
                f"external_documents/{document.document_id}",
                scope=_EXTERNAL_SCOPE,
            )
    if screen_required:
        appendix_link_order.append("PROTECTIVE_SCREENS")
    for section in included_sections:
        for paragraph in section.paragraphs:
            for reference in paragraph.sheet_links:
                if reference not in sheet_link_order:
                    sheet_link_order.append(reference)
            for reference in paragraph.appendix_links:
                if reference == "TIE_IN_PROJECT":
                    continue
                if reference not in appendix_link_order:
                    appendix_link_order.append(reference)
        section_assets: tuple[PPRKAssetIdentity, ...] = ()
        if section.section_id == "concrete_bucket":
            if "slinging" in valid_assets:
                section_assets = (valid_assets["slinging"],)
            else:
                issue(
                    "PPRK_ASSET_REQUIRED",
                    "Для бетонной бадьи отсутствует проверенная карточка строповки.",
                    "assets/slinging",
                )
        rendered = rendered_sections[section.section_id]
        text = rendered.text
        if section.section_id == "basis_and_regulations":
            text += "\n\nНормативный реестр выпуска\n\n" + "\n\n".join(record.release_text() for record in regulations)
        resolved_references = tuple(
            dict.fromkeys(
                [
                    f"drawing.{reference}"
                    for paragraph in section.paragraphs
                    for reference in paragraph.sheet_links
                ]
                + [
                    (
                        "external.tie_in_project"
                        if reference == "TIE_IN_PROJECT"
                        else f"appendix.{reference}"
                    )
                    for paragraph in section.paragraphs
                    for reference in paragraph.appendix_links
                    if reference != "REGULATION_REGISTER"
                    if reference != "TIE_IN_PROJECT" or (tie_levels and tie_document_ready)
                ]
            )
        )
        section_parts.append(
            PPRKDocumentPart(
                f"section.{section.section_id}",
                section.title,
                "note",
                (
                    PPRKSheet(
                        f"section.{section.section_id}",
                        section.title,
                        "note",
                        section_id=section.section_id,
                        asset_identities=section_assets,
                        reference_keys=resolved_references,
                    ),
                ),
                rendered_text=text,
                include_reason=dict(inclusion_reasons)[section.section_id],
            )
        )

    # CALCULATED_DRAWINGS is a template-level aggregate link, not a physical
    # sheet. Resolve it to the concrete drawing targets collected from the
    # remaining sections so it can never become an unrendered phantom page.
    if "CALCULATED_DRAWINGS" in sheet_link_order:
        sheet_link_order = [reference for reference in sheet_link_order if reference != "CALCULATED_DRAWINGS"]
        concrete_keys = tuple(f"drawing.{reference}" for reference in sheet_link_order)
        resolved_parts: list[PPRKDocumentPart] = []
        for part in section_parts:
            sheets = []
            for sheet in part.sheets:
                keys: list[str] = []
                for key in sheet.reference_keys:
                    replacements = concrete_keys if key == "drawing.CALCULATED_DRAWINGS" else (key,)
                    for replacement in replacements:
                        if replacement not in keys:
                            keys.append(replacement)
                sheets.append(replace(sheet, reference_keys=tuple(keys)))
            resolved_parts.append(replace(part, sheets=tuple(sheets)))
        section_parts = resolved_parts

    graphical_parts = [
        PPRKDocumentPart(
            f"drawing.{reference}",
            reference,
            "graphical",
            (PPRKSheet(f"drawing.{reference}", reference, "graphical"),),
            include_reason="template_reference",
        )
        for reference in sheet_link_order
    ]
    appendix_parts: list[PPRKDocumentPart] = []
    for reference in appendix_link_order:
        if reference == "REGULATION_REGISTER":
            continue
        identity: tuple[PPRKAssetIdentity, ...] = ()
        required_asset_id = _ASSET_APPENDIX_MAP.get(reference)
        if required_asset_id:
            asset_identity = valid_assets.get(required_asset_id)
            if asset_identity is None:
                issue(
                    "PPRK_ASSET_REQUIRED",
                    f"Для приложения {reference} отсутствует проверенный ресурс {required_asset_id}.",
                    f"assets/{required_asset_id}",
                )
            else:
                identity = (asset_identity,)
        appendix_parts.append(
            PPRKDocumentPart(
                f"appendix.{reference}",
                reference,
                "appendix",
                (
                    PPRKSheet(
                        f"appendix.{reference}",
                        reference,
                        "appendix",
                        asset_identities=identity,
                    ),
                ),
                include_reason="template_reference",
            )
        )

    external_parts = [
        PPRKDocumentPart(
            f"external.{document.document_id}",
            document.title,
            "external",
            (
                PPRKSheet(
                    f"external.{document.document_id}",
                    document.title,
                    "external",
                    fields=(("attachment_path", document.attachment_path),),
                ),
            ),
            include_reason="configured_external_document",
        )
        for document in sorted(
            (item for item in config.external_documents if item.present),
            key=lambda item: (item.appendix_order is None, item.appendix_order or 0, item.document_id),
        )
    ]

    numbered_parts = _with_page_numbers(
        (*service_parts, *section_parts, *graphical_parts, *appendix_parts, *external_parts)
    )
    contents: list[PPRKContentsEntry] = []
    for part in numbered_parts:
        for sheet in part.sheets:
            number = sheet.designation or str(sheet.page_number or "")
            contents.append(PPRKContentsEntry(sheet.sheet_id, part.part_id, sheet.title, number, part.kind))
    contents_count = str(len(contents))
    numbered_parts = tuple(
        replace(
            part,
            sheets=tuple(
                replace(sheet, fields=(("entry_count", contents_count),))
                if sheet.sheet_id == "service.contents"
                else sheet
                for sheet in part.sheets
            ),
        )
        for part in numbered_parts
    )

    blocked_statuses = frozenset(status for scope in issue_scopes for status in scope)
    production_allowed = ReleaseStatus.PRODUCTION not in blocked_statuses
    effective_status = _effective_status(requested_status, blocked_statuses)
    return PPRKBundle(
        numbered_parts,
        tuple(contents),
        tuple(section.section_id for section in included_sections),
        tuple(inclusion_reasons),
        tuple(exclusion_reasons),
        tuple(issues),
        requested_status,
        effective_status,
        production_allowed,
        True,
        _calculation_binding(context),
        context.active_loads,
        regulations,
        PPRKRenderRequisites(str(config.developer_organization or context.organization),
                            str(config.project_code or context.project_code), config.developer_name,
                            role_names["CHECKER"], role_names["APPROVER"], config.issue_date),
        (*mandatory, *(("tie_in_project",) if tie_levels else ())),
    )
