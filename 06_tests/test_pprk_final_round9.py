"""A document marker follows a nominal title, never a borrowed prose reference."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pypdf import PdfReader

import test_pprk_final_round2 as r2
import test_pprk_final_round7 as r7
import test_pprk_final_round8 as r8
from test_pprk_final_round5 import verified_registry
from crane_plan.pprk_context import build_pprk_context
from crane_plan.pprk_models import ReleaseStatus
from crane_plan.pprk_release_workflow import prepare_release, require_saveable_release
from crane_plan.project_io import load_project, save_project


RELATIONAL_REFERENCES = (
    "Паспорт находится на странице №42", "Акт ссылается на испытание №17",
    "Паспорт указан на листе №42", "Паспорт содержит ссылку №42",
    "Акт приложен к заявке №17", "Паспорт приведён на странице №42",
    "Паспорт хранится в приложении №42", "Акт относится к испытанию №17",
    "Паспорт размещён на листе №42", "Акт описан в протоколе на странице №17",
    "Паспорт: находится на странице №42", "Акт проверки ссылается на испытание №17",
    "Паспорт со ссылкой на страницу №42", "Акт по ссылке на испытание №17",
    "Паспорт на странице №42", "Акт в приложении №17", "Паспорт к заявке №42",
    "Паспорт страниц №42", "Протокол листов №17", "Акт испытание №17",
    "Паспорт количества страниц №42", "Акт количества испытаний №17",
    "Паспорт содержит испытания №42", "Акт проверки содержит ссылку №17",
    "Паспорт: ссылка №42", "Акт: заявка №17",
    "Паспорт содержит ссылку на акт №42", "Акт приложен к паспорту №17",
    "Паспорт находится в протоколе испытаний №42",
)
NOMINAL_TITLES = (
    "Акт проверки и испытаний №42", "Паспорт четырёхветвевого стропа №123",
    "Протокол испытаний: №42", "Акт проверки и испытаний: №42",
    "Паспорт цепного грузового стропа: номер 123",
    "Акт внеочередной проверки и контрольных испытаний: ID ACT-42",
    "Протокол периодических испытаний стропов №42",
    "Свидетельство о проверке и испытаниях: рег. №СП-42",
    "Паспорт для технической эксплуатации №123",
    "Акт приёма-передачи оснастки: шифр АП-42",
    "Паспорт: проверенный №42", "Акт №42",
    "Акт осмотра тары и траверсы: №42", "Паспорт контрольно-испытательной оснастки №123",
    "Паспорт технический №123", "Сертификат качества грузозахватных приспособлений №ТР-42",
)
MALFORMED_TITLES = (
    "Паспорт и №42", "Акт проверки и №17", "Паспорт для №42", "Акт о №17",
    "Паспорт для канатного №42", "Свидетельство о выполненной №17",
    "Акт проверки:: №42", "Акт проверки и испытаний — №42",
    "Протокол испытаний — №42", "Акт проверки, и испытаний №42",
    "Паспорт четырёхветвевого. Стропа №123", "Акт проверки\n№42",
    "Паспорт непроверенного стропа №42", "Акт проверки и испытаний отсутствует №17",
    "Паспорт для ссылки №42", "Свидетельство о заявке №17",
    "Паспорт проверки на странице №42", "Акт для страницы №17",
)


class Round9Tests(unittest.TestCase):
    assert_documents = r7.Round7Tests.assert_documents
    assert_gui_atomic_rejection = r2.Round2Tests.assert_gui_atomic_rejection

    def test_relational_prose_and_page_or_test_references_are_not_document_identity(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_documents(project, scenario, RELATIONAL_REFERENCES, False)

    def test_nominal_titles_and_all_existing_title_controls_keep_explicit_identity(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_documents(project, scenario, (*r8.NATURAL_TITLES, *NOMINAL_TITLES), True)

    def test_incomplete_nominal_grammar_and_punctuation_cannot_borrow_a_marker(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_documents(project, scenario, MALFORMED_TITLES, False)

    def test_loaded_prose_and_checkbox_remain_raw_but_not_confirmed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, value in enumerate(RELATIONAL_REFERENCES[:2]):
                project, scenario = r2.ready(root / str(index) / "fixture")
                project.loads[0].rigging_evidence = value
                path = save_project(root / str(index) / "saved", project)
                before = path.read_bytes()
                loaded = load_project(path)
                self.assertEqual(loaded.loads[0].rigging_evidence, value)
                self.assertIs(loaded.loads[0].rigging_verified, True)
                self.assertFalse(build_pprk_context(loaded, scenario, r2.verify(loaded, scenario)).active_loads[0].confirmed)
                self.assertEqual(path.read_bytes(), before)

    def test_reviewer_prose_cards_are_pending_and_all_advanced_gui_saves_are_atomic(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate((*RELATIONAL_REFERENCES[:2], "Акт приложен к заявке №17")):
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
                            self.assert_gui_atomic_rejection(project, scenario, checked, root / str(index) / status.value)
                            release = prepare_release(project, scenario, checked)
                            self.assertTrue(any(i.code == "PPRK_RIGGING_EVIDENCE_REQUIRED" for i in release.bundle.completeness_issues))
                            with self.assertRaises(ValueError):
                                require_saveable_release(release, checked)

    def test_nominal_title_controls_reach_confirmed_physical_gui_production(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate(NOMINAL_TITLES[:4]):
                    with self.subTest(value=value):
                        project, scenario = r2.ready(root / str(index) / "fixture")
                        project.loads[0].rigging_evidence = value
                        project.pprk_release.status = ReleaseStatus.PRODUCTION
                        checked = r2.verify(project, scenario)
                        try:
                            require_saveable_release(prepare_release(project, scenario, checked), checked)
                        except ValueError as error:
                            self.fail(f"A nominal document title must retain its own reference: {error}")
                        output = r2.save_via_gui(project, scenario, checked, root / str(index) / "production")
                        card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                        self.assertIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                        self.assertIn(value, card)
                        self.assertNotIn("НЕ ЗАПОЛНЕНО", card)


if __name__ == "__main__":
    unittest.main()

