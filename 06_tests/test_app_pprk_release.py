"""Headless tests of the same release boundary used by the report tab."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import crane_plan.pprk_release_workflow as app
from crane_plan.app import CranePlanApp
from crane_plan.pprk_models import PPRKReleaseConfig, ApprovalSlot, ExternalDocument, ReleaseStatus, TemplateOverride
from test_pprk_context import _fixture


class ReleaseEditorTests(unittest.TestCase):
    def test_approval_operations_keep_eight_without_fabricating_signatures(self):
        signed = ApprovalSlot("Организация", "Инженер", "Имя", "Внесено вручную", "01.11")
        rows = app.approval_rows([signed], "add")
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0], signed)
        self.assertEqual([row.signature for row in rows[1:]], [""] * 7)
        self.assertEqual(app.approval_rows(rows, "remove", 0), [ApprovalSlot() for _ in range(8)])
        self.assertEqual(app.approval_rows(rows * 2, "reset"), [ApprovalSlot() for _ in range(8)])

    def test_release_fields_are_typed_and_separate_from_engine_identity(self):
        project, _, _ = _fixture()
        before = CranePlanApp._project_snapshot(project)
        edited = app.edit_release_fields(project.pprk_release, {
            "title": "Корпус 3", "issue_year": "2027", "max_wind_speed_m_s": "8,5",
            "receiving_platform_ids": "П1, П2", "bucket_volume_m3": "",
        })
        project.pprk_release = edited
        self.assertEqual((edited.title, edited.issue_year, edited.max_wind_speed_m_s,
                          edited.receiving_platform_ids, edited.bucket_volume_m3),
                         ("Корпус 3", 2027, 8.5, ["П1", "П2"], None))
        self.assertEqual(before, CranePlanApp._project_snapshot(project))
        with self.assertRaisesRegex(ValueError, "Год"):
            app.edit_release_fields(edited, {"issue_year": "текст"})

    def test_section_reasons_status_and_missing_documents_reach_editor(self):
        project, scenario, verification = _fixture()
        config = project.pprk_release
        config.excluded_section_ids = ["orphan", "general"]
        config.status = ReleaseStatus.PRODUCTION
        config.external_documents = [ExternalDocument("passport", "Паспорт", required=True)]
        release = app.prepare_release(project, scenario, verification)
        self.assertNotEqual(release.bundle.effective_status, ReleaseStatus.PRODUCTION)
        self.assertTrue(any(i.field_id == "sections/orphan" for i in release.issues))
        self.assertTrue(any("passport" in i.field_id for i in release.issues))
        self.assertTrue(any(not included for _, _, included, _ in release.sections))
        self.assertTrue(all(any("а" <= c.lower() <= "я" for c in reason)
                            for _, _, _, reason in release.sections))
        self.assertTrue(release.bundle.preliminary_available)
        with self.assertRaises(ValueError):
            release.require_requested_status()

    def test_unverified_or_corrupt_source_is_pending_in_preliminary_copy(self):
        project, scenario, verification = _fixture()
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "passport.pdf"
            source.write_bytes(b"corrupt")
            for state, code in [("UNVERIFIED", "PPRK_EXTERNAL_UNVERIFIED"),
                                ("VERIFIED", "PPRK_EXTERNAL_NOT_PDF")]:
                doc = ExternalDocument("pass", "Паспорт", True, True, verification_status=state,
                                       attachment_path=str(source))
                project.pprk_release.external_documents = [doc]
                release = app.prepare_release(project, scenario, verification)
                self.assertIn(code, [i.code for i in release.issues])
                release.require_requested_status()
                self.assertFalse(release.project.pprk_release.external_documents[0].present)
                self.assertTrue(doc.present)
                self.assertEqual(doc.verification_status, state)

    def test_fingerprint_covers_every_input_family_and_bytes_at_same_path(self):
        project, scenario, verification = _fixture()
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.pdf"
            source.write_bytes(b"A")
            project.pprk_release.external_documents = [ExternalDocument("x", "PDF", attachment_path=str(source))]
            def fingerprint(index=1):
                return app.release_fingerprint(project, scenario, verification, index)
            original = fingerprint()
            self.assertEqual(original, fingerprint())
            self.assertNotEqual(original, fingerprint(0))
            changes = [
                (project, "city", "Омск"), (scenario, "warnings", ["Новое"]),
                (verification.protocol, "run_id", "RUN-2"),
                (project.pprk_release, "title", "Корпус"),
                (project.pprk_release, "approvals", [ApprovalSlot(signature="Подпись")]),
                (project.pprk_release, "included_section_ids", ["other"]),
                (project.pprk_release, "overrides", [TemplateOverride("p", "1", "Замена")]),
                (project.pprk_release, "status", ReleaseStatus.REVIEW),
                (project.pprk_release.external_documents[0], "number", "35"),
            ]
            for target, name, value in changes:
                with self.subTest(name=name), patch.object(target, name, value):
                    self.assertNotEqual(original, fingerprint())
            source.write_bytes(b"B")
            self.assertNotEqual(original, fingerprint())
            with patch.object(app, "release_resource_paths", return_value=[source]):
                before = fingerprint()
                source.write_bytes(b"C")
                self.assertNotEqual(before, fingerprint())

    def test_legacy_engineering_gates_block_advanced_status_in_completeness(self):
        project, scenario, verification = _fixture()
        project.pprk_release.status = ReleaseStatus.COORDINATION
        project.city = ""
        project.site.storage_zones = []
        project.site.unloading_zone = []
        project.site.restricted_zones = []
        project.restricted_zones_confirmed = False
        scenario.accounted_lifts = 0
        fields = {i.field_id for i in app.prepare_release(project, scenario, verification).issues if i.blocking}
        self.assertTrue({"city", "site.storage_zones", "site.unloading_zone",
                         "site.restricted_zones", "scenario.accounted_lifts"} <= fields)

    def test_replaced_plan_bytes_make_engine_result_stale(self):
        project, _, _ = _fixture()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.pdf"
            path.write_bytes(b"original")
            project.source_plan_pdf = str(path)
            snapshot = CranePlanApp._project_snapshot(project)
            path.write_bytes(b"revised")
            self.assertNotEqual(snapshot, CranePlanApp._project_snapshot(project))

    def test_sheet_too_large_for_a1_is_visible_before_render(self):
        from dataclasses import replace
        project, scenario, verification = _fixture()
        report = verification.protocol.verification
        check = replace(report.checks[0], code="DANGER_ZONE_INSIDE_SITE", measured_value=9.)
        verification.engine_result.verification = replace(report, checks=(*report.checks, check))
        project.site.boundary = [(-1000, -1000), (1000, -1000), (1000, 1000), (-1000, 1000)]
        release = app.prepare_release(project, scenario, verification)
        sheet = release.bundle.sheet("drawing.SITE_PLAN")
        self.assertIn("A1", dict(sheet.fields).get("pending_reason", ""))
        self.assertTrue(any(i.field_id == sheet.sheet_id for i in release.issues))
        release.require_requested_status()

    def test_preliminary_renders_physical_pending_sheets_for_missing_engine_evidence(self):
        from pypdf import PdfReader
        project, scenario, verification = _fixture()
        scenario.placements[0].sozr_plan = None
        # This legacy result has no nearest-floor row for its claimed tie level.
        view = app.prepare_release(project, scenario, verification)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.pdf"
            app.publish_release(path, view, "same", lambda: "same")
            pages = [p.extract_text() or "" for p in PdfReader(path).pages]
        self.assertIn("предварительная автоматизированная редакция", pages[0].lower())
        self.assertTrue(any("ОЖИДАЕТ РАСЧЁТА" in text and "опасной зоны" in text for text in pages))
        self.assertTrue(any("ОЖИДАЕТ РАСЧЁТА" in text and "СОЗР" in text for text in pages))
        self.assertTrue(any("ОЖИДАЕТ РАСЧЁТА" in text and "пристежек" in text for text in pages))
        project.pprk_release.status = ReleaseStatus.PRODUCTION
        final = app.prepare_release(project, scenario, verification)
        self.assertTrue(any(i.blocking and i.field_id == "drawing.SITE_PLAN" for i in final.issues))
        with self.assertRaises(ValueError):
            final.require_requested_status()

    def test_staged_publish_preserves_previous_pdf_on_mid_render_edit(self):
        project, scenario, verification = _fixture()
        release = app.prepare_release(project, scenario, verification)
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.pdf"
            output.write_bytes(b"previous")
            def fingerprint():
                return app.release_fingerprint(project, scenario, verification, 0)
            def edit_during_render(path, *_args, **_kwargs):
                path.write_bytes(b"staged")
                project.pprk_release.title = "Новое"
            with patch.object(app, "generate_report", side_effect=edit_during_render):
                with self.assertRaisesRegex(ValueError, "измен"):
                    app.publish_release(output, release, fingerprint(), fingerprint)
            self.assertEqual(output.read_bytes(), b"previous")
            self.assertEqual(list(Path(tmp).iterdir()), [output])


def ready_project():
    from test_pprk_composer import complete_release, complete_approvals
    project, scenario, verification = _fixture()
    project.pprk_release = complete_release(status=ReleaseStatus.PRODUCTION, approvals=complete_approvals())
    crane = scenario.placements[0]
    crane.tie_in_levels_m = []
    crane.sozr_plan = replace(crane.sozr_plan, admissible_contours=(((0, 0), (10, 0), (0, 10)),))
    report = verification.protocol.verification
    danger = replace(report.checks[0], code="DANGER_ZONE_INSIDE_SITE", measured_value=9.)
    verification.protocol.verification = verification.engine_result.verification = replace(
        report, checks=(*report.checks, danger))
    return project, scenario, verification


class ReleaseReviewRegressions(unittest.TestCase):
    def setUp(self):
        from crane_plan.pprk_regulations import load_release_regulations
        registry = tuple(replace(r, verification_status="VERIFIED_SOURCE") for r in load_release_regulations())
        control = patch("crane_plan.pprk_composer.load_release_regulations", return_value=registry)
        control.start()
        self.addCleanup(control.stop)
    def test_replaced_external_bytes_block_prepared_and_rebuilt_production(self):
        from test_pprk_merge import fixture
        from hashlib import sha256
        project, scenario, verification = ready_project()
        with TemporaryDirectory() as tmp:
            source = fixture(Path(tmp) / "passport.pdf", ("FIRST",))
            doc = ExternalDocument("pass", "Паспорт", required=True, present=True,
                                   verification_status="VERIFIED", attachment_path=str(source))
            doc.verified_sha256 = sha256(source.read_bytes()).hexdigest()
            project.pprk_release.external_documents.append(doc)
            first = app.prepare_release(project, scenario, verification)
            first.require_requested_status()
            fixture(source, ("REPLACEMENT",))
            rebuilt = app.prepare_release(project, scenario, verification)
            self.assertFalse(rebuilt.bundle.production_allowed)
            self.assertIn("PPRK_EXTERNAL_REVISION_CHANGED", [i.code for i in rebuilt.issues if i.blocking])
            output = Path(tmp) / "release.pdf"
            output.write_bytes(b"previous")
            # Old prepared bundle also passes through the merger's snapshot check.
            with self.assertRaisesRegex(ValueError, "повторн"):
                app.publish_release(output, first, "same", lambda: "same")
            self.assertEqual(output.read_bytes(), b"previous")

    def test_legacy_verified_record_requires_explicit_reverification(self):
        from test_pprk_merge import fixture
        from hashlib import sha256
        from crane_plan import pprk_merge
        with TemporaryDirectory() as tmp:
            source = fixture(Path(tmp) / "passport.pdf", ("FIRST",))
            cfg = PPRKReleaseConfig.from_dict({"external_documents": [{
                "document_id": "pass", "title": "Паспорт", "present": True,
                "verification_status": "VERIFIED", "attachment_path": str(source)}]})
            doc, = cfg.external_documents
            self.assertEqual(doc.verification_status, "UNVERIFIED")
            verified = pprk_merge.verify_external_revision(doc)
            cfg.external_documents = [verified]
            restored, = PPRKReleaseConfig.from_dict(cfg.to_dict()).external_documents
            self.assertEqual(restored.verification_status, "VERIFIED")
            self.assertEqual(restored.verified_sha256, sha256(source.read_bytes()).hexdigest())
            self.assertEqual(pprk_merge.inspect_external_document(restored), ())

    def test_unknown_sling_scheme_has_same_visible_gate_and_physical_title(self):
        from pypdf import PdfReader
        project, scenario, verification = ready_project()
        project.loads[0].name = "Неизвестный груз"
        project.pprk_release.status = ReleaseStatus.REVIEW
        view = app.prepare_release(project, scenario, verification)
        self.assertEqual(view.bundle.requested_status, ReleaseStatus.REVIEW)
        self.assertEqual(view.bundle.effective_status, ReleaseStatus.PRELIMINARY)
        self.assertTrue(any(i.code == "PPRK_APPENDIX_REQUIRED" and i.blocking for i in view.issues))
        with self.assertRaises(ValueError):
            view.require_requested_status()
        project.pprk_release.status = view.bundle.effective_status
        draft = app.prepare_release(project, scenario, verification)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.pdf"
            app.publish_release(path, draft, "same", lambda: "same")
            title = PdfReader(path).pages[0].extract_text()
            self.assertIn("предварительная автоматизированная редакция", title.lower())
            self.assertNotIn("На проверку", title)

    def test_completeness_panel_refuses_protocol_from_different_variant(self):
        project, scenario, verification = ready_project()
        ui = MagicMock()
        ui.tabs = {"6. Отчёт": "report"}
        ui.notebook.select.return_value = "report"
        ui._project.return_value = project
        ui._editor_config.return_value = project.pprk_release
        ui._selected_release_index.return_value = 1
        ui._calculation_is_current.return_value = True
        ui.scenarios = [scenario, scenario]
        ui.scenario_verifications = [verification, verification]
        CranePlanApp._refresh_completeness(ui)
        summary = ui.release_summary.configure.call_args.kwargs["text"]
        self.assertNotIn("Доступен PRODUCTION", summary)
        problems = ui.issue_text.insert.call_args.args[1]
        self.assertIn("вариант", problems)
        self.assertIn("Блокирует", problems)

    def workpoint_editor(self):
        project, _, _ = _fixture()
        ui = MagicMock()
        ui.site_points = project.site.boundary
        ui.building_points = project.site.building
        ui.work_points = project.work_points
        ui._collect_loads.return_value = list(project.loads)
        ui.warning_acceptances = []
        return ui, project

    def test_malformed_loaded_index_does_not_reassign_live_point(self):
        ui, _ = self.workpoint_editor()
        point = ui.work_points[0]
        point.load_index = 17
        for require_geometry in (False, True):
            with self.subTest(require_geometry=require_geometry), self.assertRaisesRegex(ValueError, "груз"):
                CranePlanApp._project(ui, require_geometry=require_geometry)
            self.assertEqual(point.load_index, 17)

    def test_read_between_delete_last_load_and_add_replacement_preserves_index(self):
        ui, project = self.workpoint_editor()
        point = ui.work_points[0]
        ui.load_tree.selection.return_value = ("row",)
        ui.load_tree.index.return_value = 0
        ui.load_tree.delete.side_effect = lambda *_: ui._collect_loads.return_value.clear()
        CranePlanApp.delete_load(ui)
        with self.assertRaisesRegex(ValueError, "груз"):
            CranePlanApp._project(ui, require_geometry=False)
        self.assertEqual(point.load_index, 0)
        ui._collect_loads.return_value.append(project.loads[0])
        snapshot = CranePlanApp._project(ui, require_geometry=False)
        self.assertEqual(snapshot.work_points[0].load_index, 0)
