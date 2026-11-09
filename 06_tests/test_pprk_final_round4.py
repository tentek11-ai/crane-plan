"""Exact review repros: absent-source races, encoded declarations, labeled evidence."""
from copy import deepcopy
import csv
import io
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from pypdf import PdfReader

import test_pprk_final_round3 as r3
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_models import ReleaseStatus
from crane_plan.pprk_release_validation import ForbiddenReferenceError, UnsafePDFMetadataError, validate_release_pdf
from crane_plan.pprk_release_workflow import prepare_release, require_saveable_release
from crane_plan.report import generate_report
import crane_plan.pprk_regulations as regulations


ENCODINGS = (
    ("utf-8", "UTF-8", b""), ("utf-8", "UTF-8", b"\xef\xbb\xbf"),
    ("utf-16-le", "UTF-16LE", b""), ("utf-16-le", "UTF-16", b"\xff\xfe"),
    ("utf-16-be", "UTF-16BE", b""), ("utf-16-be", "UTF-16", b"\xfe\xff"),
    ("utf-32-le", "UTF-32LE", b""), ("utf-32-le", "UTF-32", b"\xff\xfe\x00\x00"),
    ("utf-32-be", "UTF-32BE", b""), ("utf-32-be", "UTF-32", b"\x00\x00\xfe\xff"),
    ("cp1251", "windows-1251", b""),
)


def xml_payload(encoding, declared, bom, *, dtd=False, forbidden=False):
    declaration = f'<?xml version="1.0" encoding="{declared}"?>'
    if dtd:
        body = '<!DOCTYPE x [<!ENTITY a "safe">]><x>&a;</x>'
    elif forbidden:
        body = '<x value="27.06&#x2D;23">safe</x>'
    else:
        body = '<x value="Документ №42">hello&#x20;world</x>'
    return bom + (declaration + body).encode(encoding)


class ParserReached(BaseException):
    pass


def validate_without_reaching_xml_parser(source):
    """Audit real parser entry with profiling, without patching any function."""
    prior = sys.getprofile()
    parser_codes = {ET.fromstring.__code__, ET.iterparse.__code__}
    def audit(frame, event, arg):
        if event == "call" and frame.f_code in parser_codes:
            raise ParserReached("XML parser reached before DTD/ENTITY rejection")
        if event == "c_call" and isinstance(getattr(arg, "__self__", None), ET.XMLParser):
            raise ParserReached("XML parser feed reached before DTD/ENTITY rejection")
    try:
        sys.setprofile(audit)
        validate_release_pdf(source)
    finally:
        sys.setprofile(prior)


