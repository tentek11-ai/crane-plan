"""Lossless external PDF assembly and final physical contents for PPRk releases."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import io
import math
import os
import re
from pathlib import Path
import tempfile
from typing import Iterable

from pypdf import PdfReader, PdfWriter

from .pprk_models import CompletenessIssue, ExternalDocument, ReleaseStatus
from .pprk_release_validation import ForbiddenReferenceError, UnsafePDFMetadataError


@dataclass(frozen=True)
class MergeResult:
    output_pdf: Path
    page_count: int
    page_ranges: dict[str, tuple[int, int]]
    issues: tuple[CompletenessIssue, ...] = ()

    @property
    def production_allowed(self) -> bool:
        return not any(issue.blocking for issue in self.issues)


class PPRKMergeError(ValueError):
    """Assembly refused; the previous destination remains untouched."""

    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("; ".join(issue.message for issue in self.issues))


def _issue(code, message, document_id="", blocking=True):
    return CompletenessIssue(code, message, blocking, f"external_documents/{document_id}")


def _fail(code, message, document_id=""):
    raise PPRKMergeError((_issue(code, message, document_id),))


def _aliases(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve() or (left.exists() and right.exists() and os.path.samefile(left, right))


def _read_pdf(path: Path, document_id=""):
    try:
        data = path.read_bytes()
        if path.suffix.lower() != ".pdf" or not data.startswith(b"%PDF-"):
            _fail("PPRK_EXTERNAL_NOT_PDF", f"Не PDF: {path}", document_id)
        reader = PdfReader(io.BytesIO(data), strict=True)
        from .pprk_release_validation import validate_release_inputs, validate_pdf_metadata
        if reader.is_encrypted and not reader.decrypt(""):
            _fail("PPRK_EXTERNAL_ENCRYPTED", f"Нет доступа к зашифрованному PDF: {path}", document_id)
        validate_pdf_metadata(reader)
        if not reader.pages:
            _fail("PPRK_EXTERNAL_EMPTY", f"PDF не содержит страниц: {path}", document_id)
        for page in reader.pages:
            _fingerprint(page)
            validate_release_inputs(page.extract_text())
        return data, reader
    except UnsafePDFMetadataError as error:
        _fail("PPRK_UNSAFE_PDF_METADATA", str(error), document_id)
    except ForbiddenReferenceError as error:
        _fail("PPRK_FORBIDDEN_REFERENCE", str(error), document_id)
    except PPRKMergeError:
        raise
    except Exception as error:
        _fail("PPRK_EXTERNAL_UNREADABLE", f"PDF не читается: {path}: {error}", document_id)


def _fingerprint(page):
    contents = page.get_contents()
    return (tuple(page.mediabox), tuple(page.cropbox), page.get("/Rotate"), page.get("/UserUnit", 1), contents.get_data() if contents else b"", page.extract_text())


def _documents(documents: Iterable[ExternalDocument], protected=()):
    """Validate immutable byte snapshots in caller-supplied canonical order."""
    accepted, issues, seen_ids, seen_paths = [], [], set(), list(protected)
    for document in documents:
        if not document.document_id or document.document_id in seen_ids:
            _fail("PPRK_EXTERNAL_DUPLICATE", "Повторяется ID внешнего документа", document.document_id)
        seen_ids.add(document.document_id)
        source = Path(document.attachment_path) if document.attachment_path else None
        if source and any(_aliases(source, previous) for previous in seen_paths):
            _fail("PPRK_EXTERNAL_ALIAS", f"Повторное включение или совпадение с выходным PDF: {source}", document.document_id)
        if source:
            seen_paths.append(source)
        # Inspect an existing selected source even if its presence/verification
        # flag would otherwise hide it behind an ordinary pending issue.
        captured = None
        if source and source.is_file():
            try:
                captured = _read_pdf(source, document.document_id)
            except PPRKMergeError as error:
                unsafe = any(issue.code in {"PPRK_UNSAFE_PDF_METADATA", "PPRK_FORBIDDEN_REFERENCE"}
                             for issue in error.issues)
                # Unsafe evidence always wins. Ordinary file errors retain the
                # existing presence/verification diagnostic priority below.
                if unsafe or (document.present and document.verification_status == "VERIFIED"):
                    raise
        if not document.present or source is None or not source.exists():
            # A false presence flag must never silently discard an existing attachment.
            if not document.present and source and source.exists():
                _fail("PPRK_EXTERNAL_PATH_MISMATCH", f"PDF существует, но документ отмечен отсутствующим: {source}", document.document_id)
            issues.append(_issue("PPRK_EXTERNAL_MISSING", f"ОЖИДАЕТ ВКЛЮЧЕНИЯ: {document.title} ({document.document_id})", document.document_id, document.required))
            continue
        if document.verification_status != "VERIFIED":
            _fail("PPRK_EXTERNAL_UNVERIFIED", f"Внешний PDF не проверен: {document.title}", document.document_id)
        data, reader = captured if captured is not None else _read_pdf(source, document.document_id)
        if hashlib.sha256(data).hexdigest() != document.verified_sha256:
            _fail("PPRK_EXTERNAL_REVISION_CHANGED",
                  f"Ревизия PDF не подтверждена. Требуется повторная проверка: {document.title}", document.document_id)
        accepted.append((document, source, data, reader))
    return accepted, tuple(issues)


def verify_external_revision(document: ExternalDocument) -> ExternalDocument:
    """Record the exact readable PDF revision explicitly confirmed by the user."""
    if not document.present or not document.attachment_path:
        _fail("PPRK_EXTERNAL_MISSING", "Выберите локальный PDF и подтвердите его наличие.", document.document_id)
    data, _ = _read_pdf(Path(document.attachment_path), document.document_id)
    return replace(document, verification_status="VERIFIED", verified_sha256=hashlib.sha256(data).hexdigest())


def inspect_external_document(document: ExternalDocument) -> tuple[CompletenessIssue, ...]:
    """Preflight a selected local PDF using the same checks as final assembly."""
    try:
        _, issues = _documents((document,))
        return issues
    except PPRKMergeError as error:
        return error.issues


def _unchanged(snapshots):
    for source, original in snapshots:
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(original).digest():
            _fail("PPRK_EXTERNAL_SOURCE_CHANGED", f"Исходный PDF изменился во время сборки: {source}")


def merge_pprk_documents(main_pdf, external_documents, output_pdf) -> MergeResult:
    """Append verified PDFs, verify a reopened staging file, then replace atomically.

    Missing inputs return scoped issues and consume no pages. Malformed or
    ambiguous inputs raise PPRKMergeError. Input byte streams are never written.
    """
    main, output = Path(main_pdf), Path(output_pdf)
    if _aliases(main, output):
        _fail("PPRK_EXTERNAL_ALIAS", "Итоговый PDF совпадает с основным исходным PDF")
    accepted, issues = _documents(external_documents, (main, output))
    main_bytes, main_reader = _read_pdf(main)
    writer = PdfWriter()
    expected, ranges = [], {}
    snapshots = [(main, main_bytes)]
    for page in main_reader.pages:
        expected.append(_fingerprint(page))
        writer.add_page(page)
    for document, source, data, reader in accepted:
        start = len(expected) + 1
        for page in reader.pages:
            expected.append(_fingerprint(page))
            writer.add_page(page)
        ranges[document.document_id] = (start, len(expected))
        snapshots.append((source, data))
    temporary = None
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".merge.tmp.pdf", delete=False) as stream:
            temporary = Path(stream.name)
            writer.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        _, reopened = _read_pdf(temporary)
        if len(reopened.pages) != len(expected) or [_fingerprint(page) for page in reopened.pages] != expected:
            _fail("PPRK_EXTERNAL_VERIFY_FAILED", "Итоговый PDF нарушает порядок, геометрию или содержимое страниц")
        _unchanged(snapshots)
        os.replace(temporary, output)
    except PPRKMergeError:
        raise
    except Exception as error:
        _fail("PPRK_EXTERNAL_WRITE_FAILED", f"Не удалось атомарно собрать ППРк: {error}")
    finally:
        writer.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return MergeResult(output, len(expected), ranges, issues)


def _canonical_documents(bundle, records):
    by_id = {}
    for record in records:
        if record.document_id in by_id:
            _fail("PPRK_EXTERNAL_DUPLICATE", "Повторяется ID в реестре выпуска", record.document_id)
        by_id[record.document_id] = record
    ordered = []
    external_started = False
    for part in bundle.parts:
        if part.kind != "external":
            if external_started:
                _fail("PPRK_EXTERNAL_ORDER_MISMATCH", "Внешние PDF должны завершать канонический состав")
            continue
        external_started = True
        document_id = part.part_id.removeprefix("external.")
        document = by_id.pop(document_id, None)
        if document is None:
            _fail("PPRK_EXTERNAL_PATH_MISMATCH", "Внешняя часть отсутствует в сохраненном реестре выпуска", document_id)
        paths = [dict(sheet.fields).get("attachment_path", "") for sheet in part.sheets]
        if not paths or any(not path or not document.attachment_path or not _aliases(Path(path), Path(document.attachment_path)) for path in paths):
            _fail("PPRK_EXTERNAL_PATH_MISMATCH", "Путь внешнего документа отличается от составленного комплекта", document_id)
        ordered.append(document)
    for document in by_id.values():
        if document.present:
            _fail("PPRK_EXTERNAL_ORDER_MISMATCH", "Присутствующий PDF отсутствует в каноническом составе", document.document_id)
        ordered.append(document)
    return tuple(ordered)


def _range_label(start, end):
    return f"стр. {start}" if start == end else f"стр. {start}–{end}"


def _reference_overrides(documents, accepted, first_page):
    overrides, cursor = {}, first_page
    counts = {doc.document_id: len(reader.pages) for doc, _, _, reader in accepted}
    for document in documents:
        key = f"external.{document.document_id}"
        if document.document_id in counts:
            label = _range_label(cursor, cursor + counts[document.document_id] - 1)
            cursor += counts[document.document_id]
        else:
            label = f"ОЖИДАЕТ ВКЛЮЧЕНИЯ: {document.title}"
        overrides[key] = label
        overrides[f"appendix.{document.document_id.upper()}"] = label
    return overrides


def external_document_issues(bundle):
    """Known composer issues requiring a pending register even without records."""
    return tuple(issue for issue in bundle.completeness_issues if issue.code in {
        "PPRK_TIE_PROJECT_REQUIRED", "PPRK_EXTERNAL_DOCUMENT_REQUIRED",
    })


def _implicit_pending_rows(bundle, documents):
    configured = {document.document_id for document in documents}
    rows = {}
    for issue in sorted(external_document_issues(bundle), key=lambda item: (item.field_id, item.code, item.message)):
        document_id = issue.field_id.removeprefix("external_documents/")
        if not document_id or document_id == issue.field_id:
            document_id = "tie_in_project" if issue.code == "PPRK_TIE_PROJECT_REQUIRED" else "external_document"
        if document_id not in configured:
            rows.setdefault(document_id, []).append(issue.message)
    return tuple((document_id, "; ".join(dict.fromkeys(messages))) for document_id, messages in rows.items())


def _with_register(bundle, documents, overrides, issues):
    from .pprk_composer import PPRKDocumentPart, PPRKSheet, PPRKContentsEntry
    register_id = "section.external_register"
    if not documents and not _implicit_pending_rows(bundle, documents):
        return bundle
    paragraphs = []
    for document in documents:
        paragraphs.append(
            f"{document.document_id} — {document.title}\n"
            f"Номер: {document.number or 'не заполнено'}; дата: {document.date or 'не заполнено'}; "
            f"организация: {document.organization or 'не заполнено'}; проверка: {document.verification_status}; "
            f"{overrides.get('external.' + document.document_id, 'ОЖИДАЕТ ВКЛЮЧЕНИЯ')}"
        )
    for document_id, message in _implicit_pending_rows(bundle, documents):
        paragraphs.append(f"ОЖИДАЕТ ВКЛЮЧЕНИЯ: {document_id} — {message}")
    register = PPRKDocumentPart(register_id, "Реестр внешних документов", "note", (PPRKSheet(register_id, "Реестр внешних документов", "note"),), rendered_text="\n\n".join(paragraphs))
    parts = list(bundle.parts)
    insert = next((index for index, part in enumerate(parts) if part.kind not in ("service", "note")), len(parts))
    parts.insert(insert, register)
    contents = (*bundle.contents, PPRKContentsEntry(register_id, register_id, register.title, "", "note"))
    return replace(bundle, parts=tuple(parts), contents=contents, completeness_issues=(*bundle.completeness_issues, *issues), production_allowed=bundle.production_allowed and not any(i.blocking for i in issues))


def _contents_count(main_count, external_count):
    # Page 4 is replaced; continuation leaves follow generated parts, before imports.
    extra = 0
    while True:
        needed = max(0, math.ceil((main_count + external_count + extra) / 30) - 1)
        if needed == extra:
            return extra
        extra = needed


def external_contents_titles(document, page_count):
    """Shared complete strings for preparation and final physical contents."""
    return tuple(f"{document.title} / {document.document_id} / лист {index}"
                 for index in range(1, page_count + 1))


def _finalize_contents(main, accepted, extra, output, bundle, document_status=None):
    """List each physical page exactly once, including note continuations."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas
    from .pprk_text_report import _frame, _draw_cell_text, _font
    from reportlab.lib.units import mm
    reader = PdfReader(main)
    titles = []
    current_note = ""
    note_titles = [part.title for part in bundle.parts if part.kind == "note"]
    for index, page in enumerate(reader.pages, 1):
        lines = [line.strip() for line in page.extract_text().splitlines() if line.strip()]
        title = next((line for line in lines if line != "ППРк" and not line.startswith("Лист ")), f"Лист ППРк {index}")
        if index <= 4:
            title = bundle.parts[index - 1].title
        elif lines[:2] == ["ППРк", f"Лист {index}"]:
            compact = "".join(page.extract_text().split())
            heading = next((name for name in note_titles if "".join(name.split()) in compact), None)
            if heading:
                current_note = heading
                title = heading
            elif current_note:
                title = current_note + " / продолжение"
        if index > 4 and lines[:1] != ["ППРк"]:
            designation = re.search(r"ГЧ-\d+(?:\.\d+)?", page.extract_text())
            if designation and designation.group() not in title:
                title += " / " + designation.group()
        titles.append(title)
    titles[3] = "Состав проекта / итоговый"
    titles.extend("Состав проекта / продолжение" for _ in range(extra))
    for document, _, _, source in accepted:
        titles.extend(external_contents_titles(document, len(source.pages)))
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    total = len(titles)
    for page_index in range(extra + 1):
        physical = 4 if page_index == 0 else len(reader.pages) + page_index
        _frame(canvas, physical)
        canvas.setFont(_font(), 11)
        canvas.drawCentredString(A4[0] / 2, A4[1] - 22 * mm, "СОСТАВ ПРОЕКТА / ИТОГОВЫЙ")
        y = A4[1] - 35 * mm
        for index in range(page_index * 30, min((page_index + 1) * 30, total)):
            canvas.rect(24 * mm, y - 7 * mm, 160 * mm, 7 * mm)
            _draw_cell_text(canvas, titles[index], 25 * mm, y - 7 * mm, 138 * mm, 7 * mm, font_size=7)
            _draw_cell_text(canvas, f"стр. {index + 1}", 165 * mm, y - 7 * mm, 18 * mm, 7 * mm, font_size=8)
            y -= 7 * mm
        canvas.showPage()
    canvas.save()
    if document_status:
        from .report import _apply_document_status
        contents_path = Path(output).with_name("contents-status.pdf")
        contents_path.write_bytes(buffer.getvalue())
        _apply_document_status(contents_path, document_status)
        buffer = io.BytesIO(contents_path.read_bytes())
    contents = PdfReader(buffer)
    writer = PdfWriter()
    for index, page in enumerate(reader.pages):
        writer.add_page(contents.pages[0] if index == 3 else page)
    for page in contents.pages[1:]:
        writer.add_page(page)
    with output.open("wb") as stream:
        writer.write(stream)
    writer.close()


