"""Clause boundaries require an actual role identity, never incidental digits."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pypdf import PdfReader

import test_pprk_final_round2 as r2
import test_pprk_final_round6 as r6
import test_pprk_final_round7 as r7
from test_pprk_final_round5 import verified_registry
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_models import ReleaseStatus
from crane_plan.pprk_release_workflow import prepare_release, require_saveable_release
from crane_plan.project_io import load_project, save_project


REVIEWER_NEGATIVES = (
    "Паспорт содержит 1 ссылку: акт от 03.11.2026",
    "Акт содержит 1 ссылку — паспорт от 2024-02-29",
)
NUMBER_OWNER_NEGATIVES = (
    *REVIEWER_NEGATIVES,
    *(f"Паспорт содержит {count} ссылку{separator}акт от 03.11.2026"
      for count in (0, 1, 2, 42, 2026, 123456) for separator in (": ", " — ", " - ")),
    *(f"{left}{separator}паспорт от 2024-02-29" for left in (
        "Акт содержит 12 страниц", "Протокол содержит 3 испытания", "Паспорт дефектов 0",
        "Паспорт масса 500 кг", "Паспорт грузоподъёмность 5,0 т") for separator in (": ", " — ")),
    "Паспорт содержит 1 ссылку: акт №42",
    "Акт содержит 2 страницы — протокол испытаний ID TEST-ABC",
    "Паспорт содержит 1 ссылку: акт содержит 2 ссылки — паспорт от 2024-02-29",
)
ROLE_NEGATIVES = {
    "rigging_type": ("Тип содержит 1 ссылку: канатный", "Описание 42 — канатный",
                     "Оснастка содержит 3 элемента: траверса"),
    "sling_identification": ("Строп содержит 1 ссылку: 4СК-5,0", "Марка содержит 42 ссылки — TR-ABC",
                             "Описание 123: Строп 4СК-5,0 №123"),
    "rigging_evidence": ("Описание 42: паспорт от 2024-02-29", "Описание 123 — Акт №42"),
}
ROLE_CONTROLS = {
    "rigging_type": ("Тип: канатный", "Канатный: рисков нет", "Траверса — исправна"),
    "sling_identification": ("Марка: TR-ABC", "Номер: 123", "Строп 4СК-5,0 №123: рисков нет",
                             "Марка: TR-ABC — рисков нет"),
    "rigging_evidence": (
        "Паспорт №1: дефектов нет", "Акт №1 — рисков нет", "Акт от 03.11.2026: осмотр выполнен",
        "Паспорт от 2024-02-29 — исправен", "Протокол испытаний: №42",
        "Акт проверки и испытаний №42: проверен", "Паспорт четырёхветвевого стропа №123 — исправен",
        "По акту приёма-передачи оснастки №42: проверено", "Паспорт ID PS-1: проверен",
        "Протокол шифр TEST-ABC — проверен", "Паспорт дата: 03.11.2026", "Испытательный паспорт 123"),
}
PHYSICAL_NEGATIVES = (*REVIEWER_NEGATIVES, "Акт содержит 12 страниц: паспорт от 2024-02-29")
PHYSICAL_CONTROLS = (ROLE_CONTROLS["rigging_evidence"][0], ROLE_CONTROLS["rigging_evidence"][1],
                     ROLE_CONTROLS["rigging_evidence"][2], ROLE_CONTROLS["rigging_evidence"][7])


class Round11Tests(unittest.TestCase):
    assert_documents = r7.Round7Tests.assert_documents
    assert_field_values = r6.Round6Tests.assert_field_values
    assert_gui_atomic_rejection = r2.Round2Tests.assert_gui_atomic_rejection

    def test_arbitrary_number_before_separator_does_not_discard_document_owner(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp)/"fixture")
            self.assert_documents(project, scenario, NUMBER_OWNER_NEGATIVES, False)

    def test_unidentified_owner_context_survives_separators_for_each_role(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp)/"fixture")
            self.assert_field_values(project, scenario, ROLE_NEGATIVES, False)

    def test_role_specific_identified_left_sides_and_supported_labels_stay_valid(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp)/"fixture")
            self.assert_field_values(project, scenario, ROLE_CONTROLS, True)

    def test_loaded_numeric_prose_and_checked_flags_are_retained_without_confirmation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, value in enumerate(REVIEWER_NEGATIVES):
                project, scenario = r2.ready(root/str(index)/"fixture")
                project.loads[0].rigging_evidence = value
                path = save_project(root/str(index)/"saved", project)
                before = path.read_bytes(); loaded = load_project(path)
                self.assertEqual(loaded.loads[0].rigging_evidence, value)
                self.assertIs(loaded.loads[0].rigging_verified, True)
                self.assertFalse(build_pprk_context(loaded, scenario, r2.verify(loaded, scenario)).active_loads[0].confirmed)
                self.assertEqual(path.read_bytes(), before)

    def test_numeric_owner_cards_are_pending_and_all_advanced_gui_saves_are_atomic(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate(PHYSICAL_NEGATIVES):
                    project, scenario = r2.ready(root/str(index)/"fixture")
                    project.loads[0].rigging_evidence = value
                    checked = r2.verify(project, scenario)
                    with self.subTest(value=value, status="PRELIMINARY"):
                        output = r2.save_via_gui(project, scenario, checked, root/str(index)/"draft")
                        card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                        self.assertIn("НЕ ПОДТВЕРЖДЕНО", card)
                        self.assertNotIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                    for status in ReleaseStatus:
                        if status is ReleaseStatus.PRELIMINARY:
                            continue
                        with self.subTest(value=value, status=status):
                            project.pprk_release.status = status
                            self.assert_gui_atomic_rejection(project, scenario, checked, root/str(index)/status.value)
                            view = prepare_release(project, scenario, checked)
                            self.assertTrue(any(i.code == "PPRK_RIGGING_EVIDENCE_REQUIRED" for i in view.bundle.completeness_issues))
                            with self.assertRaises(ValueError):
                                require_saveable_release(view, checked)

    def test_identified_left_sides_reach_physical_gui_production(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate(PHYSICAL_CONTROLS):
                    with self.subTest(value=value):
                        project, scenario = r2.ready(root/str(index)/"fixture")
                        project.loads[0].rigging_evidence = value
                        project.pprk_release.status = ReleaseStatus.PRODUCTION
                        checked = r2.verify(project, scenario)
                        try:
                            require_saveable_release(prepare_release(project, scenario, checked), checked)
                        except ValueError as error:
                            self.fail(f"An identified left side must retain eligibility: {error}")
                        output = r2.save_via_gui(project, scenario, checked, root/str(index)/"production")
                        card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                        self.assertIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                        self.assertIn(value, card)
                        self.assertNotIn("НЕ ЗАПОЛНЕНО", card)


if __name__ == "__main__":
    unittest.main()