class Round4Tests(unittest.TestCase):
    assert_gui_atomic_rejection = r3.round2.Round2Tests.assert_gui_atomic_rejection

    def test_missing_underlays_created_after_capture_are_ignored_in_both_report_modes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kind in ("plan", "section"):
                for bundled in (False, True):
                    with self.subTest(kind=kind, bundled=bundled):
                        directory = root / f"{kind}-{bundled}"; directory.mkdir()
                        project, scenario = r3.round2.ready(directory / "fixture")
                        source = directory / "not-created-yet.pdf"
                        poison = r3.underlay(directory / "replacement.pdf", True)
                        r3.calibrated(project, kind, source)
                        before = project.to_dict()
                        bundle = prepare_release(project, scenario, r3.verify(project, scenario)).bundle if bundled else None
                        output = directory / "report.pdf"; output.write_bytes(b"previous")
                        self.assertFalse(source.exists())
                        r3.race_after_staging(directory, source, poison,
                            lambda: generate_report(output, project, [scenario], bundle=bundle), output)
                        self.assertIn("27.06-23", PdfReader(source).pages[0].extract_text())
                        title = "СТРОЙГЕНПЛАН." if kind == "plan" else "ВЫСОТНАЯ ПРИВЯЗКА."
                        page = next(p for p in PdfReader(output).pages if p.extract_text().startswith(title))
                        self.assertEqual(list(page.images), [], "A source absent at capture was later rendered")
                        self.assertEqual(project.to_dict(), before)

    def test_gui_late_underlay_creation_preserves_previous_reports_and_sidecars(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kind in ("plan", "section"):
                with self.subTest(kind=kind):
                    directory = root / kind; directory.mkdir()
                    project, scenario = r3.round2.ready(directory / "fixture")
                    source = directory / "not-created-yet.pdf"
                    poison = r3.underlay(directory / "replacement.pdf", True)
                    r3.calibrated(project, kind, source)
                    checked = r3.verify(project, scenario)
                    r3.race_after_staging(directory, source, poison,
                        lambda: self.assert_gui_atomic_rejection(project, scenario, checked, directory))

    def test_encoded_dtds_are_rejected_before_any_xml_parser_entry(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for target in ("page", "form"):
                for index, (encoding, declared, bom) in enumerate(ENCODINGS):
                    with self.subTest(target=target, encoding=encoding, bom=bool(bom)):
                        source = r3.metadata_pdf(root / f"{target}-{index}.pdf", xml_payload(encoding, declared, bom, dtd=True), target)
                        caught = None
                        try: validate_without_reaching_xml_parser(source)
                        except BaseException as exc: caught = exc
                        self.assertIsInstance(caught, UnsafePDFMetadataError)

    def test_safe_encoded_xml_is_accepted_and_decoded_entity_tokens_are_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for target in ("page", "form"):
                for index, (encoding, declared, bom) in enumerate(ENCODINGS):
                    with self.subTest(target=target, encoding=encoding, bom=bool(bom), kind="safe"):
                        safe = r3.metadata_pdf(root / f"safe-{target}-{index}.pdf", xml_payload(encoding, declared, bom), target)
                        try: validate_release_pdf(safe)
                        except ValueError as exc: self.fail(f"Safe declared XML encoding rejected: {exc}")
                    with self.subTest(target=target, encoding=encoding, bom=bool(bom), kind="entity"):
                        source = r3.metadata_pdf(root / f"token-{target}-{index}.pdf", xml_payload(encoding, declared, bom, forbidden=True), target)
                        caught = None
                        try: validate_release_pdf(source)
                        except ValueError as exc: caught = exc
                        self.assertIs(type(caught), ForbiddenReferenceError, "Decode valid XML then find its token, rather than rejecting its encoding")

    def test_reviewer_utf16le_bomless_form_dtd_is_fatal_for_every_public_status(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = xml_payload("utf-16-le", "UTF-16LE", b"", dtd=True)
            for status in ReleaseStatus:
                directory = root / status.value
                project, scenario = r3.round2.ready(directory / "fixture")
                source = r3.external_fixture(directory / "neutral.pdf", ("CLEAN",))
                r3.attach(project, source); project.pprk_release.status = status
                checked = r3.verify(project, scenario)
                release = prepare_release(project, scenario, checked)
                r3.metadata_pdf(source, payload, "form")
                with self.subTest(status=status, boundary="prepared"):
                    caught = None
                    try: require_saveable_release(release, checked)
                    except ValueError as exc: caught = exc
                    self.assertIsInstance(caught, UnsafePDFMetadataError)
                project.pprk_release.external_documents[-1].verified_sha256 = r3.hashlib.sha256(source.read_bytes()).hexdigest()
                with self.subTest(status=status, boundary="prepare"):
                    caught = None
                    try: prepare_release(project, scenario, checked)
                    except ValueError as exc: caught = exc
                    self.assertIsInstance(caught, UnsafePDFMetadataError)
                with self.subTest(status=status, boundary="public"):
                    self.assert_gui_atomic_rejection(project, scenario, checked, directory / "gui")

    def test_bomless_encoded_form_dtd_underlays_block_gui_and_legacy_atomically(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = r3.metadata_pdf(root / "neutral.pdf", xml_payload("utf-16-le", "UTF-16LE", b"", dtd=True), "form")
            for kind in ("plan", "section"):
                project, scenario = r3.round2.ready(root / kind / "fixture")
                r3.calibrated(project, kind, source)
                with self.subTest(kind=kind, boundary="legacy"):
                    output = root / f"{kind}.pdf"; output.write_bytes(b"previous")
                    with self.assertRaises(UnsafePDFMetadataError): generate_report(output, project, [scenario])
                    self.assertEqual(output.read_bytes(), b"previous")
                with self.subTest(kind=kind, boundary="public"):
                    self.assert_gui_atomic_rejection(project, scenario, r3.verify(project, scenario), root / kind / "gui")

    def test_labeled_sentinels_anywhere_in_rigging_fields_are_not_confirmation(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r3.round2.ready(Path(tmp) / "fixture")
            checked = r3.verify(project, scenario)
            self.assertTrue(build_pprk_context(project, scenario, checked).active_loads[0].confirmed)
            values = ("Номер: НЕ ЗАПОЛНЕНО", "Паспорт: НЕ ПРОВЕРЕНО", "Тип оснастки отсутствует",
                      " номер__не___заполнено ", "ПАСПОРТ__Н.Е.П.Р.О.В.Е.Р.Е.Н.О", "ТипоснасткиОТСУТСТВУЕТ")
            for field in ("rigging_type", "sling_identification", "rigging_evidence"):
                for value in values:
                    with self.subTest(field=field, value=value):
                        changed = deepcopy(project); setattr(changed.loads[0], field, value)
                        self.assertFalse(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed)
            for field, value in (("rigging_type", "Тип: канатный четырёхветвевой"),
                                 ("sling_identification", "Номер: НЕТТО-42"), ("rigging_evidence", "Паспорт No.42: ПРОВЕРЕНО")):
                with self.subTest(valid_field=field):
                    changed = deepcopy(project); setattr(changed.loads[0], field, value)
                    self.assertTrue(build_pprk_context(changed, scenario, r3.verify(changed, scenario)).active_loads[0].confirmed)

    def test_labeled_placeholders_are_pending_on_physical_cards_and_block_production(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for field, value in (("rigging_type", "Тип оснастки отсутствует"),
                                 ("sling_identification", "Номер: НЕ ЗАПОЛНЕНО"), ("rigging_evidence", "Паспорт: НЕ ПРОВЕРЕНО")):
                with self.subTest(field=field):
                    project, scenario = r3.round2.ready(root / field / "fixture")
                    setattr(project.loads[0], field, value)
                    checked = r3.verify(project, scenario)
                    output = r3.save_via_gui(project, scenario, checked, root / field / "draft")
                    card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                    self.assertIn("НЕ ПОДТВЕРЖДЕНО", card)
                    self.assertNotIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                    project.pprk_release.status = ReleaseStatus.PRODUCTION
                    self.assert_gui_atomic_rejection(project, scenario, checked, root / field / "production")

    def test_valid_labeled_evidence_still_produces_a_confirmed_production_card(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, scenario = r3.round2.ready(root / "fixture")
            load = project.loads[0]
            load.rigging_type = "Тип: канатный четырёхветвевой"
            load.sling_identification = "Номер: 4СК-42"
            load.rigging_evidence = "Паспорт No.42: ПРОВЕРЕНО"
            project.pprk_release.status = ReleaseStatus.PRODUCTION
            # Isolated legally-verified data fixture; no production function or
            # shipped regulation row is modified to bypass the independent gate.
            with regulations.DEFAULT_REGISTRY_PATH.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream); columns = reader.fieldnames; rows = list(reader)
            for row in rows: row["verification_status"] = "VERIFIED_SOURCE"
            registry = root / "controlled-registry.csv"
            with registry.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader(); writer.writerows(rows)
            with patch.object(regulations, "DEFAULT_REGISTRY_PATH", registry):
                checked = r3.verify(project, scenario)
                require_saveable_release(prepare_release(project, scenario, checked), checked)
                output = r3.save_via_gui(project, scenario, checked, root / "production")
            card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
            self.assertIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
            self.assertIn("Номер: 4СК-42", card)
            self.assertNotIn("НЕ ЗАПОЛНЕНО", card)

    def test_missing_grammatical_forms_are_not_valid_but_clarified_evidence_is(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r3.round2.ready(Path(tmp) / "fixture")
            for value in ("НЕПРОВЕРЕННЫЙ", "Паспорт: НЕПРОВЕРЕННЫЙ", "Незаполненная ведомость",
                          "Неуказанный строп", "Отсутствующий паспорт", "Ожидающий подтверждения", "Подлежит уточнению"):
                with self.subTest(missing=value):
                    changed = deepcopy(project); changed.loads[0].rigging_evidence = value
                    self.assertFalse(build_pprk_context(changed, scenario, r3.verify(changed, scenario)).active_loads[0].confirmed)
            for value in ("Уточнённый паспорт №42", "Паспорт: ПРОВЕРЕННЫЙ №42", "Паспорт No.42: ПРОВЕРЕНО"):
                with self.subTest(valid=value):
                    changed = deepcopy(project); changed.loads[0].rigging_evidence = value
                    self.assertTrue(build_pprk_context(changed, scenario, r3.verify(changed, scenario)).active_loads[0].confirmed)

    def test_expanded_and_unused_namespace_uris_are_scanned_before_publication(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payloads = (b'<x xmlns:s="27.06&#45;23"><s:field>safe</s:field></x>',
                        b'<x xmlns:s="27.06&#x2D;23">safe</x>',
                        b'<x xmlns="27.06&#x2D;23">safe</x>',
                        b'<x xmlns:s="27.06&#45;23" s:field="safe"/>')
            for target in ("page", "form"):
                for index, payload in enumerate(payloads):
                    with self.subTest(target=target, index=index, boundary="physical"):
                        source = r3.metadata_pdf(root / f"{target}-{index}.pdf", payload, target)
                        caught = None
                        try: validate_release_pdf(source)
                        except ValueError as exc: caught = exc
                        self.assertIs(type(caught), ForbiddenReferenceError)
            with self.subTest(boundary="public"):
                project, scenario = r3.round2.ready(root / "fixture")
                source = r3.metadata_pdf(root / "external.pdf", payloads[1], "form")
                r3.attach(project, source)
                self.assert_gui_atomic_rejection(project, scenario, r3.verify(project, scenario), root / "gui")
            with self.subTest(boundary="safe namespace"):
                safe_payload = b'<x xmlns="https://example.test/pprk" xmlns:s="https://example.test/unused" value="safe">hello</x>'
                safe = r3.metadata_pdf(root / "safe.pdf", safe_payload, "form")
                validate_release_pdf(safe)
                project, scenario = r3.round2.ready(root / "safe-fixture")
                r3.attach(project, safe)
                output = r3.save_via_gui(project, scenario, r3.verify(project, scenario), root / "safe-gui")
                metadata = []
                for page in PdfReader(output).pages:
                    objects = page.get("/Resources", {}).get("/XObject", {})
                    if "/Outer" in objects:
                        inner = objects["/Outer"]["/Resources"]["/XObject"]["/Inner"]
                        metadata.append(inner["/Metadata"].get_data())
                self.assertIn(safe_payload, metadata)
                validate_release_pdf(output)


if __name__ == "__main__":
    unittest.main()
