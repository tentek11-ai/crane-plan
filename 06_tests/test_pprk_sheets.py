import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from pypdf import PdfReader  # noqa: E402
from reportlab.pdfgen.canvas import Canvas  # noqa: E402

from crane_plan.models import (  # noqa: E402
    JointCranePlan,
    LiftRoute,
    Load,
    Placement,
    ProjectInput,
    ScenarioResult,
    SiteInput,
    SOZRPlan,
    SOZRPoint,
    SOZRRestrictionClass,
    RouteAlternative,
    RouteWaypoint,
    WorkPoint,
)
from crane_plan.pprk_composer import (  # noqa: E402
    PPRKBundle,
    PPRKCalculationBinding,
    PPRKContentsEntry,
    PPRKDocumentPart,
    PPRKPlacementBinding,
    PPRKSheet,
)
from crane_plan.pprk_models import ReleaseStatus  # noqa: E402
from crane_plan.pprk_context import scenario_render_sha256  # noqa: E402
from crane_plan.pprk_context import PPRKContext  # noqa: E402
from crane_plan.pprk_assets import load_asset_manifest  # noqa: E402
from crane_plan.pprk_composer import compose_pprk  # noqa: E402
from crane_plan.pprk_models import PPRKReleaseConfig  # noqa: E402
from crane_plan.pprk_templates import load_template_catalog  # noqa: E402
from crane_plan.report import generate_report  # noqa: E402


def _project():
    project = ProjectInput(
        "Жилой дом",
        "Москва",
        2026,
        "",
        "",
        -3.0,
        30.0,
        SiteInput(
            [(-45, -35), (45, -35), (45, 35), (-45, 35)],
            [(-12, -8), (12, -8), (12, 8), (-12, 8)],
            unloading_zone=[(-35, -5), (-27, -5), (-27, 5), (-35, 5)],
            storage_zones=[[(-25, -6), (-17, -6), (-17, 6), (-25, 6)]],
        ),
        [Load("Опалубка", 1200, 120, 2.4, 1.2, 1.0, lifts=10)],
        [WorkPoint(0, -5, -1, 0), WorkPoint(5, 0, 20, 0)],
        organization="ООО Проект",
        project_code="ППРК-01",
        floors=12,
    )
    return project


def _sozr(crane_id, x):
    point = SOZRPoint(
        f"{crane_id}-1",
        x + 18,
        0,
        0,
        18,
        SOZRRestrictionClass.CONDITIONAL,
        "zone-1",
        8,
        "низ груза выше 11 м",
    )
    return SOZRPlan(crane_id, 45, (), (), (point,), (), "SOZR-1.0", x, 0)


def _scenario():
    first = Placement(
        "cfg-1",
        "Liebherr 130 EC-B 6",
        -20,
        0,
        [0],
        42,
        38,
        45,
        jib_level_m=44,
        max_free_standing_height_m=38,
        accepted_crane_height_m=63,
        tie_in_levels_m=[32],
        tie_in_stage_sections=[5],
        tie_nearest_floors=[10],
        required_tie_length_m=12,
        sozr_plan=_sozr("К1", -20),
    )
    second = Placement(
        "cfg-1",
        "Liebherr 130 EC-B 6",
        20,
        0,
        [1],
        42,
        41,
        45,
        jib_level_m=47,
        accepted_crane_height_m=66,
        sozr_plan=_sozr("К2", 20),
    )
    joint = JointCranePlan(
        40,
        5,
        2,
        3,
        2,
        2,
        True,
        300,
        overlap_polygon=[(-5, -10), (5, -10), (5, 10), (-5, 10)],
        schedule_stages=["К1 работает", "К2 работает"],
    )
    return ScenarioResult("PASS", [first, second], [], [], joint_plan=joint)


