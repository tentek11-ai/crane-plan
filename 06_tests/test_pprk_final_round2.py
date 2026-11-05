"""Round-two release boundaries: real GUI protocols, physical PDFs and rollback."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from reportlab.pdfgen.canvas import Canvas

from test_full_pprk_end_to_end import build_fixture, verify, save_via_gui, external_fixture
from test_pprk_composer import complete_approvals, verified_required_documents
from crane_plan.pprk_models import ExternalDocument, ReleaseStatus
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_regulations import load_release_regulations
from crane_plan.pprk_release_validation import validate_release_pdf
from crane_plan.pprk_release_workflow import prepare_release, require_saveable_release
from crane_plan.project_io import create_project_folder
from crane_plan.report import generate_report


def ready(directory):
    project, scenario = build_fixture(directory)
    for crane in scenario.placements:
        crane.tie_in_levels_m = []
        crane.tie_in_stage_sections = []
        crane.tie_nearest_floors = []
        crane.total_additional_sections = 0
    for index, load in enumerate(project.loads):
        load.rigging_type = "Канатный"
        load.rigging_branch_count = 4
        load.sling_identification = f"4СК-{index + 1}"
        load.rigging_capacity_kg = 2500
        load.rigging_evidence = "Испытательный паспорт оснастки №123"
        load.rigging_verified = True
    project.pprk_release.issue_date = "2026-11-04"
    project.pprk_release.approvals = complete_approvals()
    project.pprk_release.approvals[0].position = "Проверил"
    project.pprk_release.approvals[0].full_name = "Контролер К.К."
    project.pprk_release.approvals[1].position = "Утвердил"
    project.pprk_release.approvals[1].full_name = "Утверждающий У.У."
    ids = {d.document_id for d in project.pprk_release.external_documents}
    project.pprk_release.external_documents.extend(d for d in verified_required_documents() if d.document_id not in ids)
    return project, scenario


class Round2Tests(unittest.TestCase):
    def test_joint_gate_uses_bound_scenario_and_does_not_substitute_other_variants(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, selected = ready(directory / "fixture")
            bundle = prepare_release(project, selected, verify(project, selected)).bundle
            other = deepcopy(selected)
            other.status = "REJECTED"
            other.joint_plan.jib_structural_height_m = 12
            output = directory / "selected.pdf"
            generate_report(output, project, [other, selected], bundle=bundle)
            sections = [p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("ВЫСОТНАЯ ПРИВЯЗКА")]
            self.assertEqual(len(sections), 1)
            self.assertIn("H=32.4", sections[0])
            self.assertIn("H=42.4", sections[0])

    def test_bracketed_or_variant_rigging_placeholders_are_not_evidence(self):
        with TemporaryDirectory() as tmp:
            project, scenario = ready(Path(tmp) / "fixture")
            checked = verify(project, scenario)
            for field in ("rigging_type", "sling_identification", "rigging_evidence"):
                for value in ("⟦НЕ ЗАПОЛНЕНО: паспорт⟧", "Не заполнена", "Н/Д", "___", "\u200b\t", "None"):
                    with self.subTest(field=field, value=value):
                        changed = deepcopy(project)
                        setattr(changed.loads[0], field, value)
                        self.assertFalse(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed)

    def assert_gui_atomic_rejection(self, project, scenario, verification, directory, reason=None):
        folder = create_project_folder(directory / "gui-projects", project)
        (folder / "reports/ППРк_предварительный.pdf").write_bytes(b"previous")
        (folder / "reports/ППРк.pdf").write_bytes(b"previous-production")
        for name in ("на_проверку", "на_согласование", "утверждённый", "в_производство"):
            (folder / f"reports/ППРк_{name}.pdf").write_bytes(b"previous-status-output")
        (folder / "reports/calculation_protocol_v21.json").write_bytes(b"previous-protocol")
        (folder / "revisions/previous.json").write_bytes(b"previous-revision")
        (folder / "project.json").write_bytes(b"previous-project")
        before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(AssertionError, reason or "GUI save blocked"):
            save_via_gui(project, scenario, verification, directory)
        self.assertEqual(before, {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()})

    def test_joint_clearance_invalid_structure_or_axis_order_is_a_fatal_gui_gate(self):
        with TemporaryDirectory() as tmp:
            base, scenario = ready(Path(tmp) / "fixture")
            mutations = (("jib_structural_height_m", 12), ("jib_structural_height_m", 9.0005), ("jib_structural_height_m", -1),
                         ("jib_structural_height_m", float("nan")), ("higher_crane_index", 1))
            for index, (field, value) in enumerate(mutations):
                with self.subTest(field=field, value=value):
                    project, changed = deepcopy((base, scenario))
                    setattr(changed.joint_plan, field, value)
                    checked = verify(project, changed)
                    with self.assertRaises(ValueError):
                        prepare_release(project, changed, checked)
                    self.assert_gui_atomic_rejection(project, changed, checked, Path(tmp) / str(index))

    def test_route_protection_requires_screen_sheet_and_project_at_public_boundary(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, scenario = ready(directory / "fixture")
            checked = verify(project, scenario)
            report = checked.protocol.verification
            protected = replace(report.checks[0], code="DANGER_ROUTE_PROTECTED", limit="PROTECTIVE_SCREEN", measured_value=13.)
            report = replace(report, checks=(*report.checks, protected))
            protocol = replace(checked.protocol, verification=report)
            checked = replace(checked, protocol=protocol, engine_result=replace(checked.engine_result, protocol=protocol, verification=report))
            release = prepare_release(project, scenario, checked)
            self.assertEqual(release.bundle.sheet("appendix.PROTECTIVE_SCREENS").asset_ids, ("protective_screens",))
            path = save_via_gui(project, scenario, checked, directory / "draft")
            text = "\n".join(p.extract_text() for p in PdfReader(path).pages)
            self.assertIn("protective_screen_project", text)
            self.assertIn("Защитный экран на консоли", text)
            project.pprk_release.status = ReleaseStatus.PRODUCTION
            self.assert_gui_atomic_rejection(project, scenario, checked, directory / "final", "screen|экран|GUI save blocked")

    def test_vector_underlays_are_scanned_before_bundle_or_legacy_rasterization(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, scenario = ready(directory / "fixture")
            source = directory / "neutral.pdf"
            canvas = Canvas(str(source))
            canvas.drawString(60, 500, "27.06-23")
            canvas.showPage(); canvas.save()
            checked = verify(project, scenario)
            clean_bundle = prepare_release(project, scenario, checked).bundle
            for kind in ("plan", "section"):
                changed = deepcopy(project)
                setattr(changed, f"source_{kind}_pdf", str(source))
                setattr(changed, f"{kind}_m_per_pixel", .1)
                verified = verify(changed, scenario)
                with self.subTest(kind=kind):
                    with self.assertRaisesRegex(ValueError, "[Зз]апрещ|reference"):
                        prepare_release(changed, scenario, verified)
                    self.assert_gui_atomic_rejection(changed, scenario, verified, directory / kind)
                    for bundle in (None, clean_bundle):
                        output = directory / f"{kind}-{bundle is None}.pdf"
                        output.write_bytes(b"previous")
                        with self.assertRaisesRegex(ValueError, "[Зз]апрещ|reference"):
                            generate_report(output, changed, [scenario], bundle=bundle)
                        self.assertEqual(output.read_bytes(), b"previous")

    def test_entity_encoded_external_page_xmp_is_rejected_atomically(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, scenario = ready(directory / "fixture")
            source = directory / "neutral.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(595, 842)
            metadata = DecodedStreamObject()
            metadata.set_data(b'<x:xmpmeta xmlns:x="adobe:ns:meta/">27.06&#45;23</x:xmpmeta>')
            metadata.update({NameObject("/Type"): NameObject("/Metadata"), NameObject("/Subtype"): NameObject("/XML")})
            page[NameObject("/Metadata")] = writer._add_object(metadata)
            with source.open("wb") as stream:
                writer.write(stream)
            with self.assertRaisesRegex(ValueError, "[Зз]апрещ|reference"):
                validate_release_pdf(source)
            project.pprk_release.external_documents.append(ExternalDocument("extra", "Внешний документ", present=True,
                verification_status="VERIFIED", attachment_path=str(source), verified_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
            self.assert_gui_atomic_rejection(project, scenario, verify(project, scenario), directory / "save")

    def test_real_nine_column_registry_keeps_locator_software_status_and_full_note(self):
        records = {r.rule_id: r for r in load_release_regulations()}
        self.assertEqual(records["REG-007"].locator, "разделы 2 и 5; формула высоты подъема; таблица 3")
        self.assertEqual(records["REG-007"].software_status, "DO_NOT_TREAT_AS_BINDING")
        self.assertTrue(records["REG-007"].verification_note.startswith("Числа основаны"))
        self.assertEqual(records["REG-008"].locator, "раздел 6")
        self.assertEqual(records["REG-008"].software_status, "DOCUMENT_STRUCTURE")
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, scenario = ready(directory / "fixture")
            path = save_via_gui(project, scenario, verify(project, scenario), directory / "save")
            text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(path).pages)
            self.assertIn("DO_NOT_TREAT_AS_BINDING", text)
            self.assertIn("Не использовать вместо грузовых характеристик", text)
            self.assertIn("DOCUMENT_STRUCTURE", text)

    def test_exact_issue_date_is_printed_and_mismatching_title_year_cannot_mislead(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, scenario = ready(directory / "fixture")
            project.pprk_release.issue_date = "2026-09-25"
            project.pprk_release.issue_year = 2028
            checked = verify(project, scenario)
            path = save_via_gui(project, scenario, checked, directory / "save")
            title = PdfReader(path).pages[0].extract_text()
            self.assertIn("2026-09-25", title)
            self.assertNotIn("Москва, 2028", title)
            project.pprk_release.status = ReleaseStatus.PRODUCTION
            release = prepare_release(project, scenario, checked)
            self.assertIn("PPRK_ISSUE_YEAR_MISMATCH", {i.code for i in release.issues if i.blocking})
            self.assert_gui_atomic_rejection(project, scenario, checked, directory / "final")

    def test_checker_and_approver_are_preserved_from_explicit_approval_roles(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, scenario = ready(directory / "fixture")
            project.pprk_release.manager_name = "Менеджер М.М."
            path = save_via_gui(project, scenario, verify(project, scenario), directory / "save")
            text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(path).pages)
            self.assertIn("Пров. Контролер К.К.", text)
            self.assertIn("Утв. Утверждающий У.У.", text)
            self.assertNotIn("Пров. Менеджер", text)
            self.assertNotIn("Утв. Менеджер", text)
            project.pprk_release.approvals[0].position = "Инженер"
            project.pprk_release.status = ReleaseStatus.PRODUCTION
            checked = verify(project, scenario)
            release = prepare_release(project, scenario, checked)
            self.assertIn("PPRK_APPROVAL_ROLE_REQUIRED", {i.code for i in release.issues if i.blocking})
            self.assertEqual(release.bundle.render_requisites.checked_by, "")
            self.assert_gui_atomic_rejection(project, scenario, checked, directory / "final")

    def test_rigging_sentinels_never_confirm_a_card_or_unlock_production(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, scenario = ready(directory / "fixture")
            project.loads[0].rigging_type = "\u200b НЕ ЗАПОЛНЕНО \u00a0"
            checked = verify(project, scenario)
            context = build_pprk_context(project, scenario, checked)
            self.assertFalse(context.active_loads[0].confirmed)
            self.assertIn("PPRK_RIGGING_EVIDENCE_REQUIRED", {i.code for i in context.completeness_issues})
            path = save_via_gui(project, scenario, checked, directory / "draft")
            cards = [p.extract_text() for p in PdfReader(path).pages if p.extract_text().startswith("Строповка:")]
            self.assertIn("НЕ ПОДТВЕРЖДЕНО", cards[0])
            self.assertNotIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", cards[0])
            project.pprk_release.status = ReleaseStatus.PRODUCTION
            self.assert_gui_atomic_rejection(project, scenario, checked, directory / "final")

    def test_external_contents_measures_actual_document_id_before_saveability(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, scenario = ready(directory / "fixture")
            source = external_fixture(directory / "external.pdf", ("EXTERNAL",))
            project.pprk_release.external_documents.append(ExternalDocument("W" * 400, "Короткое название", present=True,
                verification_status="VERIFIED", attachment_path=str(source), verified_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
            checked = verify(project, scenario)
            with self.assertRaisesRegex(ValueError, "Текст не помещается в ячейке"):
                release = prepare_release(project, scenario, checked)
                require_saveable_release(release, checked)
            self.assert_gui_atomic_rejection(project, scenario, checked, directory / "save")


if __name__ == "__main__":
    unittest.main()

