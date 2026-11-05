"""Reference publication must catch wrong load selection and changed pixels."""
import importlib
import importlib.util
import io
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from crane_plan.models import Load
from crane_plan.pprk_assets import ASSET_ROOT, load_asset_manifest
from crane_plan.pprk_composer import compose_pprk
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_models import PPRKReleaseConfig, ReleaseStatus
from crane_plan.pprk_templates import load_template_catalog
from crane_plan.report import generate_report
from test_pprk_context import _fixture
from test_pprk_sheets import _bundle, _project, _scenario


def composed(loads=None):
    project, scenario, verification = _fixture()
    if loads is not None:
        project.loads = loads
    context = build_pprk_context(project, scenario, verification)
    return project, compose_pprk(context, load_template_catalog(), load_asset_manifest(), PPRKReleaseConfig())


class AppendixTests(unittest.TestCase):
    def render_mixed_packet(self, directory, status=None):
        _, source = composed()
        base = _bundle(("LOAD_SCHEDULE",))
        appendix = source.part("appendix.SLINGING_CARDS")
        from crane_plan.pprk_composer import PPRKContentsEntry
        bundle = replace(base, parts=(*base.parts, appendix), contents=(*base.contents, PPRKContentsEntry(appendix.part_id, appendix.part_id, appendix.title, "", "appendix")), active_loads=source.active_loads)
        path = Path(directory) / "mixed.pdf"
        generate_report(path, _project(), [_scenario()], bundle=bundle, document_status=status)
        return path

    def test_status_is_visible_but_never_intersects_reference_image(self):
        import pdfplumber
        with tempfile.TemporaryDirectory() as tmp:
            path = self.render_mixed_packet(tmp, "REFERENCE STATUS")
            for page in PdfReader(path).pages:
                self.assertIn("REFERENCE STATUS", page.extract_text())
            with pdfplumber.open(path) as pdf:
                page = pdf.pages[-1]
                image, = page.images
                # Check every generated glyph, including rotated overlay text.
                for char in page.chars:
                    intersects = char["x0"] < image["x1"] and char["x1"] > image["x0"] and char["y0"] < image["y1"] and char["y1"] > image["y0"]
                    self.assertFalse(intersects, char)

    def test_every_bundle_load_table_uses_frozen_mass_not_current_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            pages = PdfReader(self.render_mixed_packet(tmp)).pages
            schedule = pages[5].extract_text()
            appendix = pages[6].extract_text()
            for text in (schedule, appendix):
                self.assertIn("1920", text)
                self.assertIn("Щит опалубки", text)
                self.assertNotIn("1320", text)
                self.assertNotIn("1200", text)
                self.assertNotIn("2.4", text)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("crane_plan.pprk_appendices"), "exact appendix renderer is missing")
        return importlib.import_module("crane_plan.pprk_appendices")

    def test_real_context_freezes_load_masses_dimensions_confirmation_and_operation(self):
        project, bundle = composed([Load("Щит опалубки", 1800, 120, 3, 1.2, 2.8,
            rigging_type="Канатный", rigging_branch_count=4, sling_identification="4СК-TEST",
            rigging_capacity_kg=2500, rigging_evidence="Испытательный паспорт 123", rigging_verified=True),
            Load("Неактивный", 1, 2, 3, 4, 5, active=False)])
        self.assertTrue(hasattr(bundle, "active_loads"), "bundle must bind immutable load payload")
        load, = bundle.active_loads
        self.assertEqual((load.load_index, load.name, load.load_kg, load.rigging_kg, load.total_kg, load.dimensions_m), (0, "Щит опалубки", 1800, 120, 1920, (3, 1.2, 2.8)))
        self.assertEqual(load.operation_ids, ("OP-W1-L1",))
        self.assertTrue(load.confirmed)
        project.loads[0].load_kg = 9999
        self.assertEqual(load.total_kg, 1920)
        self.assertEqual(self.api().build_slinging_cards(bundle)[0].scheme_number, 2)

    def test_explicit_scheme_selection_excludes_inactive_and_unknown_has_no_asset(self):
        _, bundle = composed([Load("Арматура в пучках", 500, 20, 6, 1, 1), Load("Бадья для бетона", 1800, 120, 2, 2, 3), Load("Космический аппарат", 100, 5, 1, 1, 1), Load("Трубы", 50, 2, 1, 1, 1, active=False)])
        cards = self.api().build_slinging_cards(bundle)
        self.assertEqual([card.scheme_number for card in cards], [1, 17, None])
        self.assertEqual([card.asset_id for card in cards], ["slinging", "slinging", ""])
        self.assertIn("НЕ ЗАПОЛНЕНО", cards[2].placeholder)
        self.assertTrue(any(issue.blocking for issue in cards[2].issues))

    def test_inactive_only_produces_no_cards(self):
        _, bundle = composed([Load("Опалубка", 5, 1, 1, 1, 1, active=False)])
        self.assertEqual(self.api().build_slinging_cards(bundle), ())

    def test_missing_legacy_bundle_payload_is_a_visible_blocking_placeholder(self):
        _, bundle = composed()
        card, = self.api().build_slinging_cards(replace(bundle, active_loads=None))
        self.assertIn("НЕ ЗАПОЛНЕНО", card.placeholder)
        self.assertTrue(card.issues[0].blocking)

    def test_pdf_has_exact_source_pixels_aspect_and_separate_project_table(self):
        _, bundle = composed()
        api = self.api()
        card, = api.build_slinging_cards(bundle)
        packet = io.BytesIO()
        canvas = Canvas(packet)
        result = api.draw_asset_appendix(canvas, card, load_asset_manifest())
        canvas.save()
        page, = PdfReader(io.BytesIO(packet.getvalue())).pages
        # The trusted 6575x6729 RGB board exceeds pypdf's default 75 MB
        # decompression cap. Raise it only for this exact-pixel comparison.
        with patch("pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH", 200_000_000):
            embedded, = page.images
        with Image.open(ASSET_ROOT / "slinging.png") as original:
            self.assertEqual(embedded.image.size, (6575, 6729))
            self.assertEqual(embedded.image.convert("RGB").tobytes(), original.convert("RGB").tobytes())
        x, y, w, h = result.image_box
        self.assertAlmostEqual(w / h, 6575 / 6729)
        self.assertGreaterEqual(float(page.mediabox.width), 594 * 72 / 25.4 - 1)
        text = page.extract_text()
        for value in ("Щит опалубки", "1800", "120", "1920", "3 × 1.2 × 2.8", "ПОДТВЕРЖДЕНО"):
            self.assertIn(value, text)
        import pdfplumber
        with pdfplumber.open(io.BytesIO(packet.getvalue())) as pdf:
            for char in pdf.pages[0].chars:
                self.assertTrue(char["x1"] <= x or char["x0"] >= x+w or char["y1"] <= y or char["y0"] >= y+h, char)

    def test_canonical_record_quality_category_and_dimensions_fail_closed(self):
        _, bundle = composed()
        api = self.api()
        card, = api.build_slinging_cards(bundle)
        record = load_asset_manifest()[0]
        for changed in (replace(record, sha256="0"*64), replace(record, category="storage"), replace(record, quality_status="pending"), replace(record, pixel_width=1), replace(record, title="подмена")):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "[Рр]есурс|[Аа]ссет"):
                    api.draw_asset_appendix(Canvas(io.BytesIO()), card, (changed,))
        with self.assertRaises(ValueError):
            api.draw_asset_appendix(Canvas(io.BytesIO()), card, ())

    def test_changed_or_missing_file_is_rejected_before_embedding(self):
        from unittest.mock import patch
        import shutil
        _, bundle = composed()
        api = self.api()
        card, = api.build_slinging_cards(bundle)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(ASSET_ROOT / "slinging.png", root / "slinging.png")
            with patch.object(api, "ASSET_ROOT", root):
                (root / "slinging.png").write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    api.draw_asset_appendix(Canvas(io.BytesIO()), card, load_asset_manifest())
                (root / "slinging.png").unlink()
                with self.assertRaises(ValueError):
                    api.draw_asset_appendix(Canvas(io.BytesIO()), card, load_asset_manifest())

    def test_report_appends_in_bundle_order_and_resolves_actual_pages(self):
        self.api()
        project, composed_bundle = composed()
        bundle = _bundle(("LOAD_SCHEDULE",))
        appendices = tuple(part for part in composed_bundle.parts if part.kind == "appendix" and part.sheets[0].asset_ids)
        note = replace(bundle.parts[4], sheets=(replace(bundle.parts[4].sheets[0], reference_keys=tuple(p.part_id for p in appendices)),))
        from crane_plan.pprk_composer import PPRKContentsEntry
        entries = tuple(PPRKContentsEntry(p.part_id, p.part_id, p.title, "", "appendix") for p in appendices)
        bundle = replace(bundle, parts=(*bundle.parts[:4], note, *bundle.parts[5:], *appendices), contents=(*bundle.contents, *entries), active_loads=composed_bundle.active_loads)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.pdf"
            generate_report(path, _project(), [_scenario()], bundle=bundle)
            pages = PdfReader(path).pages
            self.assertEqual(len(pages), 6 + len(appendices))
            for offset, part in enumerate(appendices, 7):
                self.assertEqual(len(pages[offset-1].images), 1)
                self.assertIn(f"стр. {offset}", pages[3].extract_text())
                self.assertIn(f"стр. {offset}", pages[4].extract_text())
            slinging_index = next(i for i, part in enumerate(appendices, 6) if part.part_id == "appendix.SLINGING_CARDS")
            self.assertIn("1920", pages[slinging_index].extract_text())
            self.assertNotIn("ОЖИДАЕТ ВКЛЮЧЕНИЯ", pages[4].extract_text())

    def test_unknown_active_load_blocks_final_release_and_preliminary_has_placeholder(self):
        self.api()
        _, bundle = composed([Load("Космический аппарат", 100, 5, 1, 1, 1)])
        bundle = replace(bundle, parts=tuple(replace(p, sheets=tuple(replace(s, reference_keys=tuple(k for k in s.reference_keys if not k.startswith("drawing."))) for s in p.sheets)) for p in bundle.parts if p.kind != "graphical"), contents=tuple(e for e in bundle.contents if e.kind != "graphical"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unknown.pdf"
            with self.assertRaisesRegex(ValueError, "[Пп]риложени|[Сс]тропов|[Сс]татус"):
                generate_report(path, _project(), [], bundle=replace(bundle, requested_status=ReleaseStatus.PRODUCTION))
            self.assertFalse(path.exists())
            generate_report(path, _project(), [], bundle=bundle)
            pages = PdfReader(path).pages
            self.assertTrue(any("Космический аппарат" in (p.extract_text() or "") and "НЕ ЗАПОЛНЕНО" in (p.extract_text() or "") for p in pages))

    def test_all_six_categories_embed_exact_pixels_in_stable_bundle_order(self):
        _, bundle = composed()
        api = self.api()
        from crane_plan.pprk_composer import PPRKAssetIdentity, PPRKDocumentPart, PPRKSheet
        records = load_asset_manifest()
        names = ("SLINGING_CARDS", "FENCING", "SAFETY_SIGNS", "HAND_SIGNALS", "STORAGE_SCHEMES", "PROTECTIVE_SCREENS")
        parts = tuple(PPRKDocumentPart("appendix."+name, record.title, "appendix", (PPRKSheet("appendix."+name, record.title, "appendix", asset_identities=(PPRKAssetIdentity(record.asset_id, record.sha256, record.category, record.quality_status),)),)) for name, record in zip(names, records))
        plans = api.plan_asset_appendices(replace(bundle, parts=parts), records)
        self.assertEqual([plan.asset_id for plan in plans], ["slinging", "fencing", "safety_signs", "hand_signals", "storage", "protective_screens"])
        for plan, record in zip(plans, records):
            with self.subTest(asset=record.asset_id):
                packet = io.BytesIO()
                canvas = Canvas(packet)
                result = api.draw_asset_appendix(canvas, plan, records)
                canvas.save()
                page, = PdfReader(io.BytesIO(packet.getvalue())).pages
                with patch("pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH", 200_000_000):
                    embedded, = page.images
                with Image.open(ASSET_ROOT / record.file_name) as image:
                    self.assertEqual(image.convert("RGB").tobytes(), embedded.image.convert("RGB").tobytes())
                self.assertEqual(result.sha256, record.sha256)

    def test_missing_required_dimensions_and_unconfirmed_values_remain_visible(self):
        _, bundle = composed()
        api = self.api()
        load, = bundle.active_loads
        card, = api.build_slinging_cards(replace(bundle, active_loads=(replace(load, dimensions_m=(3, None, 2)),)))
        self.assertIn("НЕ ЗАПОЛНЕНО", card.placeholder)
        self.assertTrue(card.issues)
        card, = api.build_slinging_cards(replace(bundle, active_loads=(replace(load, confirmed=False),)))
        self.assertIn("НЕ ПОДТВЕРЖДЕНО", dict(card.fields)["Подтверждение исходных данных"])
        self.assertTrue(card.issues[0].blocking)

    def test_incomplete_dimension_tuple_cannot_publish_a_scheme(self):
        _, bundle = composed()
        load, = bundle.active_loads
        card, = self.api().build_slinging_cards(replace(bundle, active_loads=(replace(load, dimensions_m=(3, 2)),)))
        self.assertEqual(card.asset_id, "")
        self.assertIn("НЕ ЗАПОЛНЕНО", card.placeholder)

    def test_expansion_keeps_verified_identity_for_each_active_card(self):
        _, bundle = composed()
        api = self.api()
        plans = api.plan_asset_appendices(bundle, load_asset_manifest())
        expanded = api.expand_bundle_appendices(bundle, plans)
        card = next(plan for plan in plans if plan.category == "slinging")
        sheet = expanded.sheet(card.sheet_id)
        self.assertEqual(sheet.asset_ids, ("slinging",))
        self.assertEqual(sheet.asset_identities[0].sha256, "1f4690b5bf2ef169c9f5227e6048105c48dd065650969d25ebb6b4330ec16009")

    def test_inactive_only_appendix_reference_is_explicitly_not_applicable(self):
        _, source = composed([Load("Опалубка", 5, 1, 1, 1, 1, active=False)])
        base = _bundle(())
        part = source.part("appendix.SLINGING_CARDS")
        note = replace(base.parts[4], sheets=(replace(base.parts[4].sheets[0], reference_keys=(part.part_id,)),))
        bundle = replace(base, parts=(*base.parts[:4], note, part), active_loads=())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inactive.pdf"
            generate_report(path, _project(), [], bundle=bundle)
            pages = PdfReader(path).pages
            self.assertEqual(len(pages), 5)
            self.assertIn("НЕ ПРИМЕНИМО", pages[4].extract_text())
            self.assertNotIn("ОЖИДАЕТ ВКЛЮЧЕНИЯ", pages[4].extract_text())


if __name__ == "__main__":
    unittest.main()

