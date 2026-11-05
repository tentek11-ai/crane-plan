"""Real release workflow: deterministic fixture, physical PDF and raster QA.

Run directly to retain PDF/PNGs/contact sheets under ignored tmp/task11-evidence.
No reference PDF, network, synthetic protocol, engine or PDF mocks are used.
"""
from pathlib import Path
from dataclasses import replace, fields, is_dataclass
from enum import Enum
from copy import deepcopy
import io
import hashlib
import json
import re
import shutil
import shutil
import sys
import zipfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageChops
import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.pdfgen.canvas import Canvas

ROOT = (Path(sys.argv[2]).resolve() / "app" if len(sys.argv) > 2 and sys.argv[1] == "--portable"
        else Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.models import (Load, Placement, ProjectInput, ScenarioResult, SiteInput,
                              WorkPoint, JointCranePlan, RestrictedZone, RestrictedZoneKind,
                              LiftRoute, RouteWaypoint)
from crane_plan.engine import load_catalog_v3, verify_scenario_v21, IntegrationStatus
from crane_plan.engine.verification import VerificationStatus
from crane_plan.pdf_workspace import render_page
from crane_plan.sozr import build_sozr_plan
from crane_plan.pprk_models import PPRKReleaseConfig, ExternalDocument, ReleaseStatus
from crane_plan.pprk_merge import verify_external_revision
from crane_plan.pprk_assets import load_asset_manifest, validate_asset_library
from crane_plan.pprk_release_workflow import (prepare_release, publish_release,
    release_fingerprint, require_selected_protocol)
from crane_plan.pprk_sheets import plan_calculated_sheets
from crane_plan.pprk_appendices import plan_asset_appendices

CATALOG = load_catalog_v3(ROOT / "02_processed_data/cranes/crane_configurations_v3.json")
EVIDENCE = ROOT / "tmp/task11-evidence"


class DisplayValue:
    def __init__(self, value=""):
        self.value = value
    def set(self, value):
        self.value = value
    def get(self):
        return self.value


def save_via_gui(project, scenario, verification, directory, before_save=None):
    """Public GUI save with actual engine/project/PDF IO and dialog capture only."""
    from crane_plan.app import CranePlanApp
    import crane_plan.app as app_module
    ui = object.__new__(CranePlanApp)
    ui.scenarios, ui.scenario_verifications = [scenario], [verification]
    ui.selected_release_index = 0
    ui._project = lambda: deepcopy(project)
    ui.calculation_input_snapshot = ui._project_snapshot(project)
    ui.project_root = directory / "gui-projects"
    ui.report_path_var, ui.status = DisplayValue(), DisplayValue()
    if before_save:
        before_save(ui)
    warnings, errors = [], []
    with (patch.object(app_module.messagebox, "showwarning", side_effect=lambda *args: warnings.append(args)),
          patch.object(app_module.messagebox, "showerror", side_effect=lambda *args: errors.append(args)),
          patch.object(app_module.messagebox, "showinfo")):
        ui.save_and_report()
    if warnings or errors:
        raise AssertionError(f"GUI save blocked: {warnings or errors}")
    path = Path(ui.report_path_var.get().removeprefix("Готово: "))
    if not path.is_file():
        raise AssertionError("GUI save did not publish a PDF")
    return path


EXPECTED_PAGE_MAP = (
    ("service.title", "Титульный лист", 1),
    ("service.approvals", "Лист согласований", 2),
    ("service.familiarization", "Лист регистрации ознакомления", 3),
    ("service.contents", "Состав проекта / итоговый", 4),
    ("section.general", "Общие данные и назначение ППРк", 5),
    ("section.basis_and_regulations", "Основания для разработки и нормативные документы", 6),
    ("section.basis_and_regulations.continuation", "Основания для разработки и нормативные документы / продолжение", 7),
    ("section.object_characteristics", "Характеристика объекта", 8),
    ("section.crane_characteristics", "Характеристика крана и принятой конфигурации", 9),
    ("section.preparatory_measures", "Подготовительные мероприятия", 10),
    ("section.work_procedure", "Порядок производства работ", 11),
    ("section.construction_stages", "Этапы строительства и изменения конфигурации крана", 12),
    ("section.safe_crane_operations", "Организация безопасного производства работ с применением ПС", 13),
    ("section.safe_crane_operations.continuation", "Организация безопасного производства работ с применением ПС / продолжение", 14),
    ("section.lifting_accessories", "Грузозахватные приспособления и тара", 15),
    ("section.loading_operations", "Погрузочно-разгрузочные работы", 16),
    ("section.long_loads", "Перемещение длинномерных грузов", 17),
    ("section.storage", "Складирование и хранение материалов и конструкций", 18),
    ("section.concrete_bucket", "Работа с бетонной бадьей", 19),
    ("section.receiving_platforms", "Выносные приемные площадки", 20),
    ("section.opening_delivery", "Подача грузов через проемы", 21),
    ("section.joint_operations", "Совместная работа кранов, механизмов и производственных зон", 22),
    ("section.fire_safety", "Пожарная безопасность", 23),
    ("section.storm_and_weather", "Штормовое предупреждение и погодные ограничения", 24),
    ("section.work_at_height", "Безопасное производство работ на высоте", 25),
    ("section.electrical_safety", "Электробезопасность и заземление", 26),
    ("section.environmental_protection", "Охрана окружающей среды", 27),
    ("section.external_documents", "Перечень внешних специальных проектов и подтверждений", 28),
    ("external.register", "Реестр внешних документов", 29),
    ("drawing.SITE_PLAN", "СТРОЙГЕНПЛАН. Лист ГЧ-01: расположение башенных кранов", 30),
    ("drawing.VERTICAL_SECTION", "ВЫСОТНАЯ ПРИВЯЗКА. Лист ГЧ-02", 31),
    ("drawing.LOAD_SCHEDULE", "ГРУЗОВАЯ ВЕДОМОСТЬ И РАСЧЁТНЫЕ МАССЫ / ГЧ-03", 32),
    ("drawing.ROUTE_PLAN.1", "МАРШРУТЫ ПОДАЧИ И СОЗР. К1 130 EC-B 6. Координаты точек ограничения / ГЧ-04.1", 33),
    ("drawing.ROUTE_PLAN.2", "МАРШРУТЫ ПОДАЧИ И СОЗР. К2 130 EC-B 6. Координаты точек ограничения / ГЧ-04.2", 34),
    ("drawing.SOZR_PLAN.1", "СОЗР. К1 130 EC-B 6. Координаты точек ограничения / ГЧ-05.1", 35),
    ("drawing.SOZR_PLAN.2", "СОЗР. К2 130 EC-B 6. Координаты точек ограничения / ГЧ-05.2", 36),
    ("drawing.JOINT_WORK_PLAN", "СХЕМА СОВМЕСТНОЙ РАБОТЫ ДВУХ БАШЕННЫХ КРАНОВ. ВАРИАНТ 1 / ГЧ-06", 37),
    ("drawing.JOINT_WORK_SCHEDULE", "ГРАФИК СОВМЕСТНОЙ РАБОТЫ К1 И К2. ВАРИАНТ 1 / ГЧ-07", 38),
    ("appendix.FENCING", "Инвентарные ограждения опасных зон", 39),
    ("appendix.SAFETY_SIGNS", "Знаки безопасности", 40),
    ("appendix.HAND_SIGNALS", "Знаковая сигнализация при перемещении грузов", 41),
    ("appendix.SLINGING_CARDS.load-1", "Строповка: Бадья", 42),
    ("appendix.SLINGING_CARDS.load-2", "Строповка: Арматура", 43),
    ("appendix.STORAGE_SCHEMES", "Складирование арматуры", 44),
    ("service.contents.continuation", "Состав проекта / продолжение", 45),
    ("external.foundation_project.1", "Испытательный проект основания / foundation_project / лист 1", 46),
    ("external.tie_in_project.1", "Испытательный проект пристёжек / tie_in_project / лист 1", 47),
    ("external.tie_in_project.2", "Испытательный проект пристёжек / tie_in_project / лист 2", 48),
    ("external.tie_in_project.3", "Испытательный проект пристёжек / tie_in_project / лист 3", 49),
    ("external.tie_in_project.4", "Испытательный проект пристёжек / tie_in_project / лист 4", 50),
)


def assert_final_page_map(case, texts):
    case.assertEqual(len(texts), 50)
    rows = [(" ".join(title.split()), int(page))
            for text in (texts[3], texts[44])
            for title, page in re.findall(r"(.+?)\s+стр\. (\d+)", "\n".join(text.splitlines()[3:]), re.S)]
    case.assertEqual(rows, [(title, page) for _, title, page in EXPECTED_PAGE_MAP])
    # Bind each stable part/sheet identity to actual physical content too: a
    # correct-looking contents page cannot hide reordered physical PDF pages.
    services = {"service.title": "ППРк: испытательный корпус",
                "service.approvals": "ЛИСТ СОГЛАСОВАНИЙ",
                "service.familiarization": "ЛИСТ РЕГИСТРАЦИИ ОЗНАКОМЛЕНИЯ",
                "service.contents": "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ",
                "service.contents.continuation": "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ"}
    external = {46: "FOUNDATION-LAST", 47: "TIE-PORTRAIT", 48: "TIE-LANDSCAPE", 49: "TIE-ROTATED", 50: "TIE-CROP"}
    for identity, title, page in EXPECTED_PAGE_MAP:
        compact = " ".join(texts[page - 1].split())
        if identity in services:
            case.assertIn(services[identity], compact, identity)
            case.assertIn(f"Лист {page} ", compact + " ", identity)
        elif page in external:
            case.assertEqual(compact, external[page], identity)
        elif identity == "section.basis_and_regulations.continuation":
            case.assertTrue(compact.startswith("ППРк Лист 7 https://publication.pravo.gov.ru/Document/View/0001202502070031"), identity)
        elif identity == "section.safe_crane_operations.continuation":
            case.assertTrue(compact.startswith("ППРк Лист 14 выключателями в качестве рабочих органов"), identity)
        elif identity.startswith(("drawing.", "appendix.")):
            case.assertTrue(compact.startswith(title.split(" / ГЧ-")[0]), identity)
        else:
            prefix = f"ППРк Лист {page} " + ("ПОЯСНИТЕЛЬНАЯ ЗАПИСКА " if page == 5 else "")
            case.assertTrue(compact.startswith(prefix + title), identity)
    register = " ".join(texts[28].split())
    bindings = [(document_id, title.strip(), (int(start), int(end or start)))
                for document_id, title, start, end in re.findall(
                    r"(foundation_project|tie_in_project) — (.*?) Номер: .*?проверка: VERIFIED; стр\. (\d+)(?:–(\d+))?", register)]
    case.assertEqual(bindings, [("foundation_project", "Испытательный проект основания", (46, 46)),
                                ("tie_in_project", "Испытательный проект пристёжек", (47, 50))])


class SectorArcRegressionTests(unittest.TestCase):
    def test_allowed_and_excluded_arcs_match_route_planner_semantics(self):
        from crane_plan.report import _draw_sector_overlay
        from crane_plan.route_planner import _angle_in_sectors
        from reportlab.lib import colors

        class Drawing(Canvas):
            def __init__(self):
                super().__init__(io.BytesIO(), pagesize=A4, invariant=1)
                self.arcs = []
            def arc(self, x1, y1, x2, y2, startAng=0, extent=90):
                self.arcs.append((self._strokeColorObj, startAng, extent))
                return super().arc(x1, y1, x2, y2, startAng, extent)

        cases = [(0, 0, 0), (0, 360, 360), (360, 0, 0), (400, 30, 350),
                 (260, 30, 130), (350, 10, 20), (.3, .1, 359.8)]
        for start, end, sweep in cases:
            with self.subTest(start=start, end=end):
                placement = Placement("test", "test", 0, 0, [], 10, 10,
                    allowed_sector_start_deg=start, allowed_sector_end_deg=end)
                drawing = Drawing()
                _draw_sector_overlay(drawing, (200, 200), 100, placement, colors.blue, 10)
                allowed = [(a % 360, e) for color, a, e in drawing.arcs if color == colors.blue]
                forbidden = [(a % 360, e) for color, a, e in drawing.arcs if color == colors.HexColor("#C00000")]
                self.assertEqual(len(allowed), int(sweep > 0))
                if allowed:
                    self.assertAlmostEqual(allowed[0][0], start % 360)
                    self.assertAlmostEqual(allowed[0][1], sweep)
                self.assertEqual(len(forbidden), int(sweep < 360))
                if forbidden:
                    self.assertAlmostEqual(forbidden[0][0], end % 360)
                    self.assertAlmostEqual(forbidden[0][1], 360 - sweep)
                for angle in (0, .05, .1, .2, .3, .4, 10, 20, 30, 40, 180, 260, 350, 359.99):
                    rendered = (sweep == 360 or (angle - start % 360) % 360 <= sweep + 1e-9)
                    self.assertEqual(rendered, _angle_in_sectors(angle, ((start, end),)))
                # Explicit tower-exclusion arcs use the identical semantics.
                placement.allowed_sector_start_deg, placement.allowed_sector_end_deg = 0, 360
                placement.tower_exclusion_start_deg, placement.tower_exclusion_end_deg = start, end
                drawing = Drawing()
                _draw_sector_overlay(drawing, (200, 200), 100, placement, colors.blue, 10)
                excluded = [(a % 360, e) for color, a, e in drawing.arcs if color == colors.HexColor("#C00000")]
                self.assertEqual(len(excluded), 2 * int(sweep > 0))
                for angle, extent in excluded:
                    self.assertAlmostEqual(angle, start % 360)
                    self.assertAlmostEqual(extent, sweep)


class GuiReleaseRegressionTests(unittest.TestCase):
    def test_gui_rejects_foreign_scenario_protocol_without_writing_existing_files(self):
        from crane_plan.project_io import create_project_folder
        (ROOT / "tmp/test-temp").mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=ROOT / "tmp/test-temp") as tmp:
            directory = Path(tmp)
            project, scenario = build_fixture(directory)
            first = verify(project, scenario)
            second = verify_scenario_v21(project, scenario, CATALOG, scenario_index=1,
                run_id="E2E-OTHER-SCENARIO", created_at="2026-11-04T12:00:00+03:00")
            self.assertEqual(first.scenario_index, 0)
            self.assertEqual(second.scenario_index, 1)
            self.assertEqual(second.engine_result.verification.status, VerificationStatus.VALID)
            folder = create_project_folder(directory / "gui-projects", project)
            for name, data in (("reports/ППРк_предварительный.pdf", b"previous-pdf"),
                               ("reports/calculation_protocol_v21.json", b"previous-protocol"),
                               ("project.json", b"previous-project"),
                               ("revisions/prior.json", b"previous-revision")):
                (folder / name).write_bytes(data)
            before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
            with self.assertRaisesRegex(AssertionError, "каноническ"):
                save_via_gui(project, scenario, replace(first, protocol=second.protocol), directory)
            after = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
            self.assertEqual(after, before)

    def test_save_guard_compares_every_serialized_field_and_rejects_nested_changes(self):
        from crane_plan.engine.protocol import canonical_json, CalculationProtocolV3
        from crane_plan.pprk_release_workflow import require_saveable_release
        (ROOT / "tmp/test-temp").mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=ROOT / "tmp/test-temp") as tmp:
            project, scenario = build_fixture(Path(tmp))
            verified = verify(project, scenario)
            view = prepare_release(project, scenario, verified)
            payload = json.loads(canonical_json(verified.protocol))
            def mutate(value):
                if isinstance(value, dict):
                    changed = deepcopy(value)
                    key = next(iter(changed))
                    changed[key] = mutate(changed[key])
                    return changed
                if isinstance(value, list):
                    return [mutate(value[0]), *value[1:]] if value else ["mutated"]
                if isinstance(value, str):
                    return value + "-mutated"
                if isinstance(value, (int, float)):
                    return value + 1
                return "mutated"
            # Keep self-reported input/result hashes intact for nested changes.
            # Full canonical content must be checked rather than these two fields.
            for field in fields(verified.protocol):
                with self.subTest(field=field.name):
                    changed = deepcopy(payload)
                    changed[field.name] = mutate(changed[field.name])
                    protocol = CalculationProtocolV3(**changed)
                    with self.assertRaisesRegex(ValueError, "каноническ"):
                        require_saveable_release(view, replace(verified, protocol=protocol))
            for field, replacement in (("load_kg", 9999), ("crane_id", "FOREIGN-CRANE")):
                with self.subTest(nested_field=field):
                    changed = deepcopy(payload)
                    if field == "load_kg":
                        changed["project"]["operations"][0]["load"][field] = replacement
                    else:
                        changed["solution"]["stages"][0]["placements"][0]["id"] = replacement
                    self.assertEqual(changed["input_sha256"], payload["input_sha256"])
                    self.assertEqual(changed["result_sha256"], payload["result_sha256"])
                    with self.assertRaisesRegex(ValueError, "каноническ"):
                        require_saveable_release(view, replace(verified, protocol=CalculationProtocolV3(**changed)))
            with self.assertRaisesRegex(ValueError, "каноническ"):
                require_saveable_release(view, replace(verified, engine_result=replace(verified.engine_result, protocol=None)))

    def test_canonical_equivalent_deserialized_protocol_can_be_saved(self):
        from crane_plan.engine.protocol import canonical_json
        (ROOT / "tmp/test-temp").mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=ROOT / "tmp/test-temp") as tmp:
            directory = Path(tmp)
            project, scenario = build_fixture(directory)
            verified = verify(project, scenario)
            def restore(original, value):
                if is_dataclass(original):
                    return replace(original, **{f.name: restore(getattr(original, f.name), value[f.name]) for f in fields(original)})
                if isinstance(original, Enum):
                    return type(original)(value)
                if isinstance(original, (tuple, list)):
                    return type(original)(restore(old, new) for old, new in zip(original, value))
                if isinstance(original, dict):
                    return {key: restore(original[key], item) for key, item in value.items()}
                return value
            restored = restore(verified.protocol, json.loads(canonical_json(verified.protocol)))
            self.assertIsNot(restored, verified.protocol)
            self.assertIsNot(restored.project, verified.protocol.project)
            self.assertEqual(canonical_json(restored), canonical_json(verified.protocol))
            path = save_via_gui(project, scenario, replace(verified, protocol=restored), directory)
            saved = json.loads((path.parent / "calculation_protocol_v21.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, json.loads(canonical_json(restored)))
            self.assertIn("предварительная автоматизированная редакция", PdfReader(path).pages[0].extract_text())

    def test_public_gui_saves_preliminary_tie_scenario_with_warning_and_protocol(self):
        (ROOT / "tmp/test-temp").mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=ROOT / "tmp/test-temp") as tmp:
            directory = Path(tmp)
            project, scenario = build_fixture(directory)
            verification = verify(project, scenario)
            path = save_via_gui(project, scenario, verification, directory)
            self.assertEqual(path.name, "ППРк_предварительный.pdf")
            title = PdfReader(path).pages[0].extract_text()
            self.assertIn("предварительная автоматизированная редакция", title)
            self.assertIn("НЕ ДЛЯ ВЫПУСКА", title)
            protocol = json.loads((path.parent / "calculation_protocol_v21.json").read_text(encoding="utf-8"))
            self.assertEqual(protocol["input_sha256"], verification.protocol.input_sha256)

    def test_preliminary_gui_save_still_requires_current_inputs_and_selected_protocol(self):
        (ROOT / "tmp/test-temp").mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=ROOT / "tmp/test-temp") as tmp:
            directory = Path(tmp)
            project, scenario = build_fixture(directory)
            verification = verify(project, scenario)
            def change_after_calculation(ui):
                changed = deepcopy(project)
                changed.loads[0].load_kg += 10
                ui._project = lambda: changed
            with self.assertRaisesRegex(AssertionError, "изменились после расчёта"):
                save_via_gui(project, scenario, verification, directory, change_after_calculation)
            with self.assertRaisesRegex(AssertionError, "другому варианту"):
                save_via_gui(project, scenario, replace(verification, scenario_index=1), directory)
            self.assertFalse((directory / "gui-projects").exists())

    def test_expert_draft_does_not_bypass_rejected_fatal_or_missing_protocol(self):
        (ROOT / "tmp/test-temp").mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=ROOT / "tmp/test-temp") as tmp:
            directory = Path(tmp)
            project, scenario = build_fixture(directory)
            verification = verify(project, scenario)
            report = verification.engine_result.verification
            failed = replace(report, checks=(replace(report.checks[0], passed=False, review_required=False), *report.checks[1:]))
            for invalid in (replace(verification, status=IntegrationStatus.REJECTED),
                            replace(verification, protocol=None),
                            replace(verification, engine_result=replace(verification.engine_result, verification=failed))):
                with self.subTest(status=invalid.status, protocol=invalid.protocol is not None):
                    with self.assertRaisesRegex(AssertionError, "GUI save blocked"):
                        save_via_gui(project, scenario, invalid, directory)
                    self.assertFalse((directory / "gui-projects").exists())
            for status in (ReleaseStatus.REVIEW, ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION):
                with self.subTest(requested_status=status):
                    project.pprk_release.status = status
                    with self.assertRaisesRegex(AssertionError, "GUI save blocked"):
                        save_via_gui(project, scenario, verification, directory)
                    self.assertFalse((directory / "gui-projects").exists())


