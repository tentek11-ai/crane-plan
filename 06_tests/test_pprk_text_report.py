import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import re
import sys


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from pypdf import PdfReader  # noqa: E402
import pdfplumber  # noqa: E402

from crane_plan.models import ProjectInput, SiteInput  # noqa: E402
from crane_plan.pprk_assets import load_asset_manifest  # noqa: E402
from crane_plan.pprk_composer import (  # noqa: E402
    PPRKBundle,
    PPRKContentsEntry,
    PPRKDocumentPart,
    PPRKSheet,
    compose_pprk,
)
from crane_plan.pprk_context import PPRKContext  # noqa: E402
from crane_plan.pprk_models import CompletenessIssue, PPRKReleaseConfig, ReleaseStatus  # noqa: E402
from crane_plan.pprk_text_report import (  # noqa: E402
    build_contents_page_map,
    build_explanatory_note_story,
    render_pprk_text_report,
)
from crane_plan.pprk_templates import load_template_catalog  # noqa: E402
from crane_plan.report import generate_report  # noqa: E402


def _sheet(part_id, title, kind, page, **changes):
    values = dict(
        sheet_id=part_id,
        title=title,
        kind=kind,
        page_number=page,
    )
    values.update(changes)
    return PPRKSheet(**values)


def sample_bundle(*, long_text=False):
    title_fields = (
        ("title", "ППРк на возведение монолитного здания"),
        ("lifting_equipment_type", "Башенный кран"),
        ("crane_model", "Liebherr 130 EC-B 6"),
        ("crane_configurations", "60 м; 6 т"),
        ("approval_marks", "УТВЕРЖДАЮ / СОГЛАСОВАНО"),
        ("object_name", "Жилой дом"),
        ("object_address", "г. Москва, ул. Проектная, д. 1"),
        ("organization", "ООО Проект"),
        ("project_code", "ППРК-01"),
        ("developer_position", "Главный инженер проекта"),
        ("developer_name", "⟦НЕ ЗАПОЛНЕНО: developer_name⟧"),
        ("developer_date", "04.11.2026"),
        ("manager_position", "Технический директор"),
        ("manager_name", "Петров П.П."),
        ("manager_date", "04.11.2026"),
        ("issue_city", "Москва"),
        ("issue_year", "2026"),
    )
    approvals = tuple(
        ("Организация", "Должность", f"Фамилия {index}", "Подпись", "04.11.2026")
        for index in range(1, 9)
    )
    general_text = (
        "Проект определяет безопасную организацию работ башенным краном. "
        "Все численные параметры принимаются из проверенного расчётного протокола."
    )
    if long_text:
        general_text = "\n\n".join(
            f"Пункт {index}. {general_text} Контрольная метка LONG-{index:02d}."
            for index in range(1, 46)
        )
    safety_text = (
        "Перемещение груза над людьми запрещается. "
        "Работы выполняются по утвержденным схемам строповки."
    )
    parts = (
        PPRKDocumentPart(
            "service.title",
            "Титульный лист",
            "service",
            (_sheet("service.title", "Титульный лист", "service", 1, fields=title_fields),),
        ),
        PPRKDocumentPart(
            "service.approvals",
            "Лист согласований",
            "service",
            (_sheet("service.approvals", "Лист согласований", "service", 2, approval_slots=approvals),),
        ),
        PPRKDocumentPart(
            "service.familiarization",
            "Лист регистрации ознакомления",
            "service",
            (_sheet("service.familiarization", "Лист регистрации ознакомления", "service", 3),),
        ),
        PPRKDocumentPart(
            "service.contents",
            "Состав проекта",
            "service",
            (_sheet("service.contents", "Состав проекта", "service", 4),),
        ),
        PPRKDocumentPart(
            "section.general",
            "Общие данные и назначение ППРк",
            "note",
            (_sheet("section.general", "Общие данные и назначение ППРк", "note", 5, section_id="general"),),
            rendered_text=general_text,
        ),
        PPRKDocumentPart(
            "section.safe_operations",
            "Безопасное производство работ с применением ПС",
            "note",
            (_sheet("section.safe_operations", "Безопасное производство работ с применением ПС", "note", 6, section_id="safe_operations"),),
            rendered_text=safety_text,
        ),
    )
    contents = tuple(
        PPRKContentsEntry(
            sheet.sheet_id,
            part.part_id,
            sheet.title,
            str(sheet.page_number),
            part.kind,
        )
        for part in parts
        for sheet in part.sheets
    )
    return PPRKBundle(
        parts=parts,
        contents=contents,
        included_section_ids=("general", "safe_operations"),
        inclusion_reasons=(("general", "required:always"), ("safe_operations", "required:always")),
        exclusion_reasons=(),
        completeness_issues=(
            CompletenessIssue(
                "PPRK_TITLE_FIELD_REQUIRED",
                "Не заполнено имя разработчика.",
                True,
                "title/developer_name",
            ),
        ),
        requested_status=ReleaseStatus.PRELIMINARY,
        effective_status=ReleaseStatus.PRELIMINARY,
        production_allowed=False,
    )