def _bundle(graphical_ids, project=None):
    service = (
        ("service.title", "Титульный лист"),
        ("service.approvals", "Лист согласований"),
        ("service.familiarization", "Лист регистрации ознакомления"),
        ("service.contents", "Состав проекта"),
    )
    parts = []
    for page, (part_id, title) in enumerate(service, 1):
        fields = ()
        approvals = ()
        if part_id == "service.title":
            fields = (("title", "ППРк"), ("object_name", "Жилой дом"), ("object_address", "Москва"))
        if part_id == "service.approvals":
            approvals = tuple(("", "", "", "", "") for _ in range(8))
        parts.append(PPRKDocumentPart(part_id, title, "service", (PPRKSheet(part_id, title, "service", page_number=page, fields=fields, approval_slots=approvals),)))
    note = PPRKDocumentPart(
        "section.general",
        "Общие данные",
        "note",
        (PPRKSheet("section.general", "Общие данные", "note", page_number=5, section_id="general"),),
        rendered_text="Расчётные графические листы приведены далее.",
    )
    parts.append(note)
    for index, sheet_id in enumerate(graphical_ids, 1):
        target = f"drawing.{sheet_id}"
        parts.append(PPRKDocumentPart(target, sheet_id, "graphical", (PPRKSheet(target, sheet_id, "graphical", designation=f"ГЧ-{index:02d}"),)))
    contents = tuple(
        PPRKContentsEntry(sheet.sheet_id, part.part_id, sheet.title, sheet.designation or str(sheet.page_number or ""), part.kind)
        for part in parts
        for sheet in part.sheets
    )
    from crane_plan.pprk_context import PPRKActiveLoad
    loads = tuple(PPRKActiveLoad(index, load.name, load.active, load.load_kg, load.rigging_kg, load.total_kg, (load.length_m, load.width_m, load.height_m), (), False, lifts=load.lifts) for index, load in enumerate((project or _project()).loads) if load.active)
    return PPRKBundle(tuple(parts), contents, ("general",), (), (), (), ReleaseStatus.PRELIMINARY, ReleaseStatus.PRELIMINARY, False, active_loads=loads)


def _bound_bundle(graphical_ids, scenario=None, danger_offset=9.4):
    scenario = scenario or _scenario()
    placements = tuple(
        PPRKPlacementBinding(
            legacy_configuration_reference=placement.crane_id,
            model=placement.model,
            x_m=placement.x,
            y_m=placement.y,
            max_radius_m=placement.max_radius_m,
            jib_length_m=placement.jib_length_m,
            required_hook_height_m=placement.required_hook_height_m,
            jib_level_m=placement.jib_level_m,
        )
        for placement in scenario.placements
    )
    return replace(
        _bundle(graphical_ids),
        calculation_binding=PPRKCalculationBinding(
            "a" * 64,
            "b" * 64,
            placements,
            scenario_render_sha256=scenario_render_sha256(scenario),
            verified_danger_zone_offset_m=danger_offset,
        ),
    )


