"""Headless state and publication boundary of the desktop PPRk release editor."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from .engine.protocol import sha256_hex
from .engine.integration import IntegrationStatus, release_blockers
from .engine.verification import VerificationStatus
from .models import ProjectInput, ScenarioResult
from .pprk_appendices import apply_appendix_completeness, plan_asset_appendices
from .pprk_assets import ASSET_ROOT, load_asset_manifest
from .pprk_composer import PPRKBundle, compose_pprk
from .pprk_context import build_pprk_context, scenario_render_snapshot
from .pprk_merge import inspect_external_document
from .pprk_sheets import plan_calculated_sheets
from .pprk_models import ApprovalSlot, CompletenessIssue, PPRKReleaseConfig, ReleaseStatus
from .pprk_templates import DEFAULT_REGISTRY_PATH, TemplateCatalogError, load_template_catalog
from .report import generate_report
from .pprk_release_validation import ForbiddenReferenceError, UnsafePDFMetadataError, validate_release_inputs, validate_release_pdf, validate_underlays


RELEASE_FIELDS = {
    "title": "Название документа", "object_address": "Адрес объекта",
    "lifting_equipment_type": "Тип подъёмного сооружения",
    "developer_organization": "Организация-разработчик", "project_code": "Шифр проекта",
    "developer_position": "Должность разработчика", "developer_name": "ФИО разработчика",
    "developer_date": "Дата разработки", "manager_position": "Должность руководителя",
    "manager_name": "ФИО руководителя", "manager_date": "Дата утверждения",
    "issue_city": "Город выпуска", "issue_year": "Год выпуска", "issue_date": "Дата выпуска (ГГГГ-ММ-ДД)",
    "project_basis": "Основание для разработки", "plan_sheet_refs": "Листы стройгенплана",
    "responsible_fire_safety": "Ответственный за пожарную безопасность",
    "max_wind_speed_m_s": "Предельная скорость ветра, м/с",
    "fall_protection_system": "Система защиты от падения", "power_supply_scheme": "Схема электроснабжения",
    "waste_plan": "План обращения с отходами", "external_document_register": "Реестр внешних документов",
    "receiving_platform_ids": "Приёмные площадки (ID через запятую)", "opening_ids": "Проёмы (ID через запятую)",
    "bucket_volume_m3": "Объём бадьи, м³",
}


def approval_rows(slots, action=None, index=None):
    rows = list(slots[:8])
    rows.extend(ApprovalSlot() for _ in range(8 - len(rows)))
    if action == "reset":
        return [ApprovalSlot() for _ in range(8)]
    if action == "remove" and index is not None:
        rows.pop(index)
        rows.append(ApprovalSlot())
    return rows


def edit_release_fields(config, values):
    changes = {}
    for key, raw in values.items():
        value = raw.strip()
        if key in ("max_wind_speed_m_s", "bucket_volume_m3", "issue_year"):
            try:
                numeric = int(value) if key == "issue_year" else float(value.replace(",", "."))
                if not math.isfinite(numeric) or numeric <= 0:
                    raise ValueError
            except ValueError:
                if value:
                    raise ValueError(f"{RELEASE_FIELDS[key]} — введите положительное число.") from None
                numeric = None
            changes[key] = numeric
        elif key in ("opening_ids", "receiving_platform_ids", "included_section_ids", "excluded_section_ids"):
            changes[key] = [item.strip() for item in value.split(",") if item.strip()]
        else:
            changes[key] = value
    return replace(config, **changes)


def release_resource_paths():
    # Include actual catalog, manifest and image bytes, even when names and metadata stay the same.
    return [DEFAULT_REGISTRY_PATH, *sorted(p for p in ASSET_ROOT.rglob("*") if p.is_file())]


def source_digest(path):
    try:
        with Path(path).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError:
        return None


def release_fingerprint(project, scenario, verification, index):
    sources = [project.source_plan_pdf, project.source_section_pdf]
    sources.extend(doc.attachment_path for doc in project.pprk_release.external_documents)
    paths = [*release_resource_paths(), *(Path(source) for source in sources if source)]
    hashes = {str(path): source_digest(path) for path in paths}
    return sha256_hex((project.to_dict(), index, scenario_render_snapshot(scenario),
                       scenario_render_snapshot(verification), hashes))


_CONDITIONS = {
    "has_load_longer_than_3m": "длина груза превышает 3 м",
    "has_concrete_bucket": "применяется бетонная бадья",
    "has_receiving_platforms": "указаны приёмные площадки",
    "has_opening_delivery": "указаны проёмы подачи",
    "has_joint_operations": "предусмотрена совместная работа кранов",
}


def _reason(reason):
    fixed = {"required:always": "Обязательный раздел",
             "required:no_expert_decision": "Обязателен для проекта, исключение отклонено",
             "manual_include": "Включён вручную",
             "manual_exclude:not_applicable": "Неприменимый раздел исключён вручную"}
    if reason in fixed:
        return fixed[reason]
    rule, _, condition = reason.partition(":")
    label = "Условие выполнено" if rule == "condition" else "Условие не выполнено"
    return f"{label}: {_CONDITIONS.get(condition, condition)}"


@dataclass(frozen=True)
class ReleaseView:
    project: ProjectInput
    scenario: ScenarioResult
    bundle: PPRKBundle
    sections: tuple
    issues: tuple[CompletenessIssue, ...]
    document_status: str | None

    def require_requested_status(self):
        if self.bundle.requested_status != self.bundle.effective_status or any(i.blocking for i in self.issues):
            reasons = "\n".join(i.message for i in self.issues if i.blocking)
            raise ValueError(f"Запрошенный статус недоступен. Исправьте замечания комплектности.\n{reasons}")


def _reject_unsafe_external_issues(issues):
    for issue in issues:
        if issue.code == "PPRK_UNSAFE_PDF_METADATA":
            raise UnsafePDFMetadataError(issue.message)
        if issue.code == "PPRK_FORBIDDEN_REFERENCE":
            raise ForbiddenReferenceError(issue.message)


def require_saveable_release(release, verification):
    """Resolve status once for GUI saves; diagnostic previews stay available.

    A genuine expert protocol may accompany an explicit preliminary draft.
    Rejected/failed calculations and missing protocols never enter that path.
    Requested/effective status gates remain owned by the prepared release.
    """
    validate_underlays(release.project)
    for document in release.project.pprk_release.external_documents:
        _reject_unsafe_external_issues(inspect_external_document(document))
    release.require_requested_status()
    if release.scenario.joint_plan is not None:
        from .report import _joint_vertical_geometry
        _joint_vertical_geometry(release.scenario)
    report = verification.engine_result.verification if verification.engine_result else None
    if (verification.status == IntegrationStatus.REJECTED
            or (report and (report.status == VerificationStatus.INVALID
                            or any(not c.passed and not c.review_required for c in report.checks)))):
        raise ValueError("Вариант отклонён независимой проверкой и не может быть сохранён как ППРк.")
    if verification.protocol is None:
        raise ValueError("Для сохранения выполните расчёт с протоколом проверки; экспертный вариант без протокола недоступен.")
    canonical_protocol = getattr(verification.engine_result, "protocol", None)
    try:
        # Reuse the full canonical serializer used by release fingerprints.
        # Input/result hash fields alone omit metadata and can survive a nested
        # mutation. Compare every serialized value, without object identity.
        matches_canonical = (canonical_protocol is not None and
                             scenario_render_snapshot(verification.protocol) ==
                             scenario_render_snapshot(canonical_protocol))
    except (TypeError, ValueError):
        matches_canonical = False
    if not matches_canonical:
        raise ValueError("Сохраняемый протокол не соответствует каноническому протоколу выбранного расчёта. Выполните расчёт повторно.")
    expert_draft = (verification.status == IntegrationStatus.EXPERT_REVIEW_REQUIRED
                    and release.bundle.requested_status == ReleaseStatus.PRELIMINARY and report is not None)
    if not verification.release_allowed and not expert_draft:
        raise ValueError("\n".join(release_blockers((verification,), 0)))


def _pending_drawings(bundle, project, scenario):
    missing = {}
    if project.work_points and bundle.calculation_binding.verified_danger_zone_offset_m is None:
        missing["drawing.SITE_PLAN"] = "Нет подтверждённого вылета опасной зоны."
    if not scenario.placements or any(p.sozr_plan is None for p in scenario.placements):
        for sheet in ("drawing.ROUTE_PLAN", "drawing.SOZR_PLAN"):
            missing[sheet] = "Отсутствуют подтверждённые данные СОЗР выбранного крана."
    if any(len(p.tie_in_levels_m) > min(len(p.tie_in_stage_sections), len(p.tie_nearest_floors))
           for p in scenario.placements):
        missing["drawing.VERTICAL_SECTION"] = "В протоколе нет полной ведомости пристежек."
    if scenario.joint_plan is None:
        missing["drawing.JOINT_WORK_SCHEDULE"] = "Нет подтверждённого графика совместной работы."
    parts, issues = [], []
    for part in bundle.parts:
        if part.kind == "graphical" and part.part_id not in missing:
            try:
                plan_calculated_sheets(replace(bundle, parts=(part,)), project, scenario)
            except ValueError as exc:
                missing[part.part_id] = str(exc)
        if part.part_id in missing:
            text = missing[part.part_id]
            issues.append(CompletenessIssue("PPRK_DRAWING_DATA_REQUIRED", text, True, part.part_id))
            sheet, = part.sheets
            part = replace(part, sheets=(replace(sheet, fields=(*sheet.fields, ("pending_reason", text))),))
        parts.append(part)
    return replace(bundle, parts=tuple(parts)), tuple(issues)


def require_selected_protocol(index, verification):
    if verification.scenario_index != index:
        raise ValueError("Протокол относится к другому варианту. Выполните расчёт повторно.")


def _preflight_internal_text(bundle, appendices, documents):
    """Exercise the production fitters before a release can be called saveable.

    Physical contents paginate independently of the provisional leaf. Check
    their fixed-size cells individually rather than imposing a one-leaf limit.
    The service/note proof contains no images or engineering recalculation.
    """
    import io
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.units import mm
    from .pprk_text_report import _draw_cell_text, render_pprk_text_report
    proof = Canvas(io.BytesIO())
    for part in bundle.parts:
        for sheet in part.sheets:
            _draw_cell_text(proof, sheet.title, 0, 0, 138 * mm, 7 * mm, font_size=7)
    for appendix in appendices:
        _draw_cell_text(proof, appendix.title, 0, 0, 138 * mm, 7 * mm, font_size=7)
    from pypdf import PdfReader
    from .pprk_merge import external_contents_titles
    for document in documents:
        if document.present:
            for title in external_contents_titles(document, len(PdfReader(document.attachment_path).pages)):
                _draw_cell_text(proof, title, 0, 0, 138 * mm, 7 * mm, font_size=7)
    with TemporaryDirectory(prefix=".pprk-text-proof-") as directory:
        render_pprk_text_report(Path(directory) / "proof.pdf", replace(bundle, contents=()))


def prepare_release(project, scenario, verification):
    validate_release_inputs(project, scenario)
    validate_underlays(project)
    if scenario.joint_plan is not None:
        from .report import _joint_vertical_geometry
        _joint_vertical_geometry(scenario)
    project, scenario = deepcopy((project, scenario))
    config = project.pprk_release
    external_issues = []
    seen_ids, seen_paths = set(), set()
    for i, doc in enumerate(config.external_documents):
        path = Path(doc.attachment_path).resolve() if doc.attachment_path else None
        if not doc.document_id or doc.document_id in seen_ids or (path and path in seen_paths):
            raise ValueError("Укажите уникальный ID и отдельный PDF для каждого внешнего документа.")
        seen_ids.add(doc.document_id)
        if path:
            seen_paths.add(path)
        issues = inspect_external_document(doc)
        _reject_unsafe_external_issues(issues)
        if issues:
            # Render an explicit pending register row. Keep original metadata in the saved project.
            external_issues.extend(issues)
            config.external_documents[i] = replace(doc, present=False, attachment_path="",
                                                   verification_status="UNVERIFIED")
    context = build_pprk_context(project, scenario, verification)
    try:
        templates = load_template_catalog()
        assets = load_asset_manifest()
        bundle = compose_pprk(context, templates, assets, config)
    except (TemplateCatalogError, OSError) as exc:
        raise ValueError(f"Проверьте каталог типовых разделов, иллюстрации и текст ручных правок. {exc}") from exc
    appendices = plan_asset_appendices(bundle, assets)
    bundle = apply_appendix_completeness(bundle, appendices)
    bundle, drawing_issues = _pending_drawings(bundle, project, scenario)
    checks = (
        (project.name.strip(), "name", "Заполните название объекта."),
        (project.city.strip(), "city", "Заполните город строительства."),
        (project.site.storage_zones, "site.storage_zones", "Нанесите зону складирования."),
        (project.site.unloading_zone, "site.unloading_zone", "Нанесите зону разгрузки."),
        (project.site.restricted_zones or project.restricted_zones_confirmed,
         "site.restricted_zones", "Подтвердите наличие или отсутствие запретных зон."),
        (scenario.accounted_lifts == scenario.total_active_lifts,
         "scenario.accounted_lifts", "Выполните расчёт с учётом всех активных подъёмов."),
    )
    engineering_issues = tuple(CompletenessIssue("PPRK_PROJECT_DATA_REQUIRED", message, True, field)
                               for valid, field, message in checks if not valid)
    technical_issues = (*drawing_issues, *engineering_issues)
    issues = list(bundle.completeness_issues)
    technical = config.status in (ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION)
    issues.extend(replace(i, blocking=technical) for i in technical_issues)
    issues.extend(replace(i, blocking=i.blocking and technical) for i in external_issues)
    effective = bundle.effective_status
    if technical_issues and effective in (ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION):
        effective = ReleaseStatus.REVIEW
    if technical and any(i.blocking for i in external_issues):
        effective = ReleaseStatus.REVIEW
    bundle = replace(bundle, completeness_issues=tuple(issues), effective_status=effective,
                     production_allowed=bundle.production_allowed and not technical_issues
                     and not any(i.blocking for i in external_issues))
    _preflight_internal_text(bundle, appendices, config.external_documents)
    reasons = dict((*bundle.inclusion_reasons, *bundle.exclusion_reasons))
    sections = tuple((s.section_id, s.title, s.section_id in bundle.included_section_ids,
                      _reason(reasons[s.section_id])) for s in templates)
    status = None
    if verification.status.value not in ("VERIFIED", "VERIFIED_WITH_CONDITIONS"):
        status = "НЕ ДЛЯ ВЫПУСКА — ТРЕБУЕТСЯ ЭКСПЕРТНАЯ ПРОВЕРКА"
    return ReleaseView(project, scenario, bundle, sections, tuple(issues), status)


def issue_action(issue):
    field = issue.field_id
    if field.startswith("external_documents"):
        return "Откройте «Приложения», проверьте запись и локальный PDF."
    if field.startswith("approvals"):
        return "Заполните строки на вкладке «Согласования»."
    if field.startswith("overrides"):
        return "Сверьте ID, версию и текст правки на вкладке «Разделы»."
    if field.startswith("sections") and issue.code != "PPRK_TEMPLATE_VALUE_REQUIRED":
        return "Исправьте ручной выбор на вкладке «Разделы»."
    if field.startswith("title") or field.split("/")[-1] in RELEASE_FIELDS:
        return "Заполните соответствующее поле на вкладке «Реквизиты»."
    if field.startswith("assets"):
        return "Восстановите проверенный ресурс и повторите проверку."
    return "Проверьте указанные исходные данные проекта и повторите расчёт."


def publish_release(output, release, fingerprint, current_fingerprint, *, render=None, stage_files=None):
    release.require_requested_status()
    with TemporaryDirectory(dir=output.parent, prefix=".pprk-release-") as directory:
        staged = Path(directory) / "report.pdf"
        (render or generate_report)(staged, release.project, [release.scenario],
                                    document_status=release.document_status, bundle=release.bundle)
        if fingerprint != current_fingerprint():
            raise ValueError("Данные изменились во время формирования. Обновите предпросмотр и повторите выпуск.")
        validate_release_pdf(staged)
        files = []
        if stage_files:
            project_dir = Path(directory) / "project"
            project_dir.mkdir()
            files = stage_files(project_dir)
        def check_current():
            if fingerprint != current_fingerprint():
                raise ValueError("Данные изменились во время формирования. Обновите предпросмотр и повторите выпуск.")
        check_current()
        # Replace the PDF last. Roll back its related project/protocol files on any failure.
        backups = []
        try:
            for source, target in files:
                backup = Path(directory) / f"backup-{len(backups)}" if target.exists() else None
                if backup is not None:
                    target.replace(backup)
                backups.append((target, backup))
                source.replace(target)
            if files:
                check_current()
            staged.replace(output)
        except Exception:
            for target, backup in reversed(backups):
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    backup.replace(target)
            raise
    return output