def sample_project():
    return ProjectInput(
        "Жилой дом",
        "Москва",
        2026,
        "",
        "",
        -3,
        45,
        SiteInput(
            [(-50, -50), (50, -50), (50, 50), (-50, 50)],
            [(-10, -10), (10, -10), (10, 10), (-10, 10)],
        ),
        [],
        [],
    )


def real_composed_bundle():
    values = {
        "object_name": "Жилой дом",
        "object_address": "г. Москва, ул. Проектная, д. 1",
        "crane_model": "Liebherr 130 EC-B 6",
        "crane_count": 1,
        "crane_configurations": ("Liebherr 130 EC-B 6; стрела 60 м",),
        "building_height_m": 61.0,
        "floors": 20,
        "jib_length_m": (60.0,),
        "hook_height_m": (63.4,),
        "max_capacity_t": 6.0,
        "work_radii_m": (42.0,),
        "tower_sections": (4,),
        "tie_levels_m": (),
        "active_loads": ("Опалубка",),
        "load_masses_kg": (1800.0,),
        "rigging_masses_kg": (120.0,),
        "lift_counts": (120,),
        "max_load_length_m": 2.5,
        "storage_zone_count": 1,
        "unloading_zone": ((0.0, 0.0), (3.0, 0.0), (3.0, 5.0)),
        "sozr_points": ("Т1", "Т2"),
        "route_register": ("OP-W1-L1",),
        "project_basis": "Задание заказчика",
        "plan_sheet_refs": "ГЧ-01, ГЧ-02",
        "responsible_fire_safety": "назначается приказом",
        "max_wind_speed_m_s": 10.0,
        "fall_protection_system": "страховочная система с анкерной линией",
        "power_supply_scheme": "от ВРУ по самостоятельной линии",
        "waste_plan": "контейнерный вывоз по графику",
        "external_document_register": "паспорта и акты по ведомости",
    }
    context = PPRKContext(
        object_name=values["object_name"],
        object_address=values["object_address"],
        organization="ООО Проект",
        project_code="ППРК-01",
        verification_status="VERIFIED",
        protocol_run_id="RUN-1",
        protocol_input_sha256="a" * 64,
        protocol_result_sha256="b" * 64,
        crane_ids=("CRANE-1",),
        operation_ids=("OP-W1-L1",),
        values=values,
        traces=(),
        completeness_issues=(),
    )
    return compose_pprk(
        context,
        load_template_catalog(),
        load_asset_manifest(),
        PPRKReleaseConfig(),
    )