class PPRKSheetTests(unittest.TestCase):
    def test_choose_sheet_format_uses_smallest_standard_that_preserves_extents(self):
        from crane_plan.pprk_sheets import choose_sheet_format

        self.assertEqual(choose_sheet_format((0, 0, 350, 210), 2.5).name, "A3")
        self.assertEqual(choose_sheet_format((0, 0, 500, 330), 2.5).name, "A2")
        self.assertEqual(choose_sheet_format((0, 0, 760, 480), 2.5).name, "A1")
        with self.assertRaises(ValueError):
            choose_sheet_format((0, 0, 900, 600), 2.5)
        with self.assertRaises(ValueError):
            choose_sheet_format((0, 0, 10, 10), 1.0)

    def test_planner_preserves_bundle_order_without_inventing_unverified_zero_stages(self):
        from crane_plan.pprk_sheets import calculated_sheet_page_map, plan_calculated_sheets

        bundle = _bundle(("SITE_PLAN", "SOZR_PLAN", "VERTICAL_SECTION", "JOINT_WORK_PLAN"))
        plans = plan_calculated_sheets(bundle, _project(), _scenario())

        self.assertEqual([plan.source_sheet_id for plan in plans[:1]], ["drawing.SITE_PLAN"])
        self.assertEqual(plans[0].stage, "accepted")
        self.assertEqual(plans[0].designation, "ГЧ-01")
        self.assertLess(
            next(index for index, plan in enumerate(plans) if plan.source_sheet_id == "drawing.SOZR_PLAN"),
            next(index for index, plan in enumerate(plans) if plan.source_sheet_id == "drawing.VERTICAL_SECTION"),
        )
        self.assertEqual(sum(plan.render_kind == "sozr" for plan in plans), 2)
        self.assertEqual(plans[-1].source_sheet_id, "drawing.JOINT_WORK_PLAN")
        page_map = calculated_sheet_page_map(plans, 24)
        self.assertEqual(page_map["drawing.SITE_PLAN"], 24)

    def test_draw_calculated_plan_and_section_reuse_existing_geometry_with_stage_labels(self):
        from crane_plan.pprk_sheets import CalculatedSheetRenderContext, draw_calculated_sheet, plan_calculated_sheets

        project = _project(); scenario = _scenario()
        plans = plan_calculated_sheets(_bundle(("SITE_PLAN", "VERTICAL_SECTION")), project, scenario)
        render_context = CalculatedSheetRenderContext(project, scenario)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sheets.pdf"
            canvas = Canvas(str(path), pagesize=plans[0].sheet_format.page_size)
            draw_calculated_sheet(canvas, plans[0], render_context)
            section = next(plan for plan in plans if plan.render_kind == "vertical_section")
            canvas.setPageSize(section.sheet_format.page_size)
            draw_calculated_sheet(canvas, section, render_context)
            canvas.save()
            reader = PdfReader(str(path))
            texts = [page.extract_text() for page in reader.pages]

        self.assertEqual(len(texts), 2)
        self.assertIn("СТРОЙГЕНПЛАН", texts[0])
        self.assertNotIn("НИЖЕ 0,000", texts[0])
        self.assertNotIn("ВЫШЕ 0,000", texts[0])
        self.assertIn("ВЫСОТНАЯ ПРИВЯЗКА", texts[1])
        self.assertIn("П1", texts[1])

    def test_bundle_report_appends_graphical_sheets_in_bundle_order_and_mixed_sizes(self):
        project = _project(); scenario = _scenario()
        bundle = _bundle(("SITE_PLAN", "SOZR_PLAN", "VERTICAL_SECTION", "JOINT_WORK_PLAN", "JOINT_WORK_SCHEDULE"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "full.pdf"
            generate_report(path, project, [scenario], bundle=bundle)
            reader = PdfReader(str(path))
            texts = [page.extract_text() or "" for page in reader.pages]
            sizes = [(float(page.mediabox.width), float(page.mediabox.height)) for page in reader.pages]

        plan_index = next(index for index, text in enumerate(texts) if text.startswith("СТРОЙГЕНПЛАН"))
        sozr_index = next(index for index, text in enumerate(texts) if text.startswith("СОЗР"))
        section_index = next(index for index, text in enumerate(texts) if text.startswith("ВЫСОТНАЯ ПРИВЯЗКА"))
        joint_index = next(index for index, text in enumerate(texts) if text.startswith("СХЕМА СОВМЕСТНОЙ РАБОТЫ"))
        schedule_index = next(index for index, text in enumerate(texts) if text.startswith("ГРАФИК СОВМЕСТНОЙ РАБОТЫ"))
        self.assertLess(plan_index, sozr_index)
        self.assertLess(sozr_index, section_index)
        self.assertLess(section_index, joint_index)
        self.assertLess(joint_index, schedule_index)
        self.assertNotEqual(sizes[0], sizes[plan_index])

    def test_route_plan_has_its_own_heading_and_keeps_sozr_point_table(self):
        from crane_plan.pprk_sheets import CalculatedSheetRenderContext, draw_calculated_sheet, plan_calculated_sheets

        project = _project(); scenario = _scenario()
        route = plan_calculated_sheets(_bundle(("ROUTE_PLAN",)), project, scenario)[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "route.pdf"
            canvas = Canvas(str(path), pagesize=route.sheet_format.page_size)
            draw_calculated_sheet(canvas, route, CalculatedSheetRenderContext(project, scenario))
            canvas.save()
            text = PdfReader(str(path)).pages[0].extract_text()

        self.assertIn("МАРШРУТЫ ПОДАЧИ", text)
        self.assertIn("К1-1", text)

    def test_planner_fails_closed_when_required_scale_cannot_preserve_readability_on_a1(self):
        from crane_plan.pprk_sheets import plan_calculated_sheets

        project = _project()
        project.site.boundary = [(-100, -80), (100, -80), (100, 80), (-100, 80)]
        with self.assertRaisesRegex(ValueError, "A1"):
            plan_calculated_sheets(_bundle(("SITE_PLAN",)), project, _scenario())

    def test_far_restricted_zone_and_two_hundred_metre_section_fail_before_rendering(self):
        from crane_plan.models import RestrictedZone, RestrictedZoneKind
        from crane_plan.pprk_sheets import plan_calculated_sheets

        project = _project()
        project.site.restricted_zones = [
            RestrictedZone(
                "far",
                "Удалённая зона",
                RestrictedZoneKind.FULL_EXCLUSION,
                [(995, -5), (1005, -5), (1005, 5), (995, 5)],
                20,
            )
        ]
        with self.assertRaisesRegex(ValueError, "A1"):
            plan_calculated_sheets(_bundle(("SITE_PLAN",)), project, _scenario())

        project = _project()
        project.parapet_m = 200
        with self.assertRaisesRegex(ValueError, "A1"):
            plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, _scenario())

        project = _project()
        project.section_building_contour = [(0, 0), (20, 0), (20, 30), (0, 30)]
        scenario = _scenario()
        scenario.placements[0].accepted_crane_height_m = 200
        with self.assertRaisesRegex(ValueError, "A1"):
            plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, scenario)

        project = _project()
        project.section_building_contour = [(-1000, 0), (1000, 0), (1000, 30), (-1000, 30)]
        with self.assertRaisesRegex(ValueError, "A1"):
            plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, _scenario())

        project = _project()
        project.section_building_contour = [(0, -1000), (20, -1000), (20, 1000), (0, 1000)]
        with self.assertRaisesRegex(ValueError, "A1"):
            plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, _scenario())

        project = _project()
        project.section_building_contour = [(0, 0), (20, 0), (20, 30), (0, 30)]
        scenario = _scenario()
        scenario.placements[0].x = 1000
        with self.assertRaisesRegex(ValueError, "A1"):
            plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, scenario)

    def test_one_hundred_loads_are_split_into_listed_physical_sheets(self):
        from crane_plan.pprk_sheets import expand_bundle_graphical_parts, plan_calculated_sheets

        project = _project()
        project.loads = [
            Load(f"Груз {index}", 1000 + index, 100, 2, 1, 1, lifts=1)
            for index in range(100)
        ]
        bundle = _bundle(("LOAD_SCHEDULE",), project)
        plans = plan_calculated_sheets(bundle, project, _scenario())
        expanded = expand_bundle_graphical_parts(bundle, plans)

        self.assertGreater(len(plans), 1)
        self.assertTrue(all(plan.render_kind == "load_schedule" for plan in plans))
        self.assertEqual(sum(plan.item_end - plan.item_start for plan in plans), 100)
        graphical_entries = [entry for entry in expanded.contents if entry.kind == "graphical"]
        self.assertEqual(len(graphical_entries), len(plans))
        self.assertEqual([entry.number for entry in graphical_entries], [plan.designation for plan in plans])

    def test_bundle_binds_exactly_one_selected_scenario_and_never_uses_first_by_position(self):
        selected = _scenario()
        rejected = deepcopy(selected)
        rejected.status = "REJECTED"
        rejected.placements[0].model = "ОШИБОЧНЫЙ КРАН"
        rejected.placements[0].x = 999
        bundle = _bound_bundle(("SITE_PLAN",), selected)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "selected.pdf"
            generate_report(path, _project(), [rejected, selected], bundle=bundle)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        self.assertIn("Liebherr 130 EC-B 6", text)
        self.assertNotIn("ОШИБОЧНЫЙ КРАН", text)

        with self.assertRaisesRegex(ValueError, "сценар"):
            generate_report(Path(tempfile.gettempdir()) / "ambiguous.pdf", _project(), [selected, deepcopy(selected)], bundle=bundle)

    def test_canonical_binding_rejects_any_changed_render_engineering_state(self):
        from crane_plan.pprk_sheets import bind_calculated_scenario

        selected = _scenario()
        bundle = _bound_bundle(("SITE_PLAN",), selected)
        mutations = []
        changed = deepcopy(selected); changed.status = "REJECTED"; mutations.append(changed)
        changed = deepcopy(selected); changed.placements[0].accepted_crane_height_m += 5; mutations.append(changed)
        changed = deepcopy(selected); changed.placements[0].allowed_sector_start_deg = 20; mutations.append(changed)
        changed = deepcopy(selected); changed.placements[0].tie_in_levels_m = [27]; mutations.append(changed)
        changed = deepcopy(selected); changed.routes = [LiftRoute("OP-1", (RouteWaypoint(0, 0, 10, "slew"),), 10, (RouteAlternative("direct", True, 3, 5),), "c" * 64)]; mutations.append(changed)
        changed = deepcopy(selected); changed.placements[0].sozr_plan = replace(changed.placements[0].sozr_plan, points=()); mutations.append(changed)
        changed = deepcopy(selected); changed.joint_plan.schedule_stages.append("подмена"); mutations.append(changed)
        for changed in mutations:
            with self.subTest(change=changed.to_dict()):
                with self.assertRaisesRegex(ValueError, "сценар"):
                    bind_calculated_scenario(bundle, [changed])
                self.assertIs(bind_calculated_scenario(bundle, [changed, selected]), selected)

    def test_long_load_names_split_by_measured_wrapped_height_and_fit_each_sheet(self):
        from crane_plan.pprk_sheets import load_schedule_table_height, plan_calculated_sheets

        project = _project()
        project.loads = [
            Load(("Сверхдлинное наименование элемента монолитного здания " * 18) + str(index), 1000, 100, 2, 1, 1, lifts=1)
            for index in range(100)
        ]
        plans = plan_calculated_sheets(_bundle(("LOAD_SCHEDULE",), project), project, _scenario())
        self.assertGreater(len(plans), 5)
        self.assertEqual(sum(plan.item_end - plan.item_start for plan in plans), 100)
        for plan in plans:
            available = plan.sheet_format.page_size[1] - 73 * 72 / 25.4
            self.assertLessEqual(load_schedule_table_height(project, plan.item_start, plan.item_end), available + 0.01)

    def test_long_sozr_point_table_splits_and_each_physical_table_fits(self):
        from crane_plan.pprk_sheets import plan_calculated_sheets, sozr_table_height

        scenario = _scenario()
        template = scenario.placements[0].sozr_plan.points[0]
        points = tuple(replace(template, label=f"К1-{index}", x=float(index % 40), condition="условие " * 25) for index in range(120))
        scenario.placements[0].sozr_plan = replace(scenario.placements[0].sozr_plan, points=points)
        plans = [plan for plan in plan_calculated_sheets(_bundle(("SOZR_PLAN",)), _project(), scenario) if plan.crane_index == 0]
        self.assertGreater(len(plans), 1)
        self.assertEqual(sum(plan.item_end - plan.item_start for plan in plans), len(points))
        for plan in plans:
            available = plan.sheet_format.page_size[1] - 92 * 72 / 25.4
            self.assertLessEqual(sozr_table_height(scenario.placements[0].sozr_plan, plan.item_start, plan.item_end), available + 0.01)

    def test_bundle_site_plan_uses_verified_danger_offset_without_normative_recalculation(self):
        selected = _scenario()
        bundle = _bound_bundle(("SITE_PLAN",), selected, danger_offset=12.75)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "crane_plan.report.danger_zone_offset_from_outer_edge",
            side_effect=AssertionError("legacy recalculation must not run"),
        ):
            path = Path(tmp) / "verified-danger.pdf"
            generate_report(path, _project(), [selected], bundle=bundle)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        self.assertIn("12.75", text)

    def test_unknown_graphical_reference_is_rejected_not_silently_removed(self):
        from crane_plan.pprk_sheets import plan_calculated_sheets

        with self.assertRaisesRegex(ValueError, "UNKNOWN_DRAWING"):
            plan_calculated_sheets(_bundle(("UNKNOWN_DRAWING",)), _project(), _scenario())

    def test_contents_lists_every_emitted_graphical_designation_once(self):
        project = _project()
        project.loads = [Load(f"Груз {index}", 1000, 100, 2, 1, 1, lifts=1) for index in range(50)]
        bundle = _bundle(("LOAD_SCHEDULE", "SOZR_PLAN"), project)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "expanded.pdf"
            generate_report(path, project, [_scenario()], bundle=bundle)
            texts = [page.extract_text() or "" for page in PdfReader(str(path)).pages]
        contents = texts[3]
        emitted_designations = []
        for text in texts[5:]:
            emitted_designations.extend(token.rstrip(";,.:") for token in text.split() if token.startswith("ГЧ-"))
        for designation in sorted(set(emitted_designations)):
            self.assertEqual(contents.count(designation), 1, designation)
        self.assertIn("стр.", contents)

    def test_composed_bundle_preserves_pending_appendix_references_while_resolving_drawings(self):
        values = {
            "object_name": "Жилой дом",
            "object_address": "Москва",
            "crane_model": "Liebherr 130 EC-B 6",
            "project_basis": "Задание заказчика",
            "external_document_register": "по ведомости",
        }
        context = PPRKContext(
            "Жилой дом", "Москва", "ООО Проект", "ППРК-01", "VERIFIED",
            "RUN-1", "a" * 64, "b" * 64, ("CRANE-1",), ("OP-1",), values, (), (),
        )
        bundle = compose_pprk(
            context,
            load_template_catalog(),
            load_asset_manifest(),
            PPRKReleaseConfig(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "composed.pdf"
            generate_report(path, _project(), [_scenario()], bundle=bundle)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        self.assertIn("appendix.EXTERNAL_DOCUMENT_REGISTER", text)
        self.assertIn("ОЖИДАЕТ ВКЛЮЧЕНИЯ", text)

    @staticmethod
    def calibrated_section(directory, origin_x):
        source = Path(directory) / "section.pdf"
        canvas = Canvas(str(source), pagesize=(300, 200))
        canvas.drawString(20, 180, "source section")
        canvas.save()
        project = _project()
        project.source_section_pdf = str(source)
        project.section_render_scale = 1.5
        project.section_m_per_pixel = 0.5
        project.section_origin_x_px = origin_x
        project.section_origin_y_px = 270
        project.section_axis_dx = 0
        project.section_axis_dy = -1
        project.section_building_contour = [(0, 0), (20, 0), (20, 30), (0, 30)]
        return project

    def test_section_refuses_joint_dimension_beyond_a1_before_issuing_any_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.calibrated_section(tmp, 450)
            path = Path(tmp) / "out.pdf"
            with self.assertRaisesRegex(ValueError, "A1"):
                generate_report(path, project, [_scenario()], bundle=_bundle(("VERTICAL_SECTION",)))
            self.assertFalse(path.exists())

    def test_section_format_accounts_for_drawn_symbols_dimension_and_labels(self):
        from crane_plan.pprk_sheets import CalculatedSheetRenderContext, draw_calculated_sheet, plan_calculated_sheets
        import pypdfium2 as pdfium
        from reportlab.lib.units import mm

        with tempfile.TemporaryDirectory() as tmp:
            for origin, expected in ((None, "A2"), (225, "A2"), (380, "A1")):
                with self.subTest(origin=origin):
                    project = _project() if origin is None else self.calibrated_section(tmp, origin)
                    scenario = _scenario()
                    sheet, = plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, scenario)
                    self.assertEqual(sheet.sheet_format.name, expected)
                    path = Path(tmp) / f"out-{origin}.pdf"
                    canvas = Canvas(str(path))
                    draw_calculated_sheet(canvas, sheet, CalculatedSheetRenderContext(project, scenario))
                    canvas.save()
                    self.assertIn("чистый зазор", PdfReader(str(path)).pages[0].extract_text())
                    with pdfium.PdfDocument(str(path)) as pdf:
                        page = pdf[0]
                        width, height = page.get_size()
                        for obj in page.get_objects():
                            left, bottom, right, top = obj.get_bounds()
                            self.assertGreater(left, 19 * mm)
                            self.assertGreater(bottom, 4 * mm)
                            self.assertLess(right, width - 4 * mm)
                            self.assertLess(top, height - 4 * mm)

    def test_uncalibrated_section_notes_clear_the_printed_masts_by_three_mm(self):
        import pdfplumber
        from reportlab.lib.units import mm
        from crane_plan.pprk_sheets import CalculatedSheetRenderContext, draw_calculated_sheet, plan_calculated_sheets

        project, scenario = _project(), _scenario()
        sheet, = plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, scenario)
        self.assertEqual(sheet.sheet_format.name, "A2")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.pdf"
            canvas = Canvas(str(path))
            draw_calculated_sheet(canvas, sheet, CalculatedSheetRenderContext(project, scenario))
            canvas.save()
            with pdfplumber.open(path) as pdf:
                page = pdf.pages[0]
                masts = [r for r in page.rects if abs(r["width"] - 7 * mm) < 0.01 and r["height"] > 100 * mm]
                self.assertEqual(len(masts), 2)
                for text in (
                    "Разность осей стрел 3.0 м = высота конструкции 2.0 м + свободный зазор 1.0 м (не менее 1.0 м).",
                    "Разрез не откалиброван: показана расчётная схема без привязки к исходному PDF.",
                    "Проверить по паспорту крана и проекту пристёжек",
                ):
                    with self.subTest(note=text):
                        note, = page.search(text, regex=False)
                        for mast in masts:
                            gap = max(mast["x0"] - note["x1"], note["x0"] - mast["x1"],
                                      mast["top"] - note["bottom"], note["top"] - mast["bottom"])
                            self.assertGreaterEqual(gap - mast["linewidth"] / 2, 3 * mm)

    def test_calibrated_section_notes_clear_printed_towers_stamp_and_inset(self):
        self.assert_calibrated_note_clearance(200, 300)

    def test_calibrated_section_moves_notes_when_tower_bases_occupy_footer(self):
        self.assert_calibrated_note_clearance(65, 323)

    def assert_calibrated_note_clearance(self, origin_x, origin_y):
        import pdfplumber
        from reportlab.lib.units import mm
        from crane_plan.pprk_sheets import CalculatedSheetRenderContext, draw_calculated_sheet, plan_calculated_sheets

        with tempfile.TemporaryDirectory() as tmp:
            project = self.calibrated_section(tmp, origin_x)
            project.section_origin_y_px = origin_y
            scenario = _scenario()
            sheet, = plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, scenario)
            self.assertEqual(sheet.sheet_format.name, "A2")
            path = Path(tmp) / "section-notes.pdf"
            canvas = Canvas(str(path))
            draw_calculated_sheet(canvas, sheet, CalculatedSheetRenderContext(project, scenario))
            canvas.save()
            with pdfplumber.open(path) as pdf:
                page = pdf.pages[0]
                masts = [r for r in page.rects if abs(r["width"] - 7 * mm) < 0.01 and r["height"] > 100 * mm]
                self.assertEqual(len(masts), 2)
                tower_colors = {r["stroking_color"] for r in masts}
                obstacles = [obj for obj in page.rects + page.lines + page.curves
                             if obj["stroking_color"] in tower_colors]
                # Reserve the full stamp and tie-detail area, including its caption.
                obstacles.extend([
                    dict(x0=page.width - 190 * mm, x1=page.width - 5 * mm, y0=5 * mm, y1=45 * mm, linewidth=.5),
                    dict(x0=page.width - 90 * mm, x1=page.width - 5 * mm, y0=50 * mm, y1=94 * mm, linewidth=1.2),
                ])
                # Content-stream order also finds text obscured by other page objects.
                chars = [char for char in page.chars if not char["text"].isspace()]
                content = "".join(char["text"] for char in chars)
                for note in (
                    "Разность осей стрел 3.0 м = высота конструкции 2.0 м + свободный зазор 1.0 м (не менее 1.0 м).",
                    "Привязка выполнена по двум точкам PDF-разреза. Схема пристёжек предварительная; узлы и нагрузки - отдельный проект.",
                    "Проверить по паспорту крана и проекту пристёжек",
                ):
                    with self.subTest(note=note):
                        expected = "".join(note.split())
                        self.assertEqual(content.count(expected), 1)
                        start = content.index(expected)
                        glyphs = chars[start:start + len(expected)]
                        self.assertAlmostEqual(min(c["size"] for c in glyphs), 7, places=5)
                        clearance = min(
                            max(o["x0"] - c["x1"], c["x0"] - o["x1"], o["y0"] - c["y1"], c["y0"] - o["y1"])
                            - o["linewidth"] / 2 for c in glyphs for o in obstacles
                        )
                        self.assertGreaterEqual(clearance / mm, 3)

    def test_section_refuses_overwide_text_even_when_all_anchor_coordinates_fit(self):
        from crane_plan.pprk_sheets import plan_calculated_sheets

        for field in ("model", "project_stage"):
            with self.subTest(field=field):
                project, scenario = _project(), _scenario()
                target = scenario.placements[0] if field == "model" else project
                setattr(target, field, "W" * 1500)
                with self.assertRaisesRegex(ValueError, "A1"):
                    plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, scenario)

    def test_vertical_format_includes_free_standing_marker_and_calibrated_transform(self):
        from crane_plan.pprk_sheets import plan_calculated_sheets

        scenario = _scenario()
        scenario.placements[0].max_free_standing_height_m = 200
        with self.assertRaisesRegex(ValueError, "A1"):
            plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), _project(), scenario)

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "section.pdf"
            canvas = Canvas(str(source), pagesize=(300, 200))
            canvas.drawString(20, 180, "section")
            canvas.save()
            project = _project()
            project.source_section_pdf = str(source)
            project.section_m_per_pixel = 0.1
            project.section_origin_x_px = 50_000
            project.section_origin_y_px = 100
            project.section_axis_dx = 0
            project.section_axis_dy = -1
            with self.assertRaisesRegex(ValueError, "A1"):
                plan_calculated_sheets(_bundle(("VERTICAL_SECTION",)), project, _scenario())


if __name__ == "__main__":
    unittest.main()

