"""Field-specific identities and clause-scoped absence at public boundaries."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pypdf import PdfReader

import test_pprk_final_round2 as r2
from test_pprk_final_round5 import verified_registry
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_models import ReleaseStatus
from crane_plan.pprk_release_workflow import prepare_release, require_saveable_release


POSITIVES = {
    "rigging_type": ("Канатный", "Канатная", "Текстильными", "Тип: канатный четырёхветвевой", "Цепной", "Текстильный",
                     "Круглопрядный строп", "Траверса", "Захват", "4СК-5,0", "Строп 4СК"),
    "sling_identification": ("4СК-1", "4СК-TEST", "4СК-5,0", "Строп 4СК-5,0 №123", "Номер: 123", "123",
                             "Номер: НЕТТО-42", "No.42", "Марка: TR-ABC", "Строп ЦЕПЬ-АБВ", "УСК1-5,0"),
    "rigging_evidence": ("Испытательный паспорт оснастки №123", "Паспорт №123. Дефектов нет",
                         "Паспорт No.42: ПРОВЕРЕНО", "Уточнённый паспорт №42", "Акт от 03.11.2026",
                         "Сертификат №TR-ABC", "Протокол испытаний №42", "Свидетельство №123-45"),
}
NEGATIVES = {
    "rigging_type": ("По результатам осмотра дефектов нет.", "Проверено", "Тип оснастки",
                     "Паспорт №123", "Номер: 42", "Оснастка", "Имеется в наличии", "Канатный паспорт №123",
                     "Канатныйнет", "Захватка №123"),
    "sling_identification": ("По результатам осмотра дефектов нет.", "Осмотр от 03.11.2026 по акту 42",
                             "По результатам осмотра от 03.11.2026 дефектов нет", "Канатный", "Строп",
                             "Номер", "Паспорт №123", "Дефектов нет.", "Марка: по-результатам", "Марка: ПРОВЕРЕНО"),
    "rigging_evidence": ("По результатам осмотра дефектов нет.", "Осмотр от 03.11.2026",
                         "Идентификация подтверждена 03.11.2026", "Испытательный паспорт", "Паспорт и акт",
                         "4СК-5,0", "№123", "Все данные сверены", "Осмотр выполнен. Дефектов нет.",
                         "Актуальные сведения 123", "Протокольная запись 42", "Документ №123"),
}


class Round6Tests(unittest.TestCase):
    assert_gui_atomic_rejection = r2.Round2Tests.assert_gui_atomic_rejection

    def assert_field_values(self, project, scenario, corpus, expected):
        checked = r2.verify(project, scenario)
        for field, values in corpus.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    changed = deepcopy(project)
                    setattr(changed.loads[0], field, value)
                    self.assertEqual(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed, expected)

    def test_absence_with_intervening_reference_or_mark_is_not_evidence_in_any_role(self):
        values = ("Паспорта №123 нет", "Паспорт №123 нет", "Строп 4СК нет",
                  "Схема по акту 42 отсутствует", "Паспорт: №123 пока нет",
                  "Канатный. Паспорта инв. №123 нет", "Паспорт №123. Стропа 4СК-5,0 нет")
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_field_values(project, scenario, {field: values for field in POSITIVES}, False)

    def test_real_equipment_marks_and_named_documents_satisfy_their_own_roles(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_field_values(project, scenario, POSITIVES, True)

    def test_generic_prose_and_cross_role_values_are_not_positive_identity(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_field_values(project, scenario, NEGATIVES, False)

    def test_label_colons_bind_identity_but_identified_clauses_stop_at_colon_or_dash(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_field_values(project, scenario, {
                "rigging_type": ("Тип: канатный", "Канатный: рисков нет"),
                "sling_identification": ("Марка: TR-ABC", "Номер: 123", "Марка: TR-ABC: рисков нет",
                                         "Марка: TR-ABC — рисков нет"),
                "rigging_evidence": ("Паспорт: №123", "Протокол испытаний: №42", "Паспорт №123: рисков нет",
                                     "Паспорт №123 — рисков нет", "Паспорт №123 - рисков нет"),
            }, True)
            self.assert_field_values(project, scenario, {
                "rigging_type": ("Тип: пока нет",),
                "sling_identification": ("Номер: нет", "Марка: TR-ABC: нет"),
                "rigging_evidence": ("Паспорт: №123 нет", "Паспорт №123: нет"),
            }, False)

    def test_paraphrases_and_word_number_boundaries_preserve_scope_and_real_marks(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            missing = ("Паспорта за №123 нет", "Нет паспорта под №123", "Стропа марки 4СК-5,0 нет",
                       "Паспорта №123нет", "НЕПРОВЕРЕНО123", "Паспорт №НЕЗАПОЛНЕНО123",
                       "Канатный. Стропа 4СК-5,0нет")
            self.assert_field_values(project, scenario, {field: missing for field in POSITIVES}, False)
            self.assert_field_values(project, scenario, {
                "rigging_type": ("Строп цепной", "КАНАТНЫЙ"),
                "sling_identification": ("Бирка: АБВ-ГДЕ", "УСК1-5,0", "4ск-5,0", "НЕТТО-42"),
                "rigging_evidence": ("По паспорту №123", "Согласно протоколу №42", "Свидетельство №АБ-ВГ"),
            }, True)

    def test_implicit_role_absence_and_uppercase_clause_binding_use_one_scope(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_field_values(project, scenario, {
                "rigging_type": ("Траверса нет", "Канатный нет", "Канатный. Н.Е.Т",
                                 "Траверса отсутствует дефектовнет"),
                "sling_identification": ("4СК-5,0нет", "4СК-TEST. 4СК-5,0 нет", "4СК-TEST. Н.Е.Т",
                                         "4СК-TEST. 4СК-5,0 отсутствует дефектовнет"),
                "rigging_evidence": ("Паспорт №123. Н.Е.Т", "Паспорт №123 отсутствует дефектовнет",
                                     "Паспорт №123 отсутствуетдефекты"),
            }, False)
            self.assert_field_values(project, scenario, {
                "rigging_type": ("Траверса: рисков нет",),
                "sling_identification": ("Марка: АБВ-ГДЕ: рисков нет",),
                "rigging_evidence": ("Протокол №TEST-ABC: рисков нет", "Сертификат №АБ-ВГ — рисков нет"),
            }, True)

    def test_decimal_marks_and_separate_quality_clauses_do_not_lose_valid_identity(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_field_values(project, scenario, {
                "rigging_type": ("Канатный. Дефектов нет", "Траверса; отсутствуют дефекты", "4СК-5,0, замечаний нет",
                                 "Канатный. Дефектов — нет"),
                "sling_identification": ("4СК-5,0. Дефектов нет", "Строп 4СК-5,0 №123; повреждений нет",
                                         "Марка: TR-ABC, нет замечаний", "4СК-5,0. Дефектов — нет"),
                "rigging_evidence": ("Паспорт №123. Дефектов нет", "Паспорт №123, повреждений нет",
                                     "Протокол №42; неприменимых элементов нет", "Акт от 03.11.2026. Замечаний нет",
                                     "Паспорт №123. Дефектов — нет"),
            }, True)
            self.assert_field_values(project, scenario, {
                "rigging_type": ("Канатный. Стропа 4СК-5,0 нет",),
                "sling_identification": ("4СК-5,0. Нет", "Строп 4СК-5,0 №123 нет"),
                "rigging_evidence": ("Паспорт №123 нет. Дефектов нет", "Паспорт №123; документа №42 нет"),
            }, False)

    def test_missing_reference_and_each_invalid_role_are_pending_drafts_and_atomic_advanced_blocks(self):
        cases = (("rigging_evidence", "Паспорта №123 нет"),
                 ("rigging_type", "По результатам осмотра дефектов нет."),
                 ("rigging_type", "Траверса нет"),
                 ("sling_identification", "По результатам осмотра дефектов нет."),
                 ("rigging_evidence", "Осмотр от 03.11.2026. Дефектов нет."))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, (field, value) in enumerate(cases):
                    project, scenario = r2.ready(root / str(index) / "fixture")
                    setattr(project.loads[0], field, value)
                    checked = r2.verify(project, scenario)
                    with self.subTest(field=field, value=value, status="PRELIMINARY"):
                        output = r2.save_via_gui(project, scenario, checked, root / str(index) / "draft")
                        card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                        self.assertIn("НЕ ПОДТВЕРЖДЕНО", card)
                        self.assertNotIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                    for status in ReleaseStatus:
                        if status is ReleaseStatus.PRELIMINARY:
                            continue
                        with self.subTest(field=field, value=value, status=status):
                            project.pprk_release.status = status
                            release = prepare_release(project, scenario, checked)
                            self.assertTrue(any(issue.code == "PPRK_RIGGING_EVIDENCE_REQUIRED" for issue in release.bundle.completeness_issues))
                            with self.assertRaises(ValueError):
                                require_saveable_release(release, checked)
                            self.assert_gui_atomic_rejection(project, scenario, checked, root / str(index) / status.value)

    def test_decimal_and_uppercase_marks_reach_confirmed_physical_production_with_real_document_identity(self):
        cases = (("Канатный", "Строп 4СК-5,0 №123", "Паспорт №123. Дефектов нет"),
                 ("Траверса", "Марка: TR-ABC", "Протокол №TEST-ABC: рисков нет"),
                 ("Канатный. Дефектов — нет", "4СК-5,0. Дефектов — нет", "Паспорт №123. Дефектов — нет"))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, values in enumerate(cases):
                    with self.subTest(values=values):
                        project, scenario = r2.ready(root / str(index) / "fixture")
                        for field, value in zip(POSITIVES, values):
                            setattr(project.loads[0], field, value)
                        project.pprk_release.status = ReleaseStatus.PRODUCTION
                        checked = r2.verify(project, scenario)
                        try:
                            require_saveable_release(prepare_release(project, scenario, checked), checked)
                        except ValueError as error:
                            self.fail(f"Concrete role identities cannot be rejected: {error}")
                        output = r2.save_via_gui(project, scenario, checked, root / str(index) / "production")
                        card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                        self.assertIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                        for value in values:
                            self.assertIn(value, card)
                        self.assertNotIn("НЕ ЗАПОЛНЕНО", card)


if __name__ == "__main__":
    unittest.main()

