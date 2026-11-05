"""Immutable release snapshot of the existing normative evidence registry."""
from dataclasses import dataclass
from datetime import date
import csv
import re

from .pprk_templates import DEFAULT_REGISTRY_PATH


@dataclass(frozen=True)
class PPRKRegulation:
    rule_id: str
    topic: str
    document: str
    edition_or_status: str
    locator: str
    software_status: str
    rule_summary: str
    verification_note: str
    verification_status: str = "UNVERIFIED_STATUS"
    valid_from: str = ""
    valid_until: str = ""

    @property
    def verified(self):
        # Implementation/catalog/reference labels are not legal verification.
        return self.verification_status in {"VERIFIED_SOURCE", "VERIFIED_SOURCE_EXPIRING"}

    def release_text(self):
        return (f"{self.rule_id} — {self.document}. {self.topic}. Редакция/действие: {self.edition_or_status}. "
                f"Пункт: {self.locator}. Проверка источника: {self.verification_status}. Статус реализации: {self.software_status}. "
                f"Начало: {self.valid_from or 'не указано'}; окончание: {self.valid_until or 'не указано'}. "
                f"{self.rule_summary}. Проверка/источник: {self.verification_note}")


def _explicit_date(text, pattern):
    match = re.search(pattern + r"\s*(\d{2}\.\d{2}\.\d{4})", text)
    if not match:
        return ""
    day, month, year = map(int, match.group(1).split("."))
    return date(year, month, day).isoformat()


def load_release_regulations(path=None):
    with open(path or DEFAULT_REGISTRY_PATH, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        expected = ("rule_id", "topic", "document", "edition_or_status", "verification_status",
                    "locator", "software_status", "rule_summary", "verification_note")
        if tuple(reader.fieldnames or ()) != expected:
            raise ValueError("Неподдерживаемая или неоднозначная схема нормативного реестра")
        rows = list(reader)
    records = []
    seen = set()
    for row in rows:
        if set(row) != set(expected) or any(row[name] is None for name in expected):
            raise ValueError("Неоднозначное число полей строки нормативного реестра")
        values = {name: row[name] for name in expected}
        if not values["rule_id"] or values["rule_id"] in seen or not values["document"]:
            raise ValueError("Неполный или неоднозначный нормативный реестр")
        seen.add(values["rule_id"])
        records.append(PPRKRegulation(**values,
            valid_from=_explicit_date(values["edition_or_status"], r"действует с"),
            valid_until=_explicit_date(values["edition_or_status"], r"до")))
    if not records:
        raise ValueError("Пустой нормативный реестр")
    return tuple(records)
