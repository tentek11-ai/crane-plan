"""External assembly regression tests: physical geometry, safety and final references."""
import hashlib
import importlib
import importlib.util
import io
import re
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject, NameObject, NumberObject
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.pdfgen.canvas import Canvas

from crane_plan.pprk_models import ExternalDocument, ReleaseStatus
from crane_plan.pprk_composer import PPRKDocumentPart, PPRKSheet, PPRKContentsEntry
from crane_plan.report import generate_report
from test_pprk_text_report import sample_bundle, sample_project


def fixture(path, markers=("A4-MARK", "A3-MARK", "ROTATED-MARK", "CROP-MARK")):
    packet = io.BytesIO()
    canvas = Canvas(packet, pagesize=A4)
    for index, marker in enumerate(markers):
        canvas.setPageSize(landscape(A3) if index == 1 else A4)
        canvas.drawString(60, 150, marker)
        canvas.rect(40, 100, 120, 100)
        canvas.showPage()
    canvas.save()
    writer = PdfWriter()
    for index, page in enumerate(PdfReader(packet).pages):
        if index == 2:
            page.rotate(90)
        if index == 3:
            page.cropbox = RectangleObject((25, 45, 400, 600))
        writer.add_page(page)
    with path.open("wb") as stream:
        writer.write(stream)
    return path


def record(path, id="foundation", **kwargs):
    return ExternalDocument(id, "External foundation", present=True, attachment_path=str(path), verification_status="VERIFIED", verified_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), number="DOC-19", date="04.11.2026", organization="Engineering Org", **kwargs)


def signature(page):
    return (tuple(page.mediabox), tuple(page.cropbox), page.get("/Rotate"), page.get_contents().get_data())


class MergeTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("crane_plan.pprk_merge"), "external merge service is missing")
        return importlib.import_module("crane_plan.pprk_merge")

    def test_mixed_pages_order_geometry_content_and_source_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = fixture(root / "main.pdf", ("MAIN",))
            source = fixture(root / "проект основания с пробелами.pdf")
            hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (main, source)]
            result = self.api().merge_pprk_documents(main, [record(source)], root / "final.pdf")
            self.assertEqual(result.page_count, 5)
            self.assertEqual(result.page_ranges["foundation"], (2, 5))
            pages = PdfReader(result.output_pdf).pages
            self.assertEqual([p.extract_text().strip().splitlines()[0] for p in pages], ["MAIN", "A4-MARK", "A3-MARK", "ROTATED-MARK", "CROP-MARK"])
            self.assertEqual([signature(p) for p in pages[1:]], [signature(p) for p in PdfReader(source).pages])
            self.assertEqual(hashes, [hashlib.sha256(p.read_bytes()).hexdigest() for p in (main, source)])

    def test_missing_documents_have_structured_issues_no_phantom_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = fixture(root / "main.pdf", ("MAIN",))
            docs = [ExternalDocument("optional", "Optional"), ExternalDocument("required", "Required", required=True)]
            result = self.api().merge_pprk_documents(main, docs, root / "out.pdf")
            self.assertEqual(result.page_count, 1)
            self.assertEqual(result.page_ranges, {})
            self.assertEqual([(i.code, i.blocking) for i in result.issues], [("PPRK_EXTERNAL_MISSING", False), ("PPRK_EXTERNAL_MISSING", True)])

    def test_invalid_sources_rollback_and_cleanup(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = fixture(root / "main.pdf", ("MAIN",))
            output = fixture(root / "out.pdf", ("OLD",))
            old = output.read_bytes()
            corrupt = root / "corrupt.pdf"
            corrupt.write_bytes(b"%PDF-1.4\ncorrupt")
            nonpdf = root / "wrong.txt"
            nonpdf.write_text("not pdf")
            empty = root / "empty.pdf"
            with empty.open("wb") as stream:
                PdfWriter().write(stream)
            encrypted = root / "encrypted.pdf"
            writer = PdfWriter()
            writer.add_blank_page(200, 300)
            writer.encrypt("secret")
            with encrypted.open("wb") as stream:
                writer.write(stream)
            for source in (corrupt, nonpdf, empty, encrypted):
                with self.subTest(source=source):
                    with self.assertRaises(api.PPRKMergeError) as caught:
                        api.merge_pprk_documents(main, [record(source, required=True)], output)
                    self.assertTrue(caught.exception.issues)
                    self.assertEqual(output.read_bytes(), old)
            self.assertFalse(list(root.glob("*.merge.tmp.pdf")))

    def test_duplicate_and_aliases_are_rejected_without_touching_inputs(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = fixture(root / "main.pdf", ("MAIN",))
            source = fixture(root / "source.pdf", ("EXTERNAL",))
            for docs, output in (([record(source), record(source, "other")], root / "out.pdf"), ([record(source), record(source)], root / "out.pdf"), ([record(main)], root / "out.pdf"), ([record(source)], main), ([record(source)], source)):
                with self.subTest(output=output, docs=docs):
                    with self.assertRaises(api.PPRKMergeError):
                        api.merge_pprk_documents(main, docs, output)
            self.assertIn("MAIN", PdfReader(main).pages[0].extract_text())

    def test_write_failure_keeps_previous_output(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = fixture(root / "main.pdf", ("MAIN",))
            output = fixture(root / "out.pdf", ("OLD",))
            old = output.read_bytes()
            with patch.object(api.PdfWriter, "write", side_effect=OSError("disk full")):
                with self.assertRaises(api.PPRKMergeError):
                    api.merge_pprk_documents(main, [], output)
            self.assertEqual(output.read_bytes(), old)
            self.assertFalse(list(root.glob("*.merge.tmp.pdf")))

    def bundle(self, docs):
        bundle = sample_bundle(long_text=True)
        parts = tuple(PPRKDocumentPart("external." + doc.document_id, doc.title, "external", (PPRKSheet("external." + doc.document_id, doc.title, "external", fields=(("attachment_path", doc.attachment_path),)),)) for doc in docs)
        note = replace(bundle.parts[4], sheets=(replace(bundle.parts[4].sheets[0], reference_keys=("external.foundation", "appendix.TIE_IN_PROJECT")),))
        return replace(bundle, parts=(*bundle.parts[:4], note, *bundle.parts[5:], *parts), contents=(*bundle.contents, *(PPRKContentsEntry(p.part_id, p.part_id, p.title, "", "external") for p in parts)))

    def test_report_uses_bundle_order_resolves_references_and_register_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = record(fixture(root / "first.pdf"))
            second = record(fixture(root / "second.pdf", ("SECOND",)), "tie_in_project")
            project = sample_project()
            project.pprk_release.external_documents = [second, first]
            path = generate_report(root / "final.pdf", project, [], bundle=self.bundle([first, second]), document_status="DRAFT STATUS")
            pages = PdfReader(path).pages
            self.assertEqual([p.extract_text().strip().splitlines()[0] for p in pages[-5:]], ["A4-MARK", "A3-MARK", "ROTATED-MARK", "CROP-MARK", "SECOND"])
            text = "\n".join(p.extract_text() for p in pages[:-5])
            for value in ("foundation", "DOC-19", "04.11.2026", "Engineering Org", "VERIFIED"):
                self.assertIn(value, text)
            self.assertNotIn("ОЖИДАЕТ ВКЛЮЧЕНИЯ", text)
            self.assertNotIn("DRAFT STATUS", pages[-1].extract_text())
            self.assertIn(f"стр. {len(pages)-4}–{len(pages)-1}", text)
            self.assertIn(f"стр. {len(pages)}", text)
            self.assertEqual([signature(p) for p in pages[-5:-1]], [signature(p) for p in PdfReader(first.attachment_path).pages])
            # The finalized contents assigns exactly one row to every physical page.
            contents = "\n".join(p.extract_text() for p in pages if "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ" in p.extract_text())
            for number in range(1, len(pages) + 1):
                self.assertEqual(re.findall(r"стр\. (\d+)", contents).count(str(number)), 1)

    def test_report_missing_required_visible_preliminary_but_blocks_production(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = sample_project()
            project.pprk_release.external_documents = [ExternalDocument("missing", "Required structural project", required=True)]
            path = Path(tmp) / "preliminary.pdf"
            generate_report(path, project, [], bundle=sample_bundle())
            self.assertIn("ОЖИДАЕТ ВКЛЮЧЕНИЯ", "\n".join(p.extract_text() for p in PdfReader(path).pages))
            old = path.read_bytes()
            with self.assertRaises(ValueError):
                generate_report(path, project, [], bundle=replace(sample_bundle(), requested_status=ReleaseStatus.PRODUCTION))
            self.assertEqual(path.read_bytes(), old)

    def test_bundle_path_mismatch_blocks_and_preserves_previous_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = record(fixture(root / "right.pdf", ("RIGHT",)))
            project = sample_project()
            project.pprk_release.external_documents = [replace(doc, attachment_path=str(fixture(root / "wrong.pdf", ("WRONG",))))]
            output = fixture(root / "out.pdf", ("OLD",))
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                generate_report(output, project, [], bundle=self.bundle([doc]))
            self.assertEqual(output.read_bytes(), before)

    def test_graphics_and_asset_appendices_survive_external_finalization(self):
        from test_pprk_appendices import composed
        from test_pprk_sheets import _bundle, _project, _scenario
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, source = composed()
            base = _bundle(("LOAD_SCHEDULE",))
            appendix = source.part("appendix.SLINGING_CARDS")
            doc = record(fixture(root / "source.pdf", ("EXTERNAL-LAST",)))
            external = self.bundle([doc]).parts[-1]
            note = replace(base.parts[4], sheets=(replace(base.parts[4].sheets[0], reference_keys=("drawing.LOAD_SCHEDULE", "external.foundation", "appendix.SLINGING_CARDS")),))
            bundle = replace(base, parts=(*base.parts[:4], note, *base.parts[5:], appendix, external), contents=(*base.contents, PPRKContentsEntry(appendix.part_id, appendix.part_id, appendix.title, "", "appendix"), PPRKContentsEntry(external.part_id, external.part_id, external.title, "", "external")), active_loads=source.active_loads)
            project = _project()
            project.pprk_release.external_documents = [doc]
            output = generate_report(root / "mixed.pdf", project, [_scenario()], bundle=bundle)
            pages = PdfReader(output).pages
            self.assertIn("EXTERNAL-LAST", pages[-1].extract_text())
            self.assertIn("1920", pages[-2].extract_text())
            self.assertIn("1920", pages[-3].extract_text())
            self.assertAlmostEqual(float(pages[-2].mediabox.height), 2383.937, places=2)
            text = "\n".join(p.extract_text() for p in pages[:-1])
            self.assertNotIn("ОЖИДАЕТ ВКЛЮЧЕНИЯ", text)
            self.assertIn(f"ГЧ-01 / стр. {len(pages)-2}", text)

    def test_reopen_verification_rejects_rescaled_staged_page(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = fixture(root / "main.pdf", ("MAIN",))
            output = fixture(root / "out.pdf", ("OLD",))
            old = output.read_bytes()
            original_write = api.PdfWriter.write
            def rescale(writer, stream):
                writer.pages[0][NameObject("/UserUnit")] = NumberObject(2)
                return original_write(writer, stream)
            with patch.object(api.PdfWriter, "write", rescale):
                with self.assertRaises(api.PPRKMergeError):
                    api.merge_pprk_documents(main, [], output)
            self.assertEqual(output.read_bytes(), old)

    def test_source_change_during_write_prevents_publication(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = fixture(root / "main.pdf", ("MAIN",))
            source = fixture(root / "source.pdf", ("SOURCE",))
            output = fixture(root / "out.pdf", ("OLD",))
            old = output.read_bytes()
            original_write = api.PdfWriter.write
            def change_source(writer, stream):
                result = original_write(writer, stream)
                source.write_bytes(source.read_bytes() + b"\n% concurrent mutation")
                return result
            with patch.object(api.PdfWriter, "write", change_source):
                with self.assertRaises(api.PPRKMergeError) as caught:
                    api.merge_pprk_documents(main, [record(source)], output)
            self.assertEqual(caught.exception.issues[0].code, "PPRK_EXTERNAL_SOURCE_CHANGED")
            self.assertEqual(output.read_bytes(), old)

    def test_unverified_and_false_presence_existing_attachment_rejected(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = fixture(root / "main.pdf", ("MAIN",))
            doc = record(fixture(root / "source.pdf", ("SOURCE",)))
            for changed in (replace(doc, verification_status="UNVERIFIED"), replace(doc, present=False)):
                with self.subTest(changed=changed):
                    with self.assertRaises(api.PPRKMergeError):
                        api.merge_pprk_documents(main, [changed], root / "out.pdf")

    def test_many_external_pages_have_complete_contents_and_exact_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = record(fixture(root / "large.pdf", tuple(f"EXTERNAL-{i}" for i in range(65))))
            project = sample_project()
            project.pprk_release.external_documents = [doc]
            output = generate_report(root / "large-final.pdf", project, [], bundle=self.bundle([doc]))
            pages = PdfReader(output).pages
            contents = "\n".join(p.extract_text() for p in pages if "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ" in p.extract_text())
            for number in range(1, len(pages)+1):
                self.assertEqual(re.findall(r"стр\. (\d+)", contents).count(str(number)), 1)
            self.assertIn("EXTERNAL-0", pages[-65].extract_text())
            self.assertIn("EXTERNAL-64", pages[-1].extract_text())
            self.assertIn(f"стр. {len(pages)-64}–{len(pages)}", "\n".join(p.extract_text() for p in pages[:-65]))

    def test_noncanonical_interleaved_external_part_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = record(fixture(root / "source.pdf", ("SOURCE",)))
            project = sample_project()
            project.pprk_release.external_documents = [doc]
            bundle = self.bundle([doc])
            bundle = replace(bundle, parts=(*bundle.parts[:4], bundle.parts[-1], *bundle.parts[4:-1]))
            with self.assertRaises(ValueError):
                generate_report(root / "out.pdf", project, [], bundle=bundle)

    def test_final_report_publish_failure_is_structured_and_atomic(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = record(fixture(root / "source.pdf", ("SOURCE",)))
            project = sample_project()
            project.pprk_release.external_documents = [doc]
            output = fixture(root / "out.pdf", ("OLD",))
            before = output.read_bytes()
            original_replace = api.os.replace
            def fail_final(source, destination):
                if Path(destination) == output:
                    raise OSError("destination locked")
                return original_replace(source, destination)
            with patch.object(api.os, "replace", fail_final):
                with self.assertRaises(api.PPRKMergeError):
                    generate_report(output, project, [], bundle=self.bundle([doc]))
            self.assertEqual(output.read_bytes(), before)
            self.assertFalse(list(root.glob(".pprk-assembly-*")))

    def test_missing_structural_project_issue_blocks_production_without_record(self):
        from crane_plan.pprk_models import CompletenessIssue
        with tempfile.TemporaryDirectory() as tmp:
            output = fixture(Path(tmp) / "out.pdf", ("OLD",))
            before = output.read_bytes()
            bundle = replace(sample_bundle(), requested_status=ReleaseStatus.PRODUCTION, completeness_issues=(CompletenessIssue("PPRK_TIE_PROJECT_REQUIRED", "Missing structural tie project", True, "external_documents/tie_in_project"),))
            with self.assertRaises(ValueError):
                generate_report(output, sample_project(), [], bundle=bundle)
            self.assertEqual(output.read_bytes(), before)

    def test_55_distinct_external_documents_paginate_contents_and_keep_references(self):
        from test_pprk_sheets import _bundle, _project, _scenario
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = [replace(record(fixture(root / f"source-{i:02}.pdf", (f"SOURCE-{i:03}",)), f"doc_{i:02}"), title=f"DOCUMENT-{i:03}") for i in range(55)]
            base = _bundle(("LOAD_SCHEDULE",))
            external = self.bundle(docs).parts[-55:]
            note = replace(base.parts[4], sheets=(replace(base.parts[4].sheets[0], reference_keys=("drawing.LOAD_SCHEDULE", "external.doc_00", "external.doc_54")),))
            bundle = replace(base, parts=(*base.parts[:4], note, *base.parts[5:], *external), contents=(*base.contents, *(PPRKContentsEntry(p.part_id, p.part_id, p.title, "", "external") for p in external)))
            self.assertEqual(len(bundle.contents), 61)
            project = _project()
            project.pprk_release.external_documents = list(reversed(docs))
            output = generate_report(root / "final-55.pdf", project, [_scenario()], bundle=bundle)
            pages = PdfReader(output).pages
            self.assertEqual([p.extract_text().strip().splitlines()[0] for p in pages[-55:]], [f"SOURCE-{i:03}" for i in range(55)])
            contents = "\n".join(p.extract_text() for p in pages if "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ" in p.extract_text())
            self.assertEqual(sorted(map(int, re.findall(r"стр\. (\d+)", contents))), list(range(1, len(pages)+1)))
            register_pages = [p for p in pages[:-55] if any(f"doc_{i:02} —" in p.extract_text() for i in range(55)) and "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ" not in p.extract_text()]
            register = "\n".join(p.extract_text() for p in register_pages)
            for i in range(55):
                self.assertEqual(contents.count(f"DOCUMENT-{i:03}"), 1)
                self.assertEqual(register.count(f"doc_{i:02} —"), 1)
                self.assertRegex(register, rf"doc_{i:02} — DOCUMENT-{i:03}.*?стр\. {len(pages)-54+i}\b")
            graphic_page = next(i for i,p in enumerate(pages,1) if "Грузовая ведомость" in p.extract_text() and "1920" not in p.extract_text() and "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ" not in p.extract_text())
            note_text = pages[4].extract_text()
            self.assertIn(f"ГЧ-01 / стр. {graphic_page}", note_text)
            self.assertIn(f"стр. {len(pages)-54}", note_text)
            self.assertIn(f"стр. {len(pages)}", note_text)
            self.assertNotIn("ОЖИДАЕТ ВКЛЮЧЕНИЯ", register)

    def test_implicit_external_issues_create_pending_preliminary_register_without_records(self):
        from crane_plan.pprk_models import CompletenessIssue
        with tempfile.TemporaryDirectory() as tmp:
            for code, document_id, message in (
                ("PPRK_TIE_PROJECT_REQUIRED", "tie_in_project", "Требуется внешний проект крепления крана к зданию"),
                ("PPRK_EXTERNAL_DOCUMENT_REQUIRED", "foundation_project", "Требуется внешний проект основания крана"),
            ):
                with self.subTest(code=code):
                    project = sample_project()
                    issue = CompletenessIssue(code, message, False, f"external_documents/{document_id}")
                    bundle = replace(sample_bundle(), completeness_issues=(issue, issue))
                    output = generate_report(Path(tmp) / f"{document_id}.pdf", project, [], bundle=bundle)
                    text = "\n".join(p.extract_text() for p in PdfReader(output).pages)
                    self.assertIn("Реестр внешних документов", text)
                    self.assertIn("ОЖИДАЕТ ВКЛЮЧЕНИЯ", text)
                    self.assertEqual(text.count(message), 1)
                    self.assertIn(document_id, text)
                    self.assertEqual(project.pprk_release.external_documents, [])
                    self.assertFalse(any(p.kind == "external" for p in bundle.parts))

    def test_implicit_generic_external_issue_blocks_production_atomically(self):
        from crane_plan.pprk_models import CompletenessIssue
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            output = fixture(Path(tmp) / "out.pdf", ("OLD",))
            before = output.read_bytes()
            issue = CompletenessIssue("PPRK_EXTERNAL_DOCUMENT_REQUIRED", "Missing foundation structural project", True, "external_documents/foundation_project")
            bundle = replace(sample_bundle(), requested_status=ReleaseStatus.PRODUCTION, completeness_issues=(issue,))
            with self.assertRaises(api.PPRKMergeError) as caught:
                generate_report(output, sample_project(), [], bundle=bundle)
            self.assertEqual(caught.exception.issues, (issue,))
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
