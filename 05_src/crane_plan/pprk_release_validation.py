"""Fail-closed validation of reference identities at release boundaries."""
from dataclasses import fields, is_dataclass
from enum import Enum
from collections.abc import Mapping
from copy import deepcopy
from io import BytesIO, StringIO
from pathlib import Path
import codecs
import re
import unicodedata
import xml.etree.ElementTree as ET

from pypdf import PdfReader
from pypdf.generic import IndirectObject
from .pprk_assets import FORBIDDEN_STRINGS


FORBIDDEN_RELEASE_STRINGS = (*FORBIDDEN_STRINGS, "Тружеников", "Труженников",
    "Хамовник", "AC-TRZ", "АрхиКом", "F:/работа/аспирантура/апробация")


class ForbiddenReferenceError(ValueError):
    pass


class UnsafePDFMetadataError(ForbiddenReferenceError):
    """Unsafe XML is fatal source evidence, including in preliminary releases."""


def _normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKC", value).casefold().replace("\\", "/")
                   if not c.isspace() and unicodedata.category(c) not in {"Cc", "Cf"})


def validate_release_inputs(*values):
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, Enum):
            yield from strings(value.value)
        elif is_dataclass(value):
            for field in fields(value):
                yield from strings(getattr(value, field.name))
        elif isinstance(value, Mapping):
            for key, item in value.items():
                yield from strings(key)
                yield from strings(item)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                yield from strings(item)
    tokens = tuple(_normalized(s) for s in FORBIDDEN_RELEASE_STRINGS)
    for value in values:
        for text in strings(value):
            normalized = _normalized(text)
            if any(token in normalized for token in tokens):
                raise ForbiddenReferenceError("Запрещённые реквизиты или путь исходного reference обнаружены в выпуске.")


def validate_release_pdf(path):
    """Reopen the physical PDF before any destination or sidecar is replaced."""
    reader = PdfReader(path)
    validate_pdf_metadata(reader)
    for page in reader.pages:
        validate_release_inputs(page.extract_text())


def validate_pdf_page(page):
    _validate_metadata_graph(page)
    validate_release_inputs(page.extract_text())


def validate_underlays(project):
    """Inspect vector text/XMP before rasterization can remove the text layer."""
    for source in (project.source_plan_pdf, project.source_section_pdf):
        if source and Path(source).is_file():
            validate_release_pdf(source)


def snapshot_underlays(project, directory):
    """Validate one immutable read, then render only controlled copies of it."""
    snapshot = deepcopy(project)
    captured = {}
    for kind in ("plan", "section"):
        source = getattr(project, f"source_{kind}_pdf")
        # Absence is part of the snapshot too. Never retain a mutable path
        # which could start resolving to unvalidated bytes after capture.
        setattr(snapshot, f"source_{kind}_pdf", "")
        if not source or not Path(source).is_file():
            continue
        path = Path(source)
        key = path.resolve()
        if key not in captured:
            data = path.read_bytes()
            validate_release_pdf(BytesIO(data))
            captured[key] = data
        destination = Path(directory) / kind / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(captured[key])
        setattr(snapshot, f"source_{kind}_pdf", str(destination))
    return snapshot


def _metadata_xml_text(data):
    """Decode to Unicode and reject declarations before reaching any XML parser."""
    # ASCII declaration characters in UTF-16/32 retain their order after NUL
    # removal. This check also covers a misleading/malformed encoding label.
    raw = data.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise UnsafePDFMetadataError("Небезопасные XML-метаданные PDF: DTD/ENTITY не допускается")
    encoding, offset = None, 0
    for bom, candidate in ((b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
                           (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"),
                           (b"\xef\xbb\xbf", "utf-8")):
        if data.startswith(bom):
            encoding, offset = candidate, len(bom)
            break
    body = data[offset:]
    prefix = body[:4]
    leading = {9, 10, 13, 32, 60}  # XML whitespace or '<'
    if encoding is None and len(prefix) == 4:
        if prefix[0] in leading and prefix[1:] == b"\x00\x00\x00":
            encoding = "utf-32-le"
        elif prefix[:3] == b"\x00\x00\x00" and prefix[3] in leading:
            encoding = "utf-32-be"
        elif prefix[0] in leading and prefix[1] == 0 and prefix[3] == 0:
            encoding = "utf-16-le"
        elif prefix[0] == 0 and prefix[1] in leading and prefix[2] == 0:
            encoding = "utf-16-be"
    declaration = re.match(br"\s*<\?xml\b[^>]*?\bencoding\s*=\s*['\"]([A-Za-z][A-Za-z0-9._-]*)['\"]",
                           body.replace(b"\x00", b""), re.IGNORECASE)
    declared = codecs.lookup(declaration[1].decode("ascii")).name if declaration else None
    if encoding and declared:
        compatible = {encoding}
        if encoding.startswith("utf-16-"):
            compatible.add("utf-16")
        elif encoding.startswith("utf-32-"):
            compatible.add("utf-32")
        elif encoding == "utf-8":
            compatible.add("utf-8-sig")
        if declared not in compatible:
            raise UnsafePDFMetadataError("Противоречащие кодировки XML-метаданных PDF")
    text = body.decode(encoding or declared or "utf-8")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise UnsafePDFMetadataError("Небезопасные XML-метаданные PDF: DTD/ENTITY не допускается")
    return text


def _validate_metadata_stream(metadata):
    if metadata is not None:
        try:
            data = metadata.get_object().get_data()
            text = _metadata_xml_text(data)
            validate_release_inputs(text)
            # The parser sees only the decoded, declaration-checked Unicode;
            # it must not independently reinterpret the original byte encoding.
            with StringIO(text) as source:
                parsed = ET.iterparse(source, events=("start", "start-ns"))
                for event, value in parsed:
                    if event == "start-ns":
                        # ElementTree removes xmlns attributes; declarations,
                        # including unused ones, need their own decoded event.
                        validate_release_inputs(value)
                    else:
                        validate_release_inputs(value.tag, tuple(value.attrib.items()))
                validate_release_inputs("".join(parsed.root.itertext()))
        except ForbiddenReferenceError:
            raise
        except Exception as error:
            raise UnsafePDFMetadataError("Небезопасные или некорректные XML-метаданные PDF") from error


def _validate_metadata_graph(root):
    """Visit reachable dictionaries/resources once, including cyclic Form graphs."""
    pending, indirect_seen, direct_seen = [root], set(), set()
    while pending:
        value = pending.pop()
        if isinstance(value, IndirectObject):
            key = (id(value.pdf), value.idnum, value.generation)
            if key in indirect_seen:
                continue
            indirect_seen.add(key)
            value = value.get_object()
        if isinstance(value, Mapping):
            if id(value) in direct_seen:
                continue
            direct_seen.add(id(value))
            if value.get("/Type") == "/Metadata" or value.get("/Subtype") == "/XML":
                _validate_metadata_stream(value)
            for key, item in value.items():
                if key == "/Metadata":
                    _validate_metadata_stream(item)
                pending.append(item)
        elif isinstance(value, (list, tuple)):
            if id(value) not in direct_seen:
                direct_seen.add(id(value))
                pending.extend(value)


def validate_pdf_metadata(reader):
    validate_release_inputs(dict(reader.metadata or {}))
    _validate_metadata_graph(reader.trailer)