def assemble_pprk_report(output, project, bundle, render_main, *, document_status=None):
    """Render and finalize in isolation; publish only a verified full assembly."""
    output = Path(output)
    documents = _canonical_documents(bundle, project.pprk_release.external_documents)
    required_ids = set(bundle.required_external_document_ids)
    documents = tuple(replace(document, required=document.required or document.document_id in required_ids)
                      for document in documents)
    if bundle.requested_status in (ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION):
        missing = required_ids - {document.document_id for document in documents}
        if missing:
            _fail("PPRK_EXTERNAL_MISSING", "ОЖИДАЕТ ВКЛЮЧЕНИЯ: " + ", ".join(sorted(missing)))
    accepted, issues = _documents(documents, (output,))
    if bundle.requested_status in (ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION) and any(issue.blocking for issue in issues):
        raise PPRKMergeError(issues)
    snapshots = [(source, data) for _, source, data, _ in accepted]
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".pprk-assembly-") as directory:
        main = Path(directory) / "main.pdf"
        overrides = _reference_overrides(documents, accepted, 1)
        last_layout = None
        for _ in range(8):
            prepared = _with_register(bundle, documents, overrides, issues)
            render_main(main, prepared, overrides)
            count = len(PdfReader(main).pages)
            extra = _contents_count(count, sum(len(reader.pages) for _, _, _, reader in accepted))
            updated = _reference_overrides(documents, accepted, count + extra + 1)
            layout = (count, extra, updated)
            if layout == last_layout:
                break
            overrides, last_layout = updated, layout
        else:
            _fail("PPRK_EXTERNAL_MAP_UNSTABLE", "Карта страниц внешних документов не стабилизировалась")
        finalized = Path(directory) / "finalized.pdf"
        _finalize_contents(main, accepted, extra, finalized, prepared, document_status)
        _unchanged(snapshots)
        staged = Path(directory) / "assembled.pdf"
        result = merge_pprk_documents(finalized, documents, staged)
        for document, _, _, _ in accepted:
            start, end = result.page_ranges[document.document_id]
            if overrides[f"external.{document.document_id}"] != _range_label(start, end):
                # This invariant is determined before publication by identical snapshots/counts.
                raise AssertionError("Нарушена итоговая карта внешних страниц")
        _unchanged(snapshots)
        from .pprk_release_validation import validate_release_pdf
        validate_release_pdf(staged)
        try:
            os.replace(staged, output)
        except OSError as error:
            _fail("PPRK_EXTERNAL_WRITE_FAILED", f"Не удалось опубликовать итоговый ППРк: {error}")
        return replace(result, output_pdf=output)
