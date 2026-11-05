"""Whole-release safety regressions: physical artifacts, evidence and status gates."""
from copy import deepcopy
from dataclasses import replace
import io
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import json

import pdfplumber
from pypdf import PdfReader
from reportlab.lib.pagesizes import A2, landscape
from reportlab.pdfgen.canvas import Canvas

from test_pprk_context import _fixture
from test_pprk_composer import compose, complete_release, make_context
from test_full_pprk_end_to_end import build_fixture, verify
from crane_plan.pprk_assets import load_asset_manifest
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_composer import compose_pprk
from crane_plan.pprk_models import ReleaseStatus
from crane_plan.pprk_templates import load_template_catalog
from crane_plan.pprk_release_workflow import prepare_release, publish_release
from crane_plan.report import generate_report, _section_page, _joint_work_schedule_page
from crane_plan.models import Load


class FinalHardeningTests(unittest.TestCase):
    def test_legacy_report_cannot_publish_forbidden_reference_code(self):
        from test_io_pdf_report import sample_project
        from crane_plan.models import Placement, ScenarioResult
        project = sample_project()
        project.project_code = "27.06-23"
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "legacy.pdf"
            output.write_bytes(b"previous")
            with self.assertRaisesRegex(ValueError, "[Зз]апрещ|reference"):
                scenario = ScenarioResult("PASS", [Placement("c1", "130 EC-B 6", 20, 0, [0], 30, 35,
                    jib_length_m=40, jib_level_m=38)], [], [])
                generate_report(output, project, [scenario])
            self.assertEqual(output.read_bytes(), b"previous")

    def test_disappeared_mandatory_pdf_cannot_bypass_required_flag_at_render(self):
        from test_app_pprk_release import ready_project
        from crane_plan.pprk_regulations import load_release_regulations
        from crane_plan.pprk_merge import verify_external_revision
        project, scenario, verification = ready_project()
        registry = tuple(replace(r, verification_status="VERIFIED_SOURCE") for r in load_release_regulations())
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            documents = []
            for document in project.pprk_release.external_documents:
                source = directory / f"{document.document_id}.pdf"
                source.write_bytes(Path(document.attachment_path).read_bytes())
                documents.append(verify_external_revision(replace(document, required=False, attachment_path=str(source))))
            project.pprk_release.external_documents = documents
            with patch("crane_plan.pprk_composer.load_release_regulations", return_value=registry):
                release = prepare_release(project, scenario, verification)
            release.require_requested_status()
            confirmed = directory / "confirmed.pdf"
            generate_report(confirmed, release.project, [scenario], bundle=release.bundle)
            cards = [p.extract_text() for p in PdfReader(confirmed).pages if p.extract_text().startswith("Строповка:")]
            self.assertEqual(len(cards), 1)
            self.assertIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", cards[0])
            self.assertIn("4СК-TEST", cards[0])
            self.assertNotIn("НЕ ЗАПОЛНЕНО", cards[0])
            Path(documents[0].attachment_path).unlink()
            output = directory / "production.pdf"
            output.write_bytes(b"previous")
            with self.assertRaisesRegex(ValueError, "ОЖИДАЕТ ВКЛЮЧЕНИЯ"):
                generate_report(output, release.project, [scenario], bundle=release.bundle)
            self.assertEqual(output.read_bytes(), b"previous")

    def test_unsaveable_internal_text_layout_is_rejected_during_preparation(self):
        project, scenario, verification = _fixture()
        project.pprk_release = complete_release(title="Очень длинный заголовок проекта " * 500)
        with self.assertRaisesRegex(ValueError, "Текст не помещается в ячейке"):
            prepare_release(project, scenario, verification)

    def test_oversized_rigging_card_is_rejected_during_preparation(self):
        project, scenario, verification = _fixture()
        project.loads[0].rigging_evidence = "Паспорт оснастки №123, подтверждение конкретного груза. " * 600
        with self.assertRaisesRegex(ValueError, "Таблица приложения .* не помещается на листе"):
            prepare_release(project, scenario, verification)

    def test_physical_load_card_contents_title_is_checked_during_preparation(self):
        project, scenario, verification = _fixture()
        project.loads[0].name = "Очень длинное название груза " * 30
        with self.assertRaisesRegex(ValueError, "Текст не помещается в ячейке: Строповка:"):
            prepare_release(project, scenario, verification)

    def test_status_matrix_rejects_unverified_expired_or_missing_required_evidence(self):
        from test_pprk_composer import complete_approvals
        from crane_plan.pprk_regulations import load_release_regulations
        verified = tuple(replace(r, verification_status="VERIFIED_SOURCE") for r in load_release_regulations())
        for status in ReleaseStatus:
            for defect in ("none", "document", "date", "expired", "unverified"):
                with self.subTest(status=status, defect=defect):
                    config = complete_release(status=status, approvals=complete_approvals())
                    registry = verified
                    if defect == "document":
                        config.external_documents = []
                    elif defect == "date":
                        config.issue_date = ""
                    elif defect == "expired":
                        config.issue_date = "2027-01-01"
                    elif defect == "unverified":
                        registry = tuple(replace(r, verification_status="UNVERIFIED_STATUS") if r.rule_id == "REG-013" else r for r in verified)
                    with patch("crane_plan.pprk_composer.load_release_regulations", return_value=registry):
                        bundle = compose(config=config)
                    expected = ReleaseStatus.REVIEW if defect != "none" and status in (
                        ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION) else status
                    self.assertEqual(bundle.effective_status, expected)

    def test_project_roundtrip_preserves_rigging_and_legacy_loads_stay_unconfirmed(self):
        from crane_plan.project_io import save_project, load_project
        project, scenario, verification = _fixture()
        project.pprk_release.issue_date = "2026-11-04"
        with TemporaryDirectory() as tmp:
            path = save_project(tmp, project)
            loaded = load_project(path)
            self.assertEqual(loaded.loads[0], project.loads[0])
            self.assertEqual(loaded.pprk_release.issue_date, "2026-11-04")
            payload = json.loads(path.read_text(encoding="utf-8"))
            for key in tuple(payload["loads"][0]):
                if key.startswith("rigging_") and key not in ("rigging_kg", "rigging_height_m") or key == "sling_identification":
                    payload["loads"][0].pop(key)
            payload["pprk_release"].pop("issue_date")
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            before = path.read_bytes()
            legacy = load_project(path)
            self.assertFalse(legacy.loads[0].rigging_verified)
            self.assertEqual(legacy.pprk_release.issue_date, "")
            self.assertFalse(build_pprk_context(legacy, scenario, verification).active_loads[0].confirmed)
            self.assertEqual(before, path.read_bytes())

    def test_load_editor_collection_preserves_explicit_rigging_evidence(self):
        from crane_plan.app import CranePlanApp
        values = ("Щит опалубки", 1800, 120, 3, 1.2, 2.8, 24, "да",
                  "Канатный", "4", "4СК-123", "2500", "Паспорт 123, испытание 04.11.2026", "да")
        ui = SimpleNamespace(load_tree=SimpleNamespace(get_children=lambda: ["row"], item=lambda *args: values))
        load, = CranePlanApp._collect_loads(ui)
        self.assertEqual(getattr(load, "sling_identification", ""), "4СК-123")
        project, scenario, verification = _fixture()
        project.loads = [load]
        context = build_pprk_context(project, scenario, verification)
        self.assertTrue(context.active_loads[0].confirmed)
        self.assertIn(("Ветвей", "4"), context.active_loads[0].sling_fields)

    def test_section_axes_and_clearance_equation_use_actual_verified_jib_levels(self):
        with TemporaryDirectory() as tmp:
            project, scenario = build_fixture(Path(tmp))
            packet = io.BytesIO()
            canvas = Canvas(packet, pagesize=landscape(A2))
            _section_page(canvas, project, scenario, 1)
            _joint_work_schedule_page(canvas, project, scenario, 1, "ГЧ-09")
            canvas.save()
            reader = PdfReader(packet)
            section, schedule = [" ".join(p.extract_text().split()) for p in reader.pages]
            self.assertIn("H=32.4", section)
            self.assertIn("H=42.4", section)
            for text in (section, schedule):
                self.assertIn("10.0 м =", text)
                self.assertIn("8.0 м", text)
                self.assertNotIn("2.0 м + чистый зазор 1.0", text)
            # Distinct physical arrow levels must survive extraction, rather than
            # a corrected label placed on the old equal-height geometry.
            with pdfplumber.open(packet) as pdf:
                from reportlab.lib.units import mm
                from crane_plan.pprk_sheets import section_transform_contract
                transform = section_transform_contract(project, scenario, landscape(A2))
                masts = [rect for rect in pdf.pages[0].rects
                         if abs(rect["width"] - 7 * mm) < .01 and rect["height"] > 100 * mm]
                self.assertEqual(len(masts), 2)
                self.assertAlmostEqual(masts[0]["y1"], transform.height_point(32.4)[1], places=3)
                self.assertAlmostEqual(masts[1]["y1"], transform.height_point(42.4)[1], places=3)
                levels = {round(line["y0"], 2) for line in pdf.pages[0].lines
                          if line.get("stroking_color") in ((0, .298039, .6), (.752941, .313725, 0))
                          and abs(line["y0"] - line["y1"]) < .01 and line["width"] > 20}
                self.assertGreaterEqual(len(levels), 2)

    def test_mandatory_documents_block_advanced_even_when_unregistered(self):
        for status in ReleaseStatus:
            config = complete_release(status=status)
            config.external_documents = []
            bundle = compose(config=config)
            missing = {i.field_id for i in bundle.completeness_issues
                       if i.code == "PPRK_EXTERNAL_DOCUMENT_REQUIRED"}
            self.assertTrue({"external_documents/crane_passport", "external_documents/foundation_project",
                             "external_documents/erection_project"} <= missing)
            if status not in (ReleaseStatus.PRELIMINARY, ReleaseStatus.REVIEW):
                self.assertNotEqual(bundle.effective_status, status)

    def test_screen_mitigation_is_transferred_and_requires_sheet_and_project(self):
        project, scenario, verification = _fixture()
        protocol = verification.protocol
        protected = replace(protocol.verification.checks[0], code="DANGER_ZONE_PROTECTED",
                            limit="PROTECTIVE_SCREEN", measured_value=9.4)
        protocol.verification = replace(protocol.verification, checks=(*protocol.verification.checks, protected))
        verification.engine_result.verification = protocol.verification
        context = build_pprk_context(project, scenario, verification)
        self.assertIn("PROTECTIVE_SCREEN", context.values.get("verified_mitigation_types", ()))
        bundle = compose_pprk(context, load_template_catalog(), load_asset_manifest(), complete_release())
        self.assertEqual(bundle.sheet("appendix.PROTECTIVE_SCREENS").asset_ids, ("protective_screens",))
        self.assertIn("external_documents/protective_screen_project",
                      {i.field_id for i in bundle.completeness_issues})
        for status in (ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION):
            final = compose_pprk(context, load_template_catalog(), load_asset_manifest(), complete_release(status=status))
            self.assertNotEqual(final.effective_status, status)
            missing_clip = compose_pprk(context, load_template_catalog(),
                tuple(a for a in load_asset_manifest() if a.asset_id != "protective_screens"), complete_release(status=status))
            self.assertIn("assets/protective_screens", {i.field_id for i in missing_clip.completeness_issues if i.blocking})
        with TemporaryDirectory() as tmp:
            project.pprk_release = complete_release()
            release = prepare_release(project, scenario, verification)
            path = Path(tmp) / "screen.pdf"
            generate_report(path, project, [scenario], bundle=release.bundle)
            texts = [p.extract_text() for p in PdfReader(path).pages]
            self.assertTrue(any("protective_screen_project" in t and "ОЖИДАЕТ" in t for t in texts))
            self.assertTrue(any("Защитный экран на консоли" in t and len(p.images) == 1 for t, p in zip(texts, PdfReader(path).pages)))

    def test_regulation_metadata_and_expiry_are_preserved_in_physical_note(self):
        project, scenario, verification = _fixture()
        project.pprk_release = complete_release()
        scenario.placements[0].tie_in_levels_m = []
        # Future date is explicit evidence, not the machine clock or just year.
        project.pprk_release.issue_date = "2027-01-01"
        release = prepare_release(project, scenario, verification)
        self.assertTrue(getattr(release.bundle, "regulations", ()), "registry metadata was discarded")
        records = {r.rule_id: r for r in release.bundle.regulations}
        self.assertEqual(records["REG-010"].valid_until, "2026-12-31")
        self.assertEqual(records["REG-013"].software_status, "UNVERIFIED_STATUS")
        codes = {i.code for i in release.issues}
        self.assertIn("PPRK_REGULATION_EXPIRED", codes)
        self.assertIn("PPRK_REGULATION_UNVERIFIED", codes)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.pdf"
            generate_report(path, release.project, [scenario], bundle=release.bundle)
            text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(path).pages)
            self.assertIn("REG-010", text)
            self.assertIn("1479", text)
            self.assertIn("REG-013", text)
            self.assertIn("UNVERIFIED_STATUS", text)

    def test_forbidden_inputs_and_physical_pdf_metadata_preserve_previous_output(self):
        project, scenario, verification = _fixture()
        project.pprk_release.project_code = "27.06-23"
        with self.assertRaisesRegex(ValueError, "[Зз]апрещ|reference"):
            prepare_release(project, scenario, verification)
        project.pprk_release.project_code = "SAFE"
        release = prepare_release(project, scenario, verification)
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "result.pdf"
            output.write_bytes(b"previous")
            def contaminated(path, *args, **kwargs):
                canvas = Canvas(str(path))
                canvas.setAuthor("27.06-23")
                canvas.drawString(50, 500, "safe")
                canvas.showPage(); canvas.save()
            with self.assertRaisesRegex(ValueError, "[Зз]апрещ|reference"):
                publish_release(output, release, "same", lambda: "same", render=contaminated)
            self.assertEqual(output.read_bytes(), b"previous")

    def test_forbidden_xmp_metadata_is_scanned_before_replacement(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject
        project, scenario, verification = _fixture()
        release = prepare_release(project, scenario, verification)
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "result.pdf"
            output.write_bytes(b"previous")
            def contaminated(path, *args, **kwargs):
                writer = PdfWriter()
                writer.add_blank_page(595, 842)
                metadata = DecodedStreamObject()
                metadata.set_data(b'<x:xmpmeta xmlns:x="adobe:ns:meta/">27.06-23</x:xmpmeta>')
                metadata.update({NameObject("/Type"): NameObject("/Metadata"), NameObject("/Subtype"): NameObject("/XML")})
                writer.root_object[NameObject("/Metadata")] = writer._add_object(metadata)
                with open(path, "wb") as stream:
                    writer.write(stream)
            with self.assertRaisesRegex(ValueError, "[Зз]апрещ|reference"):
                publish_release(output, release, "same", lambda: "same", render=contaminated)
            self.assertEqual(output.read_bytes(), b"previous")

    def test_confirmed_mass_does_not_confirm_missing_rigging(self):
        project, scenario, verification = _fixture()
        project.loads[0] = replace(project.loads[0], rigging_type="", rigging_branch_count=None,
                                  sling_identification="", rigging_evidence="", rigging_verified=False)
        context = build_pprk_context(project, scenario, verification)
        self.assertFalse(context.active_loads[0].confirmed)
        self.assertIn("PPRK_RIGGING_EVIDENCE_REQUIRED", {i.code for i in context.completeness_issues})

    def test_all_calculated_pages_bind_selected_number_and_protocol(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            project, scenario = build_fixture(directory)
            verification = replace(verify(project, scenario), scenario_index=2)
            release = prepare_release(project, scenario, verification)
            path = directory / "selected.pdf"
            generate_report(path, release.project, [scenario], bundle=release.bundle)
            texts = [" ".join(p.extract_text().split()) for p in PdfReader(path).pages]
            calculated = [t for t in texts if "ГЧ-" in t and not t.startswith("ППРк")]
            self.assertGreaterEqual(len(calculated), 9)
            for text in calculated:
                self.assertIn("Вариант 3", text)
                self.assertIn(verification.protocol.run_id, text)
                self.assertIn(verification.protocol.result_sha256[:12], text)
                self.assertNotIn("ВАРИАНТ 1", text)

    def test_release_requisites_replace_legacy_stamps_without_mutating_input(self):
        project, scenario, verification = _fixture()
        project.organization, project.project_code, project.author = "OLD-ORG", "OLD-CODE", "OLD-AUTHOR"
        project.pprk_release = complete_release(developer_organization="NEW-ORG", project_code="NEW-CODE",
                                                developer_name="NEW-AUTHOR")
        release = prepare_release(project, scenario, verification)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "requisites.pdf"
            generate_report(path, release.project, [scenario], bundle=release.bundle)
            reader = PdfReader(path)
            text = " ".join(p.extract_text() for p in reader.pages) + str(reader.metadata)
            for old in ("OLD-ORG", "OLD-CODE", "OLD-AUTHOR"):
                self.assertNotIn(old, text)
            for new in ("NEW-ORG", "NEW-CODE", "NEW-AUTHOR"):
                self.assertIn(new, text)
        self.assertEqual(project.project_code, "OLD-CODE")

    def test_internal_only_38_loads_always_finalize_multiple_contents_leaves(self):
        project, scenario, verification = _fixture()
        project.pprk_release = complete_release()
        project.pprk_release.external_documents = []
        # Freeze real load evidence through the same context boundary; pending
        # capacity/rigging is honest in the preliminary physical cards.
        project.loads = [replace(project.loads[0], name=f"Щит опалубки {i}") for i in range(38)]
        release = prepare_release(project, scenario, verification)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.pdf"
            from crane_plan.pprk_release_workflow import require_saveable_release
            require_saveable_release(release, verification)
            # Exercise the empty-registry adapter even with a caller-supplied
            # bundle that has no implicit pending external rows.
            bundle = replace(release.bundle, completeness_issues=tuple(
                i for i in release.bundle.completeness_issues if not i.field_id.startswith("external_documents/")))
            generate_report(path, release.project, [scenario], bundle=bundle)
            texts = [p.extract_text() for p in PdfReader(path).pages]
            leaves = [t for t in texts if "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ" in t]
            self.assertGreaterEqual(len(leaves), 3)
            pages = [int(n) for t in leaves for n in re.findall(r"стр\. (\d+)", t)]
            self.assertEqual(sorted(pages), list(range(1, len(texts) + 1)))


if __name__ == "__main__":
    unittest.main()

