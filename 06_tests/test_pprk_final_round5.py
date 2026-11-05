"""Rigging evidence grammar and negation scope at real release boundaries."""
from contextlib import contextmanager
from copy import deepcopy
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pypdf import PdfReader

import test_pprk_final_round2 as r2
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_models import ReleaseStatus
from crane_plan.pprk_release_workflow import prepare_release, require_saveable_release
import crane_plan.pprk_regulations as regulations


FIELDS = ("rigging_type", "sling_identification", "rigging_evidence")
IDENTITIES = {
    "rigging_type": "Тип: канатный четырёхветвевой",
    "sling_identification": "Строп 4СК-42",
    "rigging_evidence": "Паспорт № 123. Осмотр от 03.11.2026 по акту 42",
}
QUALITY_COMMENTS = ("Дефектов нет.", "нет замечаний", "повреждений нет",
                    "отсутствуют дефекты", "неприменимых элементов нет")


@contextmanager
def verified_registry(directory):
    """Isolated normative data; never patch the release gate or shipped rows."""
    with regulations.DEFAULT_REGISTRY_PATH.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream); columns = reader.fieldnames; rows = list(reader)
    for row in rows:
        row["verification_status"] = "VERIFIED_SOURCE"
    registry = directory / "controlled-registry.csv"
    with registry.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader(); writer.writerows(rows)
    with patch.object(regulations, "DEFAULT_REGISTRY_PATH", registry):
        yield