def external_fixture(path, markers):
    """Small generated engineering attachments, with all ink inside each crop."""
    packet = io.BytesIO()
    canvas = Canvas(packet, pagesize=A4, invariant=1)
    for index, marker in enumerate(markers):
        canvas.setPageSize(landscape(A3) if index == 1 else A4)
        canvas.setFont("Helvetica", 16)
        canvas.drawString(60, 500, marker)
        canvas.rect(50, 120, 300, 420)
        for y in range(160, 480, 40):
            canvas.line(60, y, 340, y)
        canvas.showPage()
    canvas.save()
    writer = PdfWriter()
    for index, page in enumerate(PdfReader(packet).pages):
        if index == 2:
            page.rotate(90)
        if index == 3:
            page.mediabox = RectangleObject((-15, -20, A4[0], A4[1]))
            page.cropbox = RectangleObject((25, 45, 400, 600))
        writer.add_page(page)
    with path.open("wb") as stream:
        writer.write(stream)
    return path


def build_fixture(directory):
    directory.mkdir(parents=True, exist_ok=True)
    project = ProjectInput(
        "Испытательный корпус", "Москва", 2026, "", "", -3, 40,
        SiteInput([(-50, -50), (50, -50), (50, 50), (-50, 50)],
                  [(20, -10), (40, -10), (40, 10), (20, 10)],
                  restricted_zones=[RestrictedZone("RZ-E2E", "Ограничение высоты",
                      RestrictedZoneKind.HEIGHT_OBSTACLE,
                      [(-25, 20), (-20, 20), (-20, 25), (-25, 25)], 8)],
                  unloading_zone=[(12, -22), (18, -22), (18, -18), (12, -18)],
                  storage_zones=[[(12, -18), (18, -18), (18, -12), (12, -12)]],
                  min_crane_to_building_m=1, max_crane_to_building_m=25),
        [Load("Бадья", 1000, 100, 1.8, 1.8, 2, 12),
         Load("Арматура", 800, 80, 6, 0.5, 0.5, 8)],
        [WorkPoint(25, 0, 20, 0, "Подача бадьи"),
         WorkPoint(35, 5, 20, 1, "Подача труб")], loads_verified=True,
        restricted_zones_confirmed=True, organization="ООО Испытательный проект",
        project_code="E2E-2026", floors=12)
    project.pprk_release = PPRKReleaseConfig(
        title="ППРк: испытательный корпус", object_address="Москва, ул. Испытательная, д. 99",
        developer_organization=project.organization, project_code=project.project_code,
        lifting_equipment_type="Башенные краны",
        developer_position="Инженер", developer_name="Испытатель И.И.",
        developer_date="2026-11-04", manager_position="Руководитель",
        manager_name="Проверяющий П.П.", manager_date="2026-11-04",
        issue_city="Москва", issue_year=2026, issue_date="2026-11-04", project_basis="Испытательное задание E2E",
        plan_sheet_refs="По составу проекта", responsible_fire_safety="По приказу E2E",
        max_wind_speed_m_s=10, fall_protection_system="Анкерная линия",
        power_supply_scheme="Отдельная линия ВРУ", waste_plan="Контейнерный вывоз",
        external_document_register="Реестр E2E", bucket_volume_m3=0.5,
        receiving_platform_ids=["ПЛ-1"], opening_ids=["ПР-1"])
    scenario = ScenarioResult("PASS", [Placement(
        "LIEBHERR-130-ECB-6-60", "130 EC-B 6", 0, 0, [0], 25, 25, 40,
        jib_level_m=32.4, max_free_standing_height_m=44.4, accepted_crane_height_m=44.4,
        tie_in_levels_m=[32], tie_in_stage_sections=[1], tie_nearest_floors=[10],
        total_additional_sections=1, required_tie_length_m=23.1,
        allowed_sector_start_deg=260, allowed_sector_end_deg=30),
        Placement("LIEBHERR-130-ECB-6-60", "130 EC-B 6", 10, 10, [1], 26, 25, 40,
            jib_level_m=42.4, max_free_standing_height_m=44.4, accepted_crane_height_m=44.4)],
        [], [], total_active_lifts=20, accounted_lifts=20, calendar_days=10,
        joint_plan=JointCranePlan(14.142135624, 5, 2, 10, 2, 1, True, 100,
            overlap_polygon=[(15, -10), (20, -10), (20, 10), (15, 10)],
            rules=["Поочередная работа в общей зоне"],
            schedule_stages=["К1: подача бадьи; К2: ожидание", "К2: подача труб; К1: ожидание"]))
    scenario.routes = [LiftRoute(f"OP-W{i + 1}-L{i + 1}", (
        RouteWaypoint(15, -15, 30, "hoist"), RouteWaypoint(point.x, point.y, 30, "trolley")),
        30, (), f"e2e-route-{i + 1}") for i, point in enumerate(project.work_points)]
    # The unloading-to-storage route is retained in the same route register.
    scenario.routes.append(LiftRoute("UNLOAD-TO-STORAGE", (
        RouteWaypoint(15, -20, 30, "hoist"), RouteWaypoint(15, -15, 30, "trolley")),
        30, (), "e2e-unloading"))
    for index, placement in enumerate(scenario.placements):
        placement.sozr_plan = build_sozr_plan(f"К{index + 1}", (placement.x, placement.y),
            40, project.site.restricted_zones, [scenario.routes[index]], project)
    for doc_id, title, markers in [
        ("tie_in_project", "Испытательный проект пристёжек", ("TIE-PORTRAIT", "TIE-LANDSCAPE", "TIE-ROTATED", "TIE-CROP")),
        ("foundation_project", "Испытательный проект основания", ("FOUNDATION-LAST",))]:
        path = external_fixture(directory / f"{doc_id}.pdf", markers)
        document = ExternalDocument(doc_id, title, required=True, present=True,
            attachment_path=str(path), number=f"E2E-{doc_id}", date="2026-11-04",
            organization="Испытательная организация")
        project.pprk_release.external_documents.append(verify_external_revision(document))
    return project, scenario


