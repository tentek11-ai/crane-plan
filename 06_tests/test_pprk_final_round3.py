"""Release boundaries: float noise, immutable sources and recursive unsafe XMP."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject
from reportlab.pdfgen.canvas import Canvas

import test_pprk_final_round2 as round2
from test_full_pprk_end_to_end import verify, save_via_gui, external_fixture
from crane_plan.pdf_workspace import render_page
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_models import ExternalDocument, ReleaseStatus
from crane_plan.pprk_release_validation import ForbiddenReferenceError, validate_release_pdf
from crane_plan.pprk_release_workflow import prepare_release, require_saveable_release
from crane_plan.report import generate_report


def metadata_pdf(path, payload, target="page"):
    """Real nested Form resources, with an unused back-edge to test cycle safety."""
    writer = PdfWriter()
    page = writer.add_blank_page(600, 600)
    metadata = DecodedStreamObject()
    metadata.set_data(payload)
    metadata.update({NameObject("/Type"): NameObject("/Metadata"), NameObject("/Subtype"): NameObject("/XML")})
    metadata_ref = writer._add_object(metadata)
    inner = DecodedStreamObject(); inner.set_data(b"")
    outer = DecodedStreamObject(); outer.set_data(b"/Inner Do")
    for form in (inner, outer):
        form.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
                     NameObject("/BBox"): ArrayObject([NumberObject(n) for n in (0, 0, 600, 600)])})
    inner_ref, outer_ref = writer._add_object(inner), writer._add_object(outer)
    outer[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/Inner"): inner_ref})})
    inner[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/Back"): outer_ref})})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/Outer"): outer_ref})})
    content = DecodedStreamObject(); content.set_data(b"/Outer Do")
    page[NameObject("/Contents")] = writer._add_object(content)
    (page if target == "page" else inner)[NameObject("/Metadata")] = metadata_ref
    with Path(path).open("wb") as stream:
        writer.write(stream)
    return Path(path)


def attach(project, source):
    project.pprk_release.external_documents.append(ExternalDocument("round3", "Проверяемое приложение", present=True,
        verification_status="VERIFIED", attachment_path=str(source),
        verified_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))


def underlay(path, poisoned=False):
    canvas = Canvas(str(path), pagesize=(600, 600), invariant=1)
    if poisoned:
        canvas.rect(0, 0, 600, 600, fill=1, stroke=0)
        canvas.setFillColorRGB(1, 1, 1)
        canvas.drawString(100, 300, "27.06-23")
    else:
        canvas.rect(40, 40, 30, 20, fill=0)
        canvas.drawString(40, 80, "CLEAN UNDERLAY")
    canvas.showPage(); canvas.save()
    return Path(path)


def calibrated(project, kind, source):
    setattr(project, f"source_{kind}_pdf", str(source))
    setattr(project, f"{kind}_m_per_pixel", .5)
    setattr(project, f"{kind}_origin_x_px", 300)
    setattr(project, f"{kind}_origin_y_px", 500)
    setattr(project, f"{kind}_render_scale", 1)
    setattr(project, f"{kind}_background_intensity", .35)


def race_after_staging(root, source, replacement, operation, prior_output=None):
    """Independent real thread, no patched validation/rendering or timing hook."""
    stop, swapped = threading.Event(), threading.Event()
    errors = []
    def replace_when_staged():
        deadline = time.monotonic() + 30
        while not stop.is_set() and time.monotonic() < deadline:
            try:
                ready = any(p.is_dir() and p.name.startswith((".pprk-legacy-", ".pprk-assembly-"))
                            for p in root.rglob("*"))
                if ready:
                    if prior_output is not None and prior_output.read_bytes() != b"previous":
                        raise AssertionError("Prior destination changed before final publication")
                    replacement.replace(source)
                    swapped.set()
                    return
            except (FileNotFoundError, PermissionError):
                pass
            except Exception as exc:
                errors.append(exc)
                return
            time.sleep(.0005)
    thread = threading.Thread(target=replace_when_staged, daemon=True)
    thread.start()
    try:
        return operation()
    finally:
        stop.set(); thread.join(3)
        if errors:
            raise errors[0]
        if not swapped.is_set():
            raise AssertionError("Independent source replacement did not observe staging")


class Round3Tests(unittest.TestCase):
    assert_gui_atomic_rejection = round2.Round2Tests.assert_gui_atomic_rejection

    def test_float_representation_noise_at_exact_clearance_passes_gui_and_legacy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (low, high) in enumerate(((30.8, 30.8 + 3), (31.3, 34.3), (61.1, 64.1))):
                with self.subTest(levels=(low, high)):
                    project, scenario = round2.ready(root / f"fixture-{index}")
                    scenario.placements[0].jib_level_m = low
                    scenario.placements[1].jib_level_m = high
                    scenario.joint_plan.vertical_separation_m = 3
                    checked = verify(project, scenario)
                    release = prepare_release(project, scenario, checked)
                    require_saveable_release(release, checked)
                    gui = save_via_gui(project, scenario, checked, root / f"gui-{index}")
                    legacy = generate_report(root / f"legacy-{index}.pdf", project, [scenario])
                    for path in (gui, legacy):
                        sections = [p.extract_text() for p in PdfReader(path).pages if p.extract_text().startswith("ВЫСОТНАЯ ПРИВЯЗКА")]
                        self.assertEqual(len(sections), 1)
                        self.assertIn("чистый зазор 1.0 м", sections[0])

    def test_real_subminimum_gap_remains_fatal_gui_and_legacy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, scenario = round2.ready(root / "fixture")
            scenario.placements[0].jib_level_m = 30.8
            scenario.placements[1].jib_level_m = 30.8 + 2.9995
            scenario.joint_plan.vertical_separation_m = 2.9995
            checked = verify(project, scenario)
            self.assert_gui_atomic_rejection(project, scenario, checked, root / "gui")
            output = root / "legacy.pdf"; output.write_bytes(b"previous")
            with self.assertRaisesRegex(ValueError, "Недостаточный вертикальный зазор"):
                generate_report(output, project, [scenario])
            self.assertEqual(output.read_bytes(), b"previous")

    def test_independent_path_replacement_cannot_change_bundle_or_legacy_underlay_pixels(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kind in ("plan", "section"):
                for bundled in (False, True):
                    with self.subTest(kind=kind, bundled=bundled):
                        directory = root / f"{kind}-{bundled}"; directory.mkdir()
                        project, scenario = round2.ready(directory / "fixture")
                        source = underlay(directory / "neutral.pdf")
                        poison = underlay(directory / "replacement.pdf", True)
                        expected = render_page(source, 0, 1, background_intensity=.35)
                        calibrated(project, kind, source)
                        bundle = prepare_release(project, scenario, verify(project, scenario)).bundle if bundled else None
                        output = directory / "report.pdf"; output.write_bytes(b"previous")
                        race_after_staging(directory, source, poison,
                            lambda: generate_report(output, project, [scenario], bundle=bundle), output)
                        self.assertIn("27.06-23", PdfReader(source).pages[0].extract_text())
                        title = "СТРОЙГЕНПЛАН." if kind == "plan" else "ВЫСОТНАЯ ПРИВЯЗКА."
                        page = next(p for p in PdfReader(output).pages if p.extract_text().startswith(title))
                        self.assertTrue(any(im.image.size == expected.size and im.image.convert("RGB").tobytes() == expected.tobytes()
                                            for im in page.images), "Rendered bytes differ from the validated clean source")

    def test_gui_race_keeps_both_previous_outputs_and_sidecars_for_each_underlay(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kind in ("plan", "section"):
                with self.subTest(kind=kind):
                    directory = root / kind; directory.mkdir()
                    project, scenario = round2.ready(directory / "fixture")
                    source = underlay(directory / "neutral.pdf")
                    poison = underlay(directory / "replacement.pdf", True)
                    calibrated(project, kind, source)
                    checked = verify(project, scenario)
                    race_after_staging(directory, source, poison,
                        lambda: self.assert_gui_atomic_rejection(project, scenario, checked, directory))

    def test_every_rigging_text_field_rejects_normalized_semantic_sentinels(self):
        with TemporaryDirectory() as tmp:
            project, scenario = round2.ready(Path(tmp) / "fixture")
            checked = verify(project, scenario)
            for field in ("rigging_type", "sling_identification", "rigging_evidence"):
                for sentinel in ("НЕ ЗАПОЛНЕНО", "ОТСУТСТВУЕТ", "НЕТ", "НЕ ПРИМЕНИМО", "НЕ ПРОВЕРЕНО", "УТОЧНИТЬ"):
                    for value in (sentinel, f" ⟦{sentinel.lower()}⟧ \u200b", ".".join(sentinel.lower())):
                        with self.subTest(field=field, value=value):
                            changed = deepcopy(project); setattr(changed.loads[0], field, value)
                            self.assertFalse(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed)

    def test_semantic_sentinels_remain_pending_in_physical_gui_card_and_block_production(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for field, value in (("rigging_type", "ОТСУТСТВУЕТ"), ("sling_identification", "НЕ ПРИМЕНИМО"), ("rigging_evidence", "НЕ ПРОВЕРЕНО")):
                with self.subTest(field=field):
                    project, scenario = round2.ready(root / field / "fixture")
                    setattr(project.loads[0], field, value)
                    checked = verify(project, scenario)
                    output = save_via_gui(project, scenario, checked, root / field / "draft")
                    cards = [p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:")]
                    self.assertIn("НЕ ПОДТВЕРЖДЕНО", cards[0])
                    project.pprk_release.status = ReleaseStatus.PRODUCTION
                    self.assert_gui_atomic_rejection(project, scenario, checked, root / field / "production")

    def test_nested_form_metadata_entities_are_fatal_for_external_and_both_underlays(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for target, payload in (("page", b'<x value="27.06&#45;23"/>'), ("form", b'<x>27.06&#x2D;23</x>')):
                source = metadata_pdf(root / f"{target}.pdf", payload, target)
                with self.subTest(target=target, boundary="physical"):
                    with self.assertRaises(ForbiddenReferenceError): validate_release_pdf(source)
                for kind in ("external", "plan", "section"):
                    with self.subTest(target=target, boundary=kind):
                        project, scenario = round2.ready(root / f"{target}-{kind}" / "fixture")
                        if kind == "external": attach(project, source)
                        else: calibrated(project, kind, source)
                        self.assert_gui_atomic_rejection(project, scenario, verify(project, scenario), root / f"{target}-{kind}" / "gui")
                        if kind != "external":
                            output = root / f"{target}-{kind}-legacy.pdf"; output.write_bytes(b"previous")
                            with self.assertRaises(ForbiddenReferenceError): generate_report(output, project, [scenario])
                            self.assertEqual(output.read_bytes(), b"previous")

    def test_unsafe_xml_is_fatal_for_every_status_including_a_prepared_release(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payloads = (b'<!DOCTYPE x [<!ENTITY harmless "hello">]><x>&harmless;</x>', b'<x>malformed')
            for target in ("page", "form"):
                for index, payload in enumerate(payloads):
                    for status in ReleaseStatus:
                        with self.subTest(target=target, payload=index, status=status):
                            directory = root / f"{target}-{index}-{status.value}"
                            project, scenario = round2.ready(directory / "fixture")
                            source = external_fixture(directory / "neutral.pdf", ("CLEAN",))
                            attach(project, source); project.pprk_release.status = status
                            checked = verify(project, scenario)
                            prepared = prepare_release(project, scenario, checked)
                            metadata_pdf(source, payload, target)
                            caught = None
                            try: require_saveable_release(prepared, checked)
                            except ValueError as exc: caught = exc
                            self.assertIsInstance(caught, ForbiddenReferenceError, "Unsafe metadata must be fatal independently of ordinary status blockers")
                    with self.subTest(target=target, payload=index, boundary="public"):
                        project, scenario = round2.ready(root / f"unsafe-{target}-{index}" / "fixture")
                        source = metadata_pdf(root / f"unsafe-{target}-{index}.pdf", payload, target)
                        attach(project, source)
                        self.assert_gui_atomic_rejection(project, scenario, verify(project, scenario), root / f"unsafe-{target}-{index}" / "gui")

    def test_safe_cyclic_form_metadata_still_publishes_a_physical_external_page(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, scenario = round2.ready(root / "fixture")
            source = metadata_pdf(root / "safe.pdf", b'<x value="safe">hello&#x20;world</x>', "form")
            validate_release_pdf(source); attach(project, source)
            output = save_via_gui(project, scenario, verify(project, scenario), root / "gui")
            self.assertTrue(any("round3 / лист 1" in p.extract_text() for p in PdfReader(output).pages))
            validate_release_pdf(output)

    def test_unsafe_xml_cannot_hide_behind_unverified_or_false_presence_flags(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for target in ("page", "form"):
                for index, (present, status) in enumerate(((False, "VERIFIED"), (True, "UNVERIFIED"), (False, "UNVERIFIED"))):
                    with self.subTest(target=target, present=present, status=status):
                        project, scenario = round2.ready(root / f"{target}-{index}" / "fixture")
                        source = metadata_pdf(root / f"{target}-{index}.pdf", b'<!DOCTYPE x [<!ENTITY a "safe">]><x>&a;</x>', target)
                        attach(project, source)
                        project.pprk_release.external_documents[-1].present = present
                        project.pprk_release.external_documents[-1].verification_status = status
                        checked = verify(project, scenario)
                        with self.assertRaises(ForbiddenReferenceError): prepare_release(project, scenario, checked)
                        self.assert_gui_atomic_rejection(project, scenario, checked, root / f"{target}-{index}" / "gui")


if __name__ == "__main__":
    unittest.main()
