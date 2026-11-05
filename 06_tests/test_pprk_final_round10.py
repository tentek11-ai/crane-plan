"""A linked document date must have the same bounded owner as a number."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pypdf import PdfReader

import test_pprk_final_round2 as r2
import test_pprk_final_round7 as r7
from test_pprk_final_round5 import verified_registry
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_models import ReleaseStatus
from crane_plan.pprk_release_workflow import prepare_release, require_saveable_release
from crane_plan.project_io import load_project, save_project


NESTED_DATES = (
    "Паспорт содержит ссылку на акт от 03.11.2026",
    "Акт приложен к паспорту от 2024-02-29",
    "Паспорт ссылается на протокол испытаний от 03.11.2026",
    "Акт указывает на сертификат от 2024-02-29",
    "Паспорт находится в протоколе от 03.11.2026",
    "Паспорт со ссылкой на акт от 03.11.2026",
    "Акт по ссылке на паспорт от 2024-02-29",
    "Паспорт содержит ссылку: акт от 03.11.2026",
    "Акт приложен — паспорт от 2024-02-29",
    "Паспорт: содержит ссылку на акт от 03.11.2026",
    "Паспорт содержит ссылку на проверенный акт от 03.11.2026",
    "Акт приложен к уточнённому паспорту от 2024-02-29",
)
DIRECT_DATES = (
    "Акт от 03.11.2026", "Паспорт от 2024-02-29", "Акт проверки от 03.11.2026",
    "Паспорт стропа от 03.11.2026", "Протокол испытаний от 2024-02-29",
    "Сертификат оборудования от 03.11.2026", "Испытательный паспорт от 03.11.2026",
    "Уточнённый акт проверки от 03.11.2026", "По акту от 03.11.2026",
    "Согласно протоколу испытаний от 2024-02-29", "Паспорт дата: 03.11.2026",
    "Акт проверки (от 03.11.2026)",
)
BOUNDARIES = (
    "Акт проверки; от 03.11.2026", "Паспорт стропа. От 2024-02-29",
    "Протокол испытаний, от 03.11.2026", "Акт проверки\nот 03.11.2026",
    "Паспорт содержит ссылку: акт от 03.11.2026",
    "Акт приложен — паспорт от 2024-02-29",
)
NUMBER_CONTROL = "По акту приёма-передачи оснастки №42"


class Round10Tests(unittest.TestCase):
    assert_documents = r7.Round7Tests.assert_documents
    assert_gui_atomic_rejection = r2.Round2Tests.assert_gui_atomic_rejection

    def test_relational_nested_document_dates_do_not_supply_identity(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp)/"fixture")
            self.assert_documents(project, scenario, NESTED_DATES, False)

    def test_direct_dates_existing_natural_headers_and_approved_number_stay_valid(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp)/"fixture")
            self.assert_documents(project, scenario, (*DIRECT_DATES, NUMBER_CONTROL), True)

    def test_date_owner_binding_does_not_cross_punctuation_or_heading_boundaries(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp)/"fixture")
            self.assert_documents(project, scenario, BOUNDARIES, False)

    def test_loaded_nested_date_strings_and_flags_are_retained_without_confirmation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, value in enumerate(NESTED_DATES[:2]):
                project, scenario = r2.ready(root/str(index)/"fixture")
                project.loads[0].rigging_evidence = value
                path = save_project(root/str(index)/"saved", project)
                before = path.read_bytes(); loaded = load_project(path)
                self.assertEqual(loaded.loads[0].rigging_evidence, value)
                self.assertIs(loaded.loads[0].rigging_verified, True)
                self.assertFalse(build_pprk_context(loaded, scenario, r2.verify(loaded, scenario)).active_loads[0].confirmed)
                self.assertEqual(path.read_bytes(), before)

    def test_nested_date_cards_are_pending_and_all_advanced_gui_saves_are_atomic(self):
        cases = (*NESTED_DATES[:2], "Паспорт содержит ссылку: акт от 03.11.2026")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate(cases):
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

    def test_direct_date_and_approved_number_controls_reach_physical_gui_production(self):
        cases = (DIRECT_DATES[0], DIRECT_DATES[1], DIRECT_DATES[3], NUMBER_CONTROL)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate(cases):
                    with self.subTest(value=value):
                        project, scenario = r2.ready(root/str(index)/"fixture")
                        project.loads[0].rigging_evidence = value
                        project.pprk_release.status = ReleaseStatus.PRODUCTION
                        checked = r2.verify(project, scenario)
                        try:
                            require_saveable_release(prepare_release(project, scenario, checked), checked)
                        except ValueError as error:
                            self.fail(f"A directly owned document identity must remain eligible: {error}")
                        output = r2.save_via_gui(project, scenario, checked, root/str(index)/"production")
                        card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                        self.assertIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                        self.assertIn(value, card)
                        self.assertNotIn("НЕ ЗАПОЛНЕНО", card)


if __name__ == "__main__":
    unittest.main()