def verify(project, scenario):
    return verify_scenario_v21(project, scenario, CATALOG, scenario_index=0,
        run_id="E2E-FULL-PPRK", created_at="2026-11-04T12:00:00+03:00")


def raster_qa(path, directory):
    """Supported PDFium renderer, conservative measurable checks and contact sheets.

    Heuristics signal defects; they do not prove the absence of every collision
    between vector graphics. All pages also require human contact-sheet review.
    """
    directory.mkdir(parents=True, exist_ok=True)
    metrics, thumbs = [], []
    for index in range(len(PdfReader(path).pages)):
        image = render_page(path, index, scale=1.0)
        image.save(directory / f"page-{index + 1:02}.png")
        mask = image.convert("L").point(lambda p: 255 if p < 220 else 0)
        box = mask.getbbox()
        if box is None:
            raise AssertionError(f"Blank raster page {index + 1}")
        inset = 8
        core = mask.crop((inset, inset, image.width - inset, image.height - inset))
        ink = core.histogram()[255] / (core.width * core.height)
        if ink < 0.0008 or box[2] - box[0] < image.width * .1 or box[3] - box[1] < image.height * .1:
            raise AssertionError(f"Implausibly small content on page {index + 1}: {ink}")
        edge = sum(mask.crop(rect).histogram()[255] for rect in (
            (0, 0, image.width, 2), (0, image.height - 2, image.width, image.height),
            (0, 2, 2, image.height - 2), (image.width - 2, 2, image.width, image.height - 2)))
        if edge:
            raise AssertionError(f"Ink touches page edge {index + 1}: {edge} pixels")
        metrics.append({"page": index + 1, "size": image.size, "ink_ratio": ink, "ink_bbox": box})
        image.thumbnail((370, 430))
        thumb = Image.new("RGB", (400, 470), "#dddddd")
        thumb.paste(image, ((400 - image.width) // 2, 25))
        ImageDraw.Draw(thumb).text((12, 8), f"PAGE {index + 1:02}", fill="black")
        thumbs.append(thumb)
    for start in range(0, len(thumbs), 9):
        sheet = Image.new("RGB", (1200, 1410), "white")
        for offset, thumb in enumerate(thumbs[start:start + 9]):
            sheet.paste(thumb, ((offset % 3) * 400, (offset // 3) * 470))
        sheet.save(directory / f"contact-{start // 9 + 1:02}.png")
    (directory / "raster-metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def check_portable_release(directory):
    """Run under the packaged Python with its own app on PYTHONPATH."""
    directory = Path(directory).resolve()
    archive = directory.with_name(directory.name + "_Windows.zip")
    for relative in ("runtime/python.exe", "app/05_src/main.py", "app/README.md",
                     "Руководство пользователя.md", "Запустить КранПлан.bat",
                     "app/05_src/crane_plan/assets/pprk/sections.json",
                     "app/02_processed_data/regulations/regulation_registry.csv"):
        if not (directory / relative).is_file():
            raise AssertionError(f"Missing portable input: {relative}")
    root = directory / "app/05_src/crane_plan/assets/pprk"
    if validate_asset_library(root):
        raise AssertionError("Invalid portable asset manifest")
    assets = load_asset_manifest(root / "manifest.json")
    for asset in assets:
        if hashlib.sha256((root / asset.file_name).read_bytes()).hexdigest() != asset.sha256:
            raise AssertionError(f"Changed portable clip: {asset.asset_id}")
    for name in ("cranes", "regulations"):
        library = directory / "app/library" / name
        data = json.loads((library / "manifest.json").read_text(encoding="utf-8"))
        for entry in data["entries"]:
            if entry.get("local_file") and not (library / entry["local_file"]).is_file():
                raise AssertionError(f"Missing offline library file: {entry['local_file']}")
    excluded = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git", ".aws", ".env", "task11-evidence"}
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise AssertionError("Corrupt ZIP member")
        names = package.namelist()
        for name in names:
            parts = Path(name).parts
            if any(p in excluded or p.startswith(".env.") for p in parts) or name.endswith((".pyc", ".pyo")):
                raise AssertionError(f"Scratch/cache/secret in archive: {name}")
            if "тружен" in name.casefold() or "reference.pdf" in name.casefold():
                raise AssertionError(f"Source analogue in archive: {name}")
            if name.lower().endswith(".pdf"):
                if hashlib.sha256(package.read(name)).hexdigest() == "d586d1840d221c96041db449b7d6868824a328e66b25a21c6e6bee0fa4410392":
                    raise AssertionError(f"Renamed source analogue in archive: {name}")
        if len(names) != sum(p.is_file() for p in directory.rglob("*")):
            raise AssertionError("ZIP and release directory inventories differ")
    # Imports and font/resource-backed generation execute in the portable process.
    from crane_plan.app import CranePlanApp
    from crane_plan.pprk_templates import load_template_catalog
    if len(load_template_catalog()) != 22:
        raise AssertionError("Incomplete offline text catalog")
    import crane_plan.app as portable_app
    Path(portable_app.__file__).resolve().relative_to(directory)
    smoke = directory.parent / "portable-smoke"
    project, scenario = build_fixture(smoke)
    checked = verify(project, scenario)
    pdf = save_via_gui(project, scenario, checked, smoke)
    if len(PdfReader(pdf).pages) != 50:
        raise AssertionError("Portable PDF composition differs")
    for number in (0, 41, 49):
        render_page(pdf, number, scale=.5).save(smoke / f"portable-page-{number + 1}.png")
    result = {"files": len(names), "pprk_assets": len(assets), "archive": str(archive),
              "python": sys.executable, "application": str(portable_app.__file__), "pdf_pages": 50}
    return result


class FullPPRkEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Pin temp paths even when this module is run without the shell wrapper.
        (ROOT / "tmp/test-temp").mkdir(parents=True, exist_ok=True)
        cls.temp = TemporaryDirectory(dir=ROOT / "tmp/test-temp", prefix="full-pprk-")
        cls.directory = Path(cls.temp.name)
        cls.project, cls.scenario = build_fixture(cls.directory)
        cls.verification = verify(cls.project, cls.scenario)
        cls.release = prepare_release(cls.project, cls.scenario, cls.verification)
        cls.path = save_via_gui(cls.project, cls.scenario, cls.verification, cls.directory)
        cls.reader = PdfReader(cls.path)
        cls.texts = [page.extract_text() or "" for page in cls.reader.pages]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_protocol_preserves_expert_gate_for_ties(self):
        self.assertEqual(self.verification.engine_result.verification.status, VerificationStatus.VALID)
        self.assertEqual(self.verification.status, IntegrationStatus.EXPERT_REVIEW_REQUIRED)
        self.assertTrue(any("TIE_INS_NOT_VERIFIED" in text for text in self.verification.messages))
        self.assertEqual(self.release.bundle.effective_status, ReleaseStatus.PRELIMINARY)
        self.assertIn("НЕ ДЛЯ ВЫПУСКА", self.texts[0])
        for index in (0, 1):
            self.assertTrue(any(c.crane_id == f"SCENARIO-1-CRANE-{index + 1}" and c.passed
                for c in self.verification.engine_result.verification.checks))
        project, scenario = deepcopy((self.project, self.scenario))
        for crane in scenario.placements:
            crane.tie_in_levels_m = []
            crane.tie_in_stage_sections = []
            crane.tie_nearest_floors = []
            crane.total_additional_sections = 0
        checked = verify(project, scenario)
        self.assertEqual(checked.status, IntegrationStatus.VERIFIED_WITH_CONDITIONS)
        self.assertTrue(checked.release_allowed)
        project.pprk_release.status = ReleaseStatus.PRODUCTION
        with self.assertRaises(ValueError):
            prepare_release(project, self.scenario, self.verification).require_requested_status()

    def test_exact_physical_order_counts_and_resolved_page_map(self):
        self.assertEqual(len(self.texts), 50)
        for index, title in enumerate(("ППРк: испытательный корпус", "ЛИСТ СОГЛАСОВАНИЙ",
            "ЛИСТ РЕГИСТРАЦИИ ОЗНАКОМЛЕНИЯ", "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ")):
            self.assertIn(title, self.texts[index])
        self.assertEqual(self.texts[1].count("СОГЛАСОВАНО"), 8)
        notes = [p for p in self.release.bundle.parts if p.kind == "note"]
        self.assertEqual(len(notes), 22)
        # Literal physical starts include the safe-operations continuation on 13.
        starts = [5, 6, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28]
        for part, page in zip(notes, starts):
            self.assertIn(part.title, self.texts[page - 1])
        expected_drawings = [
            ("drawing.SITE_PLAN", "site_plan", "A1", "СТРОЙГЕНПЛАН"),
            ("drawing.VERTICAL_SECTION", "vertical_section", "A2", "ВЫСОТНАЯ ПРИВЯЗКА"),
            ("drawing.LOAD_SCHEDULE", "load_schedule", "A3", "ГРУЗОВАЯ ВЕДОМОСТЬ"),
            ("drawing.ROUTE_PLAN.1", "route_plan", "A2", "МАРШРУТЫ ПОДАЧИ И СОЗР. К1"),
            ("drawing.ROUTE_PLAN.2", "route_plan", "A2", "МАРШРУТЫ ПОДАЧИ И СОЗР. К2"),
            ("drawing.SOZR_PLAN.1", "sozr", "A2", "СОЗР. К1"),
            ("drawing.SOZR_PLAN.2", "sozr", "A2", "СОЗР. К2"),
            ("drawing.JOINT_WORK_PLAN", "joint_work_plan", "A1", "СХЕМА СОВМЕСТНОЙ РАБОТЫ"),
            ("drawing.JOINT_WORK_SCHEDULE", "joint_work_schedule", "A3", "ГРАФИК СОВМЕСТНОЙ РАБОТЫ")]
        plans = plan_calculated_sheets(self.release.bundle, self.project, self.scenario)
        self.assertEqual([(p.sheet_id, p.render_kind, p.sheet_format.name) for p in plans],
                         [row[:3] for row in expected_drawings])
        seen_sources = set()
        for page, (plan, expected) in enumerate(zip(plans, expected_drawings), 30):
            self.assertIn(expected[3], self.texts[page - 1])
            # Logical references point to the first page of an expanded group;
            # the physical contents below list every individual continuation.
            if plan.source_sheet_id not in seen_sources:
                self.assertIn(f"{plan.designation} / стр. {page}", " ".join(" ".join(self.texts[4:29]).split()))
                seen_sources.add(plan.source_sheet_id)
        self.assertIn("Реестр внешних документов", self.texts[28])
        for page, title in enumerate(("Инвентарные ограждения", "Знаки безопасности",
            "Знаковая сигнализация", "Строповка: Бадья", "Строповка: Арматура", "Складирование арматуры"), 39):
            self.assertIn(title, self.texts[page - 1])
        self.assertIn("СОСТАВ ПРОЕКТА / ИТОГОВЫЙ", self.texts[44])
        assert_final_page_map(self, self.texts)
        self.assertIn("стр. 46", self.texts[28])
        self.assertIn("стр. 47–50", self.texts[28])
        self.assertEqual([text.strip() for text in self.texts[-5:]],
            ["FOUNDATION-LAST", "TIE-PORTRAIT", "TIE-LANDSCAPE", "TIE-ROTATED", "TIE-CROP"])
        self.assertNotIn("ОЖИДАЕТ РАСЧЁТА", "\n".join(self.texts))

    def test_page_map_rejects_service_permutation_and_swapped_external_ranges(self):
        permuted = list(self.texts)
        permuted[0], permuted[1] = permuted[1], permuted[0]
        with self.assertRaises(AssertionError):
            assert_final_page_map(self, permuted)
        swapped = list(self.texts)
        swapped[28] = swapped[28].replace("стр. 46", "TEMP-RANGE").replace("стр. 47–50", "стр. 46").replace("TEMP-RANGE", "стр. 47–50")
        with self.assertRaises(AssertionError):
            assert_final_page_map(self, swapped)
        wrong_contents = list(self.texts)
        wrong_contents[3] = wrong_contents[3].replace("Титульный лист", "TEMP-TITLE").replace("Лист согласований", "Титульный лист").replace("TEMP-TITLE", "Лист согласований")
        with self.assertRaises(AssertionError):
            assert_final_page_map(self, wrong_contents)

    def test_external_pages_keep_exact_boxes_rotation_and_content(self):
        sources = sorted(self.project.pprk_release.external_documents, key=lambda d: d.document_id)
        pages = [page for doc in sources for page in PdfReader(doc.attachment_path).pages]
        for original, result in zip(pages, self.reader.pages[-5:]):
            self.assertEqual(tuple(original.mediabox), tuple(result.mediabox))
            self.assertEqual(tuple(original.cropbox), tuple(result.cropbox))
            self.assertEqual(original.get("/Rotate"), result.get("/Rotate"))
            self.assertEqual(original.get_contents().get_data(), result.get_contents().get_data())

    def test_verified_clips_remain_identical_and_physically_usable(self):
        from crane_plan.pprk_assets import ASSET_ROOT
        self.assertEqual(validate_asset_library(ASSET_ROOT), [])
        assets = {a.asset_id: a for a in load_asset_manifest()}
        self.assertEqual([p.asset_id for p in plan_asset_appendices(self.release.bundle, tuple(assets.values()))],
                         ["fencing", "safety_signs", "hand_signals", "slinging", "slinging", "storage"])
        with pdfplumber.open(self.path) as pdf:
            for number, asset_id in zip(range(39, 45), ("fencing", "safety_signs", "hand_signals", "slinging", "slinging", "storage")):
                page = self.reader.pages[number - 1]
                self.assertEqual(len(page.images), 1)
                original = Image.open(ASSET_ROOT / assets[asset_id].file_name).convert("RGB")
                # Verified 6575x6729 RGB board exceeds pypdf's default 75 MB
                # decompression guard. Bound the override to trusted repo pixels.
                with patch("pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH", 200_000_000):
                    embedded = page.images[0].image.convert("RGB")
                self.assertEqual(embedded.size, original.size)
                self.assertIsNone(ImageChops.difference(embedded, original).getbbox())
                image, = pdf.pages[number - 1].images
                width, height = image["x1"] - image["x0"], image["bottom"] - image["top"]
                self.assertGreater(min(width, height), 250)
                self.assertAlmostEqual(width / height, original.width / original.height, places=4)

    def test_no_reference_identity_source_paths_blank_or_overflowing_text(self):
        text = "\n".join(self.texts) + str(self.reader.metadata)
        for forbidden in ("ППР ЦЕНТР", "27.06-23", "AUTODESK EDUCATIONAL PRODUCT",
                          "Тружен", "F:/", "F:\\", str(ROOT), str(self.directory),
                          "source_page", "reference_clip", "d586d1840d221c96041db449b7d6868824a328e66b25a21c6e6bee0fa4410392"):
            self.assertNotIn(forbidden.casefold(), text.casefold())
        with pdfplumber.open(self.path) as pdf:
            for number, page in enumerate(pdf.pages[:45], 1):
                self.assertTrue(self.texts[number - 1].strip())
                for char in page.chars:
                    if not char["text"].strip():
                        continue
                    self.assertGreaterEqual(char["x0"], -1, (number, char))
                    self.assertLessEqual(char["x1"], page.width + 1, (number, char))
                    self.assertGreaterEqual(char["top"], -1, (number, char))
                    self.assertLessEqual(char["bottom"], page.height + 1, (number, char))
                # The deliberate diagonal expert watermark crosses document
                # content; measure collisions only among horizontal body words.
                body = page.filter(lambda obj: obj.get("object_type") != "char" or
                    (abs(obj["matrix"][1]) < 1e-6 and abs(obj["matrix"][2]) < 1e-6))
                words = body.extract_words()
                # Strong intersections of distinct word rows signal overprinting;
                # adjacent kerned letters and engineering linework are excluded.
                for i, first in enumerate(words):
                    for second in words[i + 1:]:
                        if abs(first["top"] - second["top"]) < 2:
                            continue
                        dx = min(first["x1"], second["x1"]) - max(first["x0"], second["x0"])
                        dy = min(first["bottom"], second["bottom"]) - max(first["top"], second["top"])
                        minimum = min((w["x1"] - w["x0"]) * (w["bottom"] - w["top"]) for w in (first, second))
                        self.assertFalse(dx > 0 and dy > 0 and dx * dy > .7 * minimum,
                                         (number, first, second))

    def test_every_page_renders_without_blank_edge_clipping_or_tiny_content(self):
        self.assertEqual(len(raster_qa(self.path, self.directory / "raster")), 50)

    def test_input_edit_blocks_release_then_real_recalculation_unlocks_preview_and_save(self):
        from crane_plan.app import CranePlanApp, _CalculationBundle
        from crane_plan.engine.protocol import save_protocol_atomic
        from crane_plan.project_io import save_project

        class Value:
            def __init__(self, value=""):
                self.value = value
            def set(self, value):
                self.value = value
            def get(self):
                return self.value
            def configure(self, **values):
                self.values = values
            def delete(self, *_args):
                self.value = ""
            def insert(self, _where, text):
                self.value += text

        # Use the real app calculation/apply/publication boundary. The tiny
        # widget substitutes hold display state only; engine/optimizer/IO run.
        project = deepcopy(self.project)
        project.site.boundary = [(-35, -35), (35, -35), (35, 35), (-35, 35)]
        project.site.building = [(-15, -3), (15, -3), (15, 3), (-15, 3)]
        project.site.restricted_zones = []
        project.work_points = [WorkPoint(10, 0, 20, 0, "Подача")]
        project.loads = [project.loads[0]]
        project.parapet_m = 25
        ui = object.__new__(CranePlanApp)
        ui._project = lambda: deepcopy(project)
        # Restrict the real optimizer to the supported, unchanged repository
        # configuration so an unrelated unverified model cannot win on price.
        catalog = json.loads((ROOT / "02_processed_data/cranes/crane_configurations.json").read_text(encoding="utf-8"))
        catalog["configurations"] = catalog["configurations"][:1]
        ui.catalog_path = self.directory / "verified-catalog.json"
        ui.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        ui.catalog_v3_path = ROOT / "02_processed_data/cranes/crane_configurations_v3.json"
        ui.user_catalog_path = self.directory / "absent-user-catalog.json"
        ui.warning_acceptances = []
        ui.report_excluded_pages = set()
        ui.report_selection_var = Value()
        ui.results = Value()
        ui.release_variant_var = Value()
        ui.release_variant_combo = Value()
        ui._draw_selected_sozr = lambda: None
        ui._apply_automatic_calculation(_CalculationBundle(project, [], [self.scenario], [self.verification]))
        ui.selected_release_index = 0
        ui._current_release_inputs()
        project.loads[0].load_kg += 20
        with self.assertRaisesRegex(ValueError, "изменились после расчёта"):
            ui._current_release_inputs()
        result = ui._calculate_snapshot((deepcopy(project), []))
        ui._apply_automatic_calculation(result)
        self.assertIsNotNone(ui.selected_release_index)
        current = ui._current_release_inputs()
        self.assertIs(current[1], ui.scenarios[current[3]])
        self.assertIs(current[2], ui.scenario_verifications[current[3]])
        require_selected_protocol(current[3], current[2])
        self.assertNotEqual(current[2].protocol.input_sha256, self.verification.protocol.input_sha256)
        self.assertTrue(ui._calculation_is_current(project))
        view = prepare_release(*current[:3])
        fingerprint = release_fingerprint(*current)
        for name in ("recalculated-preview.pdf", "recalculated-save.pdf"):
            output = self.directory / name
            publish_release(output, view, fingerprint, ui._current_release_fingerprint)
            self.assertIn("Испытательный корпус", PdfReader(output).pages[0].extract_text())
            self.assertTrue(ui._calculation_is_current(project))
        saved = self.directory / "saved-project"
        saved.mkdir()
        save_project(saved, current[0], [s.to_dict() for s in ui.scenarios],
                     selected_scenario_index=current[3],
                     scenario_verifications=[v.to_dict() for v in ui.scenario_verifications])
        save_protocol_atomic(saved / "calculation_protocol_v21.json", current[2].protocol)
        self.assertTrue((saved / "project.json").is_file())
        self.assertEqual(json.loads((saved / "calculation_protocol_v21.json").read_text(encoding="utf-8"))["input_sha256"], current[2].protocol.input_sha256)

    def test_wrapped_sector_exports_same_geometry_as_unwrapped_angles(self):
        # The real E2E used a permitted 260..30 degree sector; clamping its
        # negative difference to zero made ReportLab divide by zero.
        from crane_plan.report import _draw_sector_overlay
        from reportlab.lib import colors
        project, scenario = build_fixture(self.directory)
        placement = scenario.placements[0]
        streams = []
        for end in (30, 390):
            placement.allowed_sector_end_deg = end
            placement.tower_exclusion_start_deg = 350
            placement.tower_exclusion_end_deg = end - 20
            packet = io.BytesIO()
            canvas = Canvas(packet, pagesize=A4, invariant=1)
            _draw_sector_overlay(canvas, (200, 200), 100, placement, colors.blue, 10)
            canvas.showPage()
            canvas.save()
            streams.append(PdfReader(packet).pages[0].get_contents().get_data())
        self.assertEqual(streams[0], streams[1])

    def test_fixture_covers_two_cranes_ties_and_conditional_operations(self):
        before = [Path(d.attachment_path).read_bytes() for d in self.project.pprk_release.external_documents]
        project, scenario = build_fixture(self.directory)
        self.assertEqual(project.to_dict(), self.project.to_dict())
        self.assertEqual(scenario.to_dict(), self.scenario.to_dict())
        self.assertEqual(before, [Path(d.attachment_path).read_bytes() for d in project.pprk_release.external_documents])
        self.assertEqual(len(scenario.placements), 2, "E2E must exercise both crane assignments")
        self.assertTrue(scenario.joint_plan)
        self.assertTrue(any(p.tie_in_levels_m for p in scenario.placements))
        self.assertTrue(any(load.length_m > 3 for load in project.loads))
        self.assertTrue(project.site.unloading_zone and project.site.storage_zones)
        self.assertTrue(project.site.restricted_zones)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--evidence":
        project, scenario = build_fixture(EVIDENCE)
        checked = verify(project, scenario)
        saved = save_via_gui(project, scenario, checked, EVIDENCE)
        output = EVIDENCE / "full-pprk.pdf"
        shutil.copy2(saved, output)
        metrics = raster_qa(output, EVIDENCE / "raster")
        print(json.dumps({"pdf": str(output), "pages": len(metrics)}, ensure_ascii=False))
    elif len(sys.argv) > 2 and sys.argv[1] == "--portable":
        print(json.dumps(check_portable_release(sys.argv[2]), ensure_ascii=False))
    else:
        unittest.main()