class PPRKTextReportTests(unittest.TestCase):
    def test_bundle_pdf_renders_exact_front_matter_order_and_eight_approvals(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = render_pprk_text_report(Path(temporary) / "bundle.pdf", sample_bundle())
            reader = PdfReader(str(path))
            texts = [page.extract_text() or "" for page in reader.pages]

        self.assertIn("ПРОЕКТ ПРОИЗВОДСТВА РАБОТ КРАНАМИ", texts[0])
        self.assertIn("ЛИСТ СОГЛАСОВАНИЙ", texts[1])
        self.assertIn("ЛИСТ РЕГИСТРАЦИИ ОЗНАКОМЛЕНИЯ", texts[2])
        self.assertIn("СОСТАВ ПРОЕКТА", texts[3])
        self.assertEqual(texts[1].count("СОГЛАСОВАНО"), 8)
        self.assertIn("Общие данные и назначение ППРк", texts[3])
        self.assertIn("Безопасное производство работ с применением ПС", texts[3])

    def test_contents_page_does_not_silently_drop_bundle_entries(self):
        bundle = sample_bundle()
        extra_parts = tuple(
            PPRKDocumentPart(
                f"appendix.extra-{index}",
                f"Приложение контрольное {index:02d}",
                "appendix",
                (
                    _sheet(
                        f"appendix.extra-{index}",
                        f"Приложение контрольное {index:02d}",
                        "appendix",
                        6 + index,
                    ),
                ),
            )
            for index in range(1, 35)
        )
        extra_contents = tuple(
            PPRKContentsEntry(
                part.sheets[0].sheet_id,
                part.part_id,
                part.title,
                str(part.sheets[0].page_number),
                part.kind,
            )
            for part in extra_parts
        )
        bundle = replace(
            bundle,
            parts=(*bundle.parts, *extra_parts),
            contents=(*bundle.contents, *extra_contents),
        )

        with tempfile.TemporaryDirectory() as temporary:
            path = render_pprk_text_report(Path(temporary) / "contents.pdf", bundle)
            contents_text = PdfReader(str(path)).pages[3].extract_text() or ""

        self.assertIn("Приложение контрольное 34", contents_text)

    def test_bundle_pdf_contains_all_note_text_visible_placeholder_and_no_master_tokens(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = render_pprk_text_report(
                Path(temporary) / "long.pdf", sample_bundle(long_text=True), author=""
            )
            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)

        self.assertGreater(len(reader.pages), 6)
        self.assertIn("ПОЯСНИТЕЛЬНАЯ ЗАПИСКА", text)
        self.assertIn("LONG-01", text)
        self.assertIn("LONG-45", text)
        self.assertIn("НЕ ЗАПОЛНЕНО: developer_name", text)
        self.assertIn("Перемещение груза над людьми запрещается", text)
        for forbidden in ("Тружеников", "Хамовник", "АрхиКом", "AC-TRZ"):
            self.assertNotIn(forbidden, text)

    def test_contents_uses_actual_start_page_when_a_section_wraps(self):
        safety_title = "Безопасное производство работ с применением ПС"
        with tempfile.TemporaryDirectory() as temporary:
            path = render_pprk_text_report(
                Path(temporary) / "wrapped.pdf", sample_bundle(long_text=True)
            )
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]

        actual_page = next(
            index for index, text in enumerate(pages[4:], start=5) if safety_title in text
        )
        self.assertGreater(actual_page, 6)
        self.assertRegex(
            pages[3],
            re.compile(re.escape(safety_title) + r"\s+" + str(actual_page)),
        )

    def test_real_bundle_marks_unrendered_parts_without_false_numeric_pages(self):
        bundle = real_composed_bundle()
        with tempfile.TemporaryDirectory() as temporary:
            path = render_pprk_text_report(Path(temporary) / "real.pdf", bundle)
            reader = PdfReader(str(path))
            page_count = len(reader.pages)
            contents_text = reader.pages[3].extract_text() or ""

        page_map = build_contents_page_map(bundle, {}, rendered_page_count=page_count)
        rendered_ids = {
            sheet.sheet_id
            for part in bundle.parts
            if part.kind in {"service", "note"}
            for sheet in part.sheets
        }
        for entry in bundle.contents:
            if entry.target_id in rendered_ids:
                continue
            marker = page_map[entry.target_id]
            if entry.kind == "graphical":
                self.assertTrue(str(marker).startswith("ГЧ-"))
            else:
                self.assertEqual(marker, "ОЖИДАЕТ ВКЛЮЧЕНИЯ")
        self.assertIn("ОЖИДАЕТ ВКЛЮЧЕНИЯ", contents_text)
        self.assertTrue(
            all(
                not isinstance(page_map[entry.target_id], int)
                or page_map[entry.target_id] <= page_count
                for entry in bundle.contents
            )
        )

    def test_story_is_bundle_driven_and_keeps_each_included_section(self):
        story = build_explanatory_note_story(sample_bundle())
        rendered = " ".join(
            getattr(item, "text", "")
            for item in story
            if getattr(item, "text", "")
        )

        self.assertIn("Общие данные и назначение ППРк", rendered)
        self.assertIn("Безопасное производство работ с применением ПС", rendered)
        self.assertIn("Все численные параметры", rendered)

    def test_generate_report_accepts_bundle_without_breaking_blank_author(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = generate_report(
                Path(temporary) / "report.pdf",
                sample_project(),
                [],
                bundle=sample_bundle(),
            )
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)

        self.assertIn("ПРОЕКТ ПРОИЗВОДСТВА РАБОТ КРАНАМИ", text)
        self.assertIn("ПОЯСНИТЕЛЬНАЯ ЗАПИСКА", text)
        self.assertNotIn("None", text)

    def test_bundle_mode_rejects_legacy_page_selection_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "incomplete.pdf"
            with self.assertRaisesRegex(ValueError, "фиксирован"):
                generate_report(
                    path,
                    sample_project(),
                    [],
                    selected_pages=[4],
                    bundle=sample_bundle(),
                )
            self.assertFalse(path.exists())

    def test_long_title_approval_and_contents_values_are_not_silently_sliced(self):
        bundle = sample_bundle()
        long_organization = "Общество с ограниченной ответственностью Проектирование высотных строительных систем"
        long_developer = "Иванов-Константинопольский Владимир Александрович"
        long_manager = "Петрова-Сидорова Екатерина Михайловна"
        long_approval = "Акционерное общество Генеральный подрядчик и технический заказчик строительства"
        long_contents = "Приложение с полным юридическим наименованием документа и контрольной ведомостью оборудования"
        title = bundle.sheet("service.title")
        fields = dict(title.fields)
        fields.update(
            organization=long_organization,
            developer_name=long_developer,
            developer_date="04 ноября 2026 года",
            manager_name=long_manager,
            manager_date="05 ноября 2026 года",
        )
        approvals = list(bundle.sheet("service.approvals").approval_slots)
        approvals[0] = (long_approval, "Главный инженер проекта", long_developer, "Подпись", "04.11.2026")
        parts = list(bundle.parts)
        parts[0] = replace(parts[0], sheets=(replace(title, fields=tuple(fields.items())),))
        parts[1] = replace(
            parts[1],
            sheets=(replace(parts[1].sheets[0], approval_slots=tuple(approvals)),),
        )
        contents = list(bundle.contents)
        contents[-1] = replace(contents[-1], title=long_contents)
        bundle = replace(bundle, parts=tuple(parts), contents=tuple(contents))

        with tempfile.TemporaryDirectory() as temporary:
            path = render_pprk_text_report(Path(temporary) / "long-values.pdf", bundle)
            pages = [page.extract_text() or "" for page in PdfReader(str(path)).pages]
        normalized = " ".join("\n".join(pages[:4]).split())

        for value in (
            long_organization,
            long_developer,
            long_manager,
            long_approval,
            long_contents,
            "04 ноября 2026 года",
            "05 ноября 2026 года",
        ):
            self.assertIn(" ".join(value.split()), normalized)

    def test_very_long_project_title_fits_reserved_area_without_overlap(self):
        bundle = sample_bundle()
        long_title = ("TITLE548 полный проект производства работ кранами " * 20)[:548]
        self.assertEqual(len(long_title), 548)
        title_sheet = bundle.sheet("service.title")
        fields = dict(title_sheet.fields)
        fields["title"] = long_title
        parts = list(bundle.parts)
        parts[0] = replace(
            parts[0],
            sheets=(replace(title_sheet, fields=tuple(fields.items())),),
        )
        bundle = replace(bundle, parts=tuple(parts))

        with tempfile.TemporaryDirectory() as temporary:
            path = render_pprk_text_report(Path(temporary) / "long-title.pdf", bundle)
            extracted = PdfReader(str(path)).pages[0].extract_text() or ""
            with pdfplumber.open(path) as document:
                words = document.pages[0].extract_words()

        self.assertIn(" ".join(long_title.split()), " ".join(extracted.split()))
        title_words = [word for word in words if word["text"] == "TITLE548"]
        self.assertGreater(len(title_words), 1)
        table_top_points = 112 * 72 / 25.4
        self.assertLess(max(word["bottom"] for word in title_words), table_top_points)
        self.assertGreaterEqual(
            min(word["bottom"] - word["top"] for word in title_words),
            5.0,
        )

    def test_inline_missing_marker_is_emphasized_without_exposing_markup(self):
        bundle = sample_bundle()
        general = bundle.part("section.general")
        marked = replace(
            general,
            rendered_text="До значения ⟦НЕ ЗАПОЛНЕНО: clearance_m⟧ после значения.",
        )
        parts = tuple(marked if part.part_id == general.part_id else part for part in bundle.parts)
        story = build_explanatory_note_story(replace(bundle, parts=parts))
        markup = " ".join(getattr(item, "text", "") for item in story)

        self.assertIn('<font color="#C00000">НЕ ЗАПОЛНЕНО: clearance_m</font>', markup)
        self.assertNotIn("⟦", markup)


if __name__ == "__main__":
    unittest.main()

