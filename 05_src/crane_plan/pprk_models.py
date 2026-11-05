"""Data model for a complete, editable PPRk release configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date as CalendarDate
from enum import Enum
import unicodedata
import re
from typing import Any, Callable, TypeVar


class ReleaseStatus(str, Enum):
    PRELIMINARY = "PRELIMINARY"
    REVIEW = "REVIEW"
    COORDINATION = "COORDINATION"
    APPROVED = "APPROVED"
    PRODUCTION = "PRODUCTION"


@dataclass
class ApprovalSlot:
    organization: str = ""
    position: str = ""
    full_name: str = ""
    signature: str = ""
    date: str = ""
    role: str = ""


_EVIDENCE_LABELS = ("типоснастки", "тип", "номерстропа", "номер", "паспорт", "строп", "документ", "passport")
_EVIDENCE_SEPARATOR = r"[\W_]*"
_WORD_START, _WORD_END = r"(?<![^\W_])", r"(?![^\W_])"



def _evidence_phrase_pattern(value):
    return _EVIDENCE_SEPARATOR.join(re.escape(char) for char in value)


_EVIDENCE_SENTINEL_PATTERN = re.compile(
    _WORD_START + r"(?:(?:" + "|".join(map(_evidence_phrase_pattern, _EVIDENCE_LABELS)) + ")" + _EVIDENCE_SEPARATOR + r")?(?:"
    # Russian stems accept case/gender endings without enumerating suffixes.
    # Boundaries keep these phrases out of unrelated identifiers.
    + "|".join(_evidence_phrase_pattern(stem) + r"[а-я]*" for stem in (
        "отсутств", "незаполнен", "неуказан", "неподтвержден", "непроверен", "неприменим", "непредоставлен",
        "ожида", "уточня", "уточнени", "подлежитуточнени", "требуется"))
    + "|" + "|".join(map(_evidence_phrase_pattern, (
        "нд", "na", "none", "null", "tbd", "pending", "unknown", "unverified", "notfilled", "notspecified",
        "notprovided", "notapplicable", "notverified", "нетданных", "нетсведений", "уточнить")))
    + ")" + _WORD_END)

# These statements negate defects, not the existence/verification of evidence.
# Remove only the bounded quality phrase: independent missing references are
# still checked, and the selected field must retain identifying information.
_QUALITY_NOUN = (r"(?:дефект(?:а|у|ом|е|ы|ов|ам|ами|ах)?"
    + r"|(?:замечани|повреждени|нарушени)(?:е|я|ю|ем|и|й|ям|ями|ях)"
    + r"|недостаток|недостатк(?:а|у|ом|е|и|ов|ам|ами|ах))" + _WORD_END)
_QUALITY_GAP = r"[^\w.,:;!?\n]*"
_QUALITY_PREFIX_GAP = r"[^\S\r\n]+"
_ABSENCE_QUALIFIER = r"(?:пока|еще|уже|вообще|совсем|также)"
_QUALITY_ABSENCE_GAP = _QUALITY_GAP + "(?:" + _ABSENCE_QUALIFIER + _QUALITY_GAP + ")*"
_QUALITY_PREFIX_ABSENCE_GAP = _QUALITY_PREFIX_GAP + "(?:" + _ABSENCE_QUALIFIER + _QUALITY_PREFIX_GAP + ")*"
_QUALITY_SUBJECT = r"(?:(?:ни)?каки[а-я]*(?:[\W_]+либо)?" + _QUALITY_GAP + ")?" + _QUALITY_NOUN
_QUALITY_NOUN_LIST = _QUALITY_SUBJECT + r"(?:(?:\s+(?:и|или)\s+|[ \t]*,[ \t]*)" + _QUALITY_SUBJECT + ")*"
_QUALITY_COMMENT_PATTERN = re.compile(_WORD_START + r"(?:"
    + r"нет" + _QUALITY_PREFIX_ABSENCE_GAP + _QUALITY_NOUN_LIST
    + "|" + _QUALITY_NOUN_LIST + _QUALITY_ABSENCE_GAP + r"(?:нет|отсутств[а-я]*)"
    # A leading absence predicate must directly govern its quality subject;
    # punctuation can instead terminate a missing passport/equipment clause.
    + r"|отсутств[а-я]*" + _QUALITY_PREFIX_ABSENCE_GAP + _QUALITY_NOUN_LIST
    + r"|не\s*применим[а-я]*" + _QUALITY_GAP + r"элемент[а-я]*" + _QUALITY_GAP + r"нет"
    + ")" + _WORD_END, re.IGNORECASE)
# Positive identity is role-specific. A non-placeholder remainder is not an
# equipment type, a sling identifier or an identified evidence document.
_DOCUMENT_CASE = r"(?:а|у|ом|е|ы|ов|ам|ами|ах)?"
_DOCUMENT_KIND = r"(?:(?:паспорт|акт|сертификат|протокол)" + _DOCUMENT_CASE + r"|свидетельств(?:о|а|у|ом|е|ам|ами|ах))"
_DOCUMENT_KIND_PATTERN = re.compile(_WORD_START + _DOCUMENT_KIND + _WORD_END, re.IGNORECASE)
_DOCUMENT_TITLE_PATTERN = re.compile(
    r"(?:оснастки|стропа|стропов|испытаний|проверки|соответствия|качества|оборудования|тары|траверсы|захвата"
    + r"|грузозахватных|приспособлений|испытательный|технический|проверенн(?:ый|ая|ое|ые)"
    + r"|уточн[её]нн(?:ый|ая|ое|ые))" + _WORD_END, re.IGNORECASE)
_DOCUMENT_TITLE_WORD_PATTERN = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*" + _WORD_END)
_DOCUMENT_TITLE_SPACE_PATTERN = re.compile(r"[^\S\r\n]*")
_DOCUMENT_TITLE_NOUNS = {
    "genitive": frozenset(("оснастки", "стропа", "стропов", "испытания", "испытаний", "проверки",
        "соответствия", "качества", "оборудования", "тары", "траверсы", "захвата", "приспособлений",
        "приемки", "осмотра", "назначения", "приема", "передачи", "эксплуатации")),
    "prepositional": frozenset(("проверке", "испытаниях", "осмотре", "приемке", "эксплуатации", "соответствии")),
}
_DOCUMENT_TITLE_ADJECTIVE_PATTERN = re.compile(
    r"(?:(?:приемо|канатно|цепно|текстильно|контрольно)-)*(?:"
    + r"испытательн|техническ|проверенн|уточненн|канатн|цепн|текстильн|контрольн|внеочередн"
    + r"|очередн|повторн|визуальн|общ|безопасн|выполненн|периодическ|грузов|грузозахватн"
    + r"|эксплуатационн|сдаточн|(?:одно|двух|трех|четырех|много)ветвев)"
    + r"(?:ый|ий|ая|яя|ое|ее|ые|ие|ого|его|ой|ей|ому|ему|ым|им|ом|ем|ыми|ими|ых|их|ую|юю)")
_DOCUMENT_HEADER_GAP = re.compile(r"[\s:=-]*")
_DOCUMENT_REFERENCE_MARKER = re.compile(
    r"(?:#|рег(?:истрационный)?\s*#|(?:рег(?:истрационный)?\s*)?номер(?=\s|[:=#-]|\d)"
    + r"|(?:no|n|id)(?=\s|[:=#-]|\d)|шифр" + _WORD_END + ")", re.IGNORECASE)
_DOCUMENT_CODE_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-/._][A-Za-zА-Яа-яЁё0-9]+)*(?![\w,/.-])")
_DOCUMENT_CODE_GAP = re.compile(r"[\s:#=-]*")
_DOCUMENT_DATE_PATTERN = re.compile(
    _WORD_START + r"(?:от|дата)(?=\s|[:=]|\d)[\s:=]*"
    + r"(?P<date>[^\s;:!?()\[\]{}]+?)[.,]?(?=$|\s|[;:!?()\[\]{}])",
    re.IGNORECASE)
_DOCUMENT_DATE_VALUE_PATTERN = re.compile(r"(?:\d{1,2}\.\d{1,2}\.\d{4}|\d{4}-\d{1,2}-\d{1,2})")
_RIGGING_CLAUSE_STOP_PATTERN = re.compile(r"[;!?\r\n]+|(?<!\d)[.,]|[.,](?!\d)")
_LEGACY_DOCUMENT_IDENTITY = re.compile(
    r"\s*(?:(?:испытательный|технический)\s+)?(?:паспорт|акт|сертификат|протокол|свидетельство)\s+[1-9]\d*\s*",
    re.IGNORECASE)
_EVIDENCE_TARGET_PATTERN = re.compile(_WORD_START + r"(?:"
    + r"(?:схем|оснастк|строп|документ|ведомост|идентификатор|номер|тип|сведени|данн|подтверждени)[а-я]*"
    + "|" + _DOCUMENT_KIND + ")" + _WORD_END)
_NET_PATTERN = re.compile(_WORD_START + _evidence_phrase_pattern("нет") + _WORD_END)
_ROLE_ABSENCE_PATTERN = re.compile(r"(?<![^\W\d_])" + _evidence_phrase_pattern("нет") + r"(?![^\W\d_])", re.IGNORECASE)
_ABSENCE_FILLER_PATTERN = re.compile(_WORD_START + _ABSENCE_QUALIFIER + _WORD_END)
_ID_TOKEN = r"[A-Za-zА-Яа-яЁё0-9]+(?:[-/.,_][A-Za-zА-Яа-яЁё0-9]+)*"
_ID_TOKEN_PATTERN = re.compile(_ID_TOKEN)
_SLING_IDENTITY_PATTERN = re.compile(
    r"\s*(?:(?P<label>строп(?:а)?|марка|номер(?:\s*стропа)?|идентификатор(?:\s*стропа)?|бирка|инвентарный\s*номер|инв|no)"
    + r"\b\s*[:#=-]?\s*)?(?:#\s*)?(?P<mark>" + _ID_TOKEN + r")(?:\s*#\s*(?P<number>" + _ID_TOKEN + r"))?\s*",
    re.IGNORECASE)
_KNOWN_SLING_FAMILY = r"(?:\d+с[кц]|уск\d*|ст[пк]|вк)"
_TYPE_ADJECTIVE_CASE = r"(?:ый|ая|ое|ые|ого|ой|ому|ым|ом|ыми|ых|ую)"
_EQUIPMENT_TYPE_TERM = (r"(?:канатн|цепн|текстильн|ленточн|круглопрядн|петлев|кольцев)" + _TYPE_ADJECTIVE_CASE
    + r"|траверс(?:а|ы|у|ой|е|ам|ами|ах)|(?:грузо)?захват" + _DOCUMENT_CASE)
_TYPE_IDENTITY_PATTERN = re.compile(
    r"\s*(?:(?:тип(?:\s*оснастки)?|оснастка)\s*[:=-]?\s*)?(?:строп" + _DOCUMENT_CASE + r"\s+)?(?:"
    + _EQUIPMENT_TYPE_TERM
    + "|" + _KNOWN_SLING_FAMILY + ")" + _WORD_END, re.IGNORECASE)


def _rigging_clauses(value: str, *, identity_predicate: Callable[[str], bool]) -> tuple[str, ...]:
    """Keep decimal marks/dates intact, but never span sentence/clause stops."""
    # Number abbreviations are not sentence stops (No.42, инв. №123).
    value = re.sub(r"\b(no|n|инв|зав|рег|сер)\.", r"\1", value, flags=re.IGNORECASE)
    # Keep the complete candidate, including malformed punctuation tails. A
    # generic sentence split must not turn date..99 into the valid date prefix.
    date_spans = tuple((match.start("date"), match.end("date")
                        if _DOCUMENT_DATE_VALUE_PATTERN.fullmatch(match["date"]) else match.end())
                       for match in _DOCUMENT_DATE_PATTERN.finditer(value))
    sentences, start = [], 0
    for stop in _RIGGING_CLAUSE_STOP_PATTERN.finditer(value):
        if any(left <= stop.start() < right for left, right in date_spans):
            continue
        sentences.append(value[start:stop.start()])
        start = stop.end()
    sentences.append(value[start:])
    clauses = []
    for sentence in sentences:
        # Only the selected role's actual identity can end its owner context.
        # Preserve the separator otherwise: incidental counts cannot expose a
        # nested reference, and an unnumbered title cannot borrow across a dash.
        fragments = re.split(r"(:|[^\S\r\n]+-[^\S\r\n]+)", sentence)
        current = fragments[0]
        for separator, fragment in zip(fragments[1::2], fragments[2::2]):
            if not identity_predicate(current):
                current += separator + fragment  # Паспорт: №123, Марка — TR-ABC
            else:
                clauses.append(current)
                current = fragment
        clauses.append(current)
    return tuple(clause.strip() for clause in clauses if clause.strip())


def _concrete_identifier(value: str, *, labeled: bool = False, document: bool = False) -> bool:
    if not _ID_TOKEN_PATTERN.fullmatch(value):
        return False
    letters, digits = any(char.isalpha() for char in value), any(char.isdigit() for char in value)
    if value.isdecimal() or (letters and digits):
        return True
    if document and digits and not letters:
        return True  # document number/date; a sling narrative date is not a mark
    return bool(labeled and letters and value.isupper() and any(char in value for char in "-/_"))


def _sling_identity(clause: str) -> bool:
    match = _SLING_IDENTITY_PATTERN.fullmatch(clause)
    return bool(match and _concrete_identifier(match["mark"], labeled=bool(match["label"]))
                and (match["number"] is None or _concrete_identifier(match["number"], labeled=True)))


def _document_title_token(word: str, noun_case: str) -> str:
    """Positive domain vocabulary and morphology, not a prose deny-list."""
    normalized = word.casefold().replace("ё", "е")
    if all(part in _DOCUMENT_TITLE_NOUNS[noun_case] for part in normalized.split("-")):
        return "noun"
    if _DOCUMENT_TITLE_ADJECTIVE_PATTERN.fullmatch(normalized):
        return "adjective"
    return ""


def _document_reference_prefix(prefix: str) -> bool:
    """Allow attributes and the existing 'По паспорту'/'Согласно протоколу'."""
    words = prefix.casefold().replace("ё", "е").split()
    if words and words[0] in ("по", "согласно"):
        words = words[1:]
    expecting_attribute = True
    for word in words:
        if word == "и" and not expecting_attribute:
            expecting_attribute = True
        elif _document_title_token(word, "genitive") == "adjective":
            expecting_attribute = False
        else:
            return False
    return not words or not expecting_attribute


def _explicit_document_reference(clause: str, start: int) -> bool:
    cursor = _DOCUMENT_TITLE_SPACE_PATTERN.match(clause, start).end()
    colon_used = clause[cursor:cursor + 1] == ":"
    if colon_used:
        cursor = _DOCUMENT_TITLE_SPACE_PATTERN.match(clause, cursor + 1).end()
    noun_case, noun_required = "genitive", False
    seen_word, seen_nominal, expecting_word = False, False, False
    while True:
        marker_cursor = cursor
        separator = clause[marker_cursor:marker_cursor + 1] == ":"
        if separator:
            if colon_used:
                return False
            marker_cursor = _DOCUMENT_TITLE_SPACE_PATTERN.match(clause, marker_cursor + 1).end()
        parenthetical = clause[marker_cursor:marker_cursor + 1] in ("(", "[")
        if parenthetical:
            marker_cursor = _DOCUMENT_TITLE_SPACE_PATTERN.match(clause, marker_cursor + 1).end()
        marker = _DOCUMENT_REFERENCE_MARKER.match(clause, marker_cursor)
        if marker is not None:
            code_start = _DOCUMENT_CODE_GAP.match(clause, marker.end()).end()
            code = _DOCUMENT_CODE_PATTERN.match(clause, code_start)
            return bool(not expecting_word and not noun_required and code
                        and _concrete_identifier(code[0], labeled=True, document=True))
        if separator or parenthetical:
            return False
        token = _DOCUMENT_TITLE_WORD_PATTERN.match(clause, cursor)
        if token is None:
            return False
        word = token[0].casefold().replace("ё", "е")
        if not seen_word and word in ("для", "о"):
            noun_case = "prepositional" if word == "о" else "genitive"
            noun_required, expecting_word = True, True
        elif word == "и" and seen_nominal and not expecting_word:
            expecting_word = True
        else:
            category = _document_title_token(word, noun_case)
            if not category:
                return False
            if category == "noun":
                noun_required = False
            seen_nominal, expecting_word = True, False
        seen_word = True
        cursor = _DOCUMENT_TITLE_SPACE_PATTERN.match(clause, token.end()).end()


def _document_identity(clause: str) -> bool:
    """A reference belongs to a nominal heading, never to relational prose."""
    for kind in _DOCUMENT_KIND_PATTERN.finditer(clause):
        if not _document_reference_prefix(clause[:kind.start()]):
            continue
        if _explicit_document_reference(clause, kind.end()):
            return True
        # Dates retain their narrower document-heading grammar: an inspection
        # date somewhere in prose is not necessarily the document's own date.
        cursor = kind.end()
        while True:
            cursor = _DOCUMENT_HEADER_GAP.match(clause, cursor).end()
            title = _DOCUMENT_TITLE_PATTERN.match(clause, cursor)
            if title is None:
                break
            cursor = title.end()
        if clause[cursor:cursor + 1] in ("(", "["):
            cursor += 1
            cursor = _DOCUMENT_HEADER_GAP.match(clause, cursor).end()
        dated = _DOCUMENT_DATE_PATTERN.match(clause, cursor)
        if dated is not None and _DOCUMENT_DATE_VALUE_PATTERN.fullmatch(dated["date"]):
            text = dated["date"]
            parts = [int(part) for part in re.split(r"[.-]", text)]
            year, month, day = parts if "-" in text else (parts[2], parts[1], parts[0])
            try:
                CalendarDate(year, month, day)
            except ValueError:
                continue
            return True
    return False


def _type_identity(clause: str) -> bool:
    return bool(_TYPE_IDENTITY_PATTERN.match(clause) and not _DOCUMENT_KIND_PATTERN.search(clause))


_RIGGING_IDENTITY_PREDICATES = {
    "rigging_type": _type_identity,
    "sling_identification": _sling_identity,
    "rigging_evidence": _document_identity,
}


def _rigging_semantic_text(value: str) -> str:
    # Semantic words do not become identifiers by touching a number. Positive
    # identity and rendering retain the case and format of the original mark.
    return re.sub(r"(?<=[а-я])(?=[0-9])|(?<=[0-9])(?=[а-я])", " ", value.casefold().replace("ё", "е"))


def meaningful_evidence_text(value: object, *, field_id: str = "") -> bool:
    """Require a concrete role identity and reject missing data in its clause."""
    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    cleaned = "".join(char for char in normalized if char.isalnum())
    if not cleaned or cleaned in {"нет", "нд", "na", "none", "null", "no"}:
        return False
    if not field_id:
        return _EVIDENCE_SENTINEL_PATTERN.search(normalized) is None and _NET_PATTERN.search(normalized) is None
    identity_predicate = _RIGGING_IDENTITY_PREDICATES.get(field_id)
    if identity_predicate is None:
        return False
    # Preserve the number marker before NFKC expands № into the letters No.
    original = unicodedata.normalize("NFKC", value.replace("№", "#")).translate(str.maketrans("‐‑‒–—−", "------"))
    # Normalize only the reserved absence word, including dotted/number-touching
    # forms. Parse clause/label bindings once, before case-folding can alter an
    # uppercase code's identity and make positive/negative scopes disagree.
    clause_source = _ROLE_ABSENCE_PATTERN.sub(" нет ", original)
    # Recognize quality predicates before a spaced dash can be interpreted as
    # a clause boundary (Дефектов — нет). Only whole quality words are removed;
    # malformed words must never erase a missing-document predicate.
    clause_source = _QUALITY_COMMENT_PATTERN.sub(" ", clause_source)
    clauses = _rigging_clauses(clause_source, identity_predicate=identity_predicate)
    evidence = _rigging_semantic_text(clause_source)
    if _EVIDENCE_SENTINEL_PATTERN.search(evidence):
        return False
    for clause in clauses:
        semantic_clause = _rigging_semantic_text(clause)
        if not _NET_PATTERN.search(semantic_clause):
            continue
        essential = "".join(char for char in _ABSENCE_FILLER_PATTERN.sub(" ", semantic_clause) if char.isalnum())
        implicit_subject = identity_predicate(_ROLE_ABSENCE_PATTERN.sub(" ", clause))
        if essential == "нет" or _EVIDENCE_TARGET_PATTERN.search(semantic_clause) or implicit_subject:
            return False
    return (any(identity_predicate(clause) for clause in clauses)
            # Narrow compatibility for the real old heading format. It must
            # lead the field, be complete, and contain no units or metric prose.
            or bool(field_id == "rigging_evidence" and clauses
                    and _LEGACY_DOCUMENT_IDENTITY.fullmatch(clauses[0])))


@dataclass
class ExternalDocument:
    document_id: str
    title: str
    required: bool = False
    present: bool = False
    number: str = ""
    date: str = ""
    organization: str = ""
    verification_status: str = "UNVERIFIED"
    attachment_path: str = ""
    appendix_order: int | None = None
    verified_sha256: str = ""


@dataclass
class TemplateOverride:
    paragraph_id: str
    base_version: str
    replacement_text: str


@dataclass(frozen=True)
class CompletenessIssue:
    code: str
    message: str
    blocking: bool = True
    field_id: str = ""


T = TypeVar("T")


def _known_fields(model: type[T], value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if key in model.__dataclass_fields__}


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _blank_approval_slots() -> list[ApprovalSlot]:
    return [ApprovalSlot() for _ in range(8)]


@dataclass
class PPRKReleaseConfig:
    title: str = ""
    object_address: str = ""
    lifting_equipment_type: str = ""
    developer_organization: str = ""
    project_code: str = ""
    developer_position: str = ""
    developer_name: str = ""
    developer_date: str = ""
    manager_position: str = ""
    manager_name: str = ""
    manager_date: str = ""
    issue_city: str = ""
    issue_year: int | None = None
    issue_date: str = ""
    project_basis: str = ""
    plan_sheet_refs: str = ""
    responsible_fire_safety: str = ""
    max_wind_speed_m_s: float | None = None
    fall_protection_system: str = ""
    power_supply_scheme: str = ""
    waste_plan: str = ""
    external_document_register: str = ""
    receiving_platform_ids: list[str] = field(default_factory=list)
    opening_ids: list[str] = field(default_factory=list)
    bucket_volume_m3: float | None = None
    approvals: list[ApprovalSlot] = field(default_factory=_blank_approval_slots)
    included_section_ids: list[str] = field(default_factory=list)
    excluded_section_ids: list[str] = field(default_factory=list)
    overrides: list[TemplateOverride] = field(default_factory=list)
    external_documents: list[ExternalDocument] = field(default_factory=list)
    status: ReleaseStatus = ReleaseStatus.PRELIMINARY

    def to_dict(self) -> dict[str, Any]:
        return _plain(asdict(self))

    @classmethod
    def from_dict(cls, value: object) -> "PPRKReleaseConfig":
        fields = _known_fields(cls, value)
        raw_status = fields.get("status", ReleaseStatus.PRELIMINARY)
        try:
            fields["status"] = ReleaseStatus(raw_status)
        except (TypeError, ValueError):
            fields["status"] = ReleaseStatus.PRELIMINARY
        if "approvals" in fields:
            fields["approvals"] = [
                ApprovalSlot(**_known_fields(ApprovalSlot, item))
                for item in fields["approvals"]
                if isinstance(item, dict)
            ]
        if "external_documents" in fields:
            fields["external_documents"] = [
                ExternalDocument(**_known_fields(ExternalDocument, item))
                for item in fields["external_documents"]
                if isinstance(item, dict)
                and "document_id" in item
                and "title" in item
            ]
            for document in fields["external_documents"]:
                if document.verification_status == "VERIFIED" and not document.verified_sha256:
                    document.verification_status = "UNVERIFIED"
        if "overrides" in fields:
            fields["overrides"] = [
                TemplateOverride(**_known_fields(TemplateOverride, item))
                for item in fields["overrides"]
                if isinstance(item, dict)
                and all(key in item for key in ("paragraph_id", "base_version", "replacement_text"))
            ]
        for key in (
            "included_section_ids",
            "excluded_section_ids",
            "receiving_platform_ids",
            "opening_ids",
        ):
            if key in fields:
                fields[key] = [str(item) for item in fields[key]] if isinstance(fields[key], list) else []
        return cls(**fields)