class Round5Tests(unittest.TestCase):
    assert_gui_atomic_rejection = r2.Round2Tests.assert_gui_atomic_rejection

    def assert_corpus(self, project, scenario, values, expected):
        checked = r2.verify(project, scenario)
        for field in FIELDS:
            for value in values:
                with self.subTest(field=field, value=value):
                    changed = deepcopy(project)
                    setattr(changed.loads[0], field, value)
                    self.assertEqual(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed, expected)

    def test_negative_russian_stems_cover_inflection_anywhere_in_each_field(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_corpus(project, scenario, (
                "Заявка на отсутствующую схему строповки",
                "Ссылка на непроверенную ведомость оснастки",
                "К отсутствующей схеме", "Отсутствующая оснастка", "Отсутствующий паспорт",
                "Ссылка на отсутствующими документами", "Незаполненную ведомость оснастки",
                "Ссылка на не заполненную ведомость", "Ссылка на не применимую схему",
                "По непроверенным сведениям", "По не предоставленному паспорту",
                "Паспорт №123. Схема НЕ__ПОДТВЕРЖДЁННАЯ.",
                "По ожидающим подтверждения документам", "Подлежит уточнению",
            ), False)

    def test_net_rejects_missing_values_assignments_and_targeted_evidence(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_corpus(project, scenario, (
                "нет", " ⟦ Н.Е.Т ⟧ ", "Паспорт: нет", "Строп — нет", "Номер: нет",
                "схемы нет", "нет оснастки", "Схемы строповки нет", "Оснастка №42 отсутствует",
                "Паспорт №123. Схемы нет.", "Паспорт №123. Документ: нет.",
            ), False)

    def test_quality_negation_with_identifying_evidence_is_positive_in_each_field(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            checked = r2.verify(project, scenario)
            for field, identity in IDENTITIES.items():
                for comment in QUALITY_COMMENTS:
                    with self.subTest(field=field, comment=comment):
                        changed = deepcopy(project)
                        setattr(changed.loads[0], field, identity + ". " + comment)
                        self.assertTrue(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed)
            # These identities belong to their respective roles, not every field.
            for field, value in (("sling_identification", "НЕТТО-42"), ("sling_identification", "No.42"),
                                 ("rigging_evidence", "Уточнённый паспорт №42")):
                with self.subTest(field=field, value=value):
                    changed = deepcopy(project)
                    setattr(changed.loads[0], field, value)
                    self.assertTrue(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed)

    def test_quality_statements_alone_do_not_identify_rigging_or_document(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_corpus(project, scenario, QUALITY_COMMENTS, False)

    def test_quality_scope_does_not_hide_an_independent_missing_reference(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_corpus(project, scenario, (
                "Паспорт №123. Дефектов нет. Ссылка на непроверенную ведомость оснастки.",
                "Нет замечаний, но схемы нет.",
                "Паспорт №123. Отсутствуют дефекты; отсутствующая схема строповки.",
                "Паспорт №123. Неприменимых элементов нет, оснастка отсутствует.",
                "Паспорт №123 отсутствует, дефектов нет.",
                "Паспорт №123 отсутствует: дефектов нет.",
                "Паспорт №123 отсутствует — дефекты не выявлены.",
            ), False)
            checked = r2.verify(project, scenario)
            for field, identity in IDENTITIES.items():
                with self.subTest(field=field, positive="Дефектов — нет"):
                    changed = deepcopy(project)
                    setattr(changed.loads[0], field, identity + ". Дефектов — нет.")
                    self.assertTrue(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed)

    def test_quality_lists_and_labels_still_require_identifying_information(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            comments = ("Нет дефектов и повреждений", "Дефекты и повреждения отсутствуют",
                        "Нет дефектов, повреждений", "Дефекты, повреждения отсутствуют",
                        "Нет замечаний к оснастке", "Паспорт: дефектов нет", "Строп: повреждений нет")
            self.assert_corpus(project, scenario, comments, False)
            checked = r2.verify(project, scenario)
            for field, identity in IDENTITIES.items():
                for comment in comments:
                    with self.subTest(field=field, comment=comment):
                        changed = deepcopy(project)
                        setattr(changed.loads[0], field, identity + ". " + comment)
                        self.assertTrue(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed)

    def test_qualifiers_do_not_turn_essential_absence_or_quality_only_text_into_identity(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_corpus(project, scenario, (
                "Пока нет", "Паспорт: ещё нет", "Строп — совсем нет", "Вообще нет замечаний",
                "Паспорт №123. Схемы пока нет.", "Паспорт №123. Нет пока оснастки.",
                "Паспорт: отсутствуют какие-либо дефекты", "Совсем нет повреждений",
            ), False)
            checked = r2.verify(project, scenario)
            for field, identity in IDENTITIES.items():
                for comment in ("Вообще нет замечаний", "Пока нет повреждений", "Отсутствуют какие-либо дефекты"):
                    with self.subTest(field=field, positive=comment):
                        changed = deepcopy(project)
                        setattr(changed.loads[0], field, identity + ". " + comment)
                        self.assertTrue(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed)

    def test_reviewer_phrases_are_pending_in_physical_draft_and_block_all_advanced_statuses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate(("Заявка на отсутствующую схему строповки",
                                               "Ссылка на непроверенную ведомость оснастки")):
                    project, scenario = r2.ready(root / str(index) / "fixture")
                    project.loads[0].rigging_evidence = value
                    checked = r2.verify(project, scenario)
                    with self.subTest(value=value, status="PRELIMINARY"):
                        output = r2.save_via_gui(project, scenario, checked, root / str(index) / "draft")
                        card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                        self.assertIn("НЕ ПОДТВЕРЖДЕНО", card)
                        self.assertNotIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                    for status in ReleaseStatus:
                        if status is ReleaseStatus.PRELIMINARY:
                            continue
                        with self.subTest(value=value, status=status):
                            project.pprk_release.status = status
                            release = prepare_release(project, scenario, checked)
                            self.assertTrue(any(issue.code == "PPRK_RIGGING_EVIDENCE_REQUIRED" for issue in release.bundle.completeness_issues))
                            with self.assertRaises(ValueError):
                                require_saveable_release(release, checked)
                            self.assert_gui_atomic_rejection(project, scenario, checked, root / str(index) / status.value)

    def test_valid_inspection_sentence_preserves_confirmed_physical_production_card(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                project, scenario = r2.ready(root / "fixture")
                project.loads[0].rigging_type = IDENTITIES["rigging_type"] + ". Отсутствуют дефекты."
                project.loads[0].sling_identification = IDENTITIES["sling_identification"] + ". Повреждений нет."
                evidence = IDENTITIES["rigging_evidence"] + ". Дефектов нет."
                project.loads[0].rigging_evidence = evidence
                project.pprk_release.status = ReleaseStatus.PRODUCTION
                checked = r2.verify(project, scenario)
                require_saveable_release(prepare_release(project, scenario, checked), checked)
                output = r2.save_via_gui(project, scenario, checked, root / "production")
                card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                self.assertIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                self.assertIn(evidence, card)
                self.assertNotIn("НЕ ЗАПОЛНЕНО", card)
                self.assertNotIn("НЕ ПОДТВЕРЖДЕНО", card)


if __name__ == "__main__":
    unittest.main()

