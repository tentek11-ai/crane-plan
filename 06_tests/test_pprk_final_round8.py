"""Document dates are whole tokens; explicit references allow natural titles."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pypdf import PdfReader

import test_pprk_final_round2 as r2
from test_pprk_final_round5 import verified_registry
import test_pprk_final_round7 as r7
from crane_plan.pprk_models import ReleaseStatus
from crane_plan.pprk_release_workflow import prepare_release, require_saveable_release


INVALID_DATES = (
    "Акт проверки от 2026-11-03-99", "Паспорт от 03.11.2026.99",
    "Паспорт от -2026-11-03", "Акт от 2026-11-03--99", "Акт от 03.11.2026..99",
    "Акт от 2026-11-03.99", "Акт от 03.11.2026-99", "Акт от 2026-11-030",
    "Акт от 003.11.2026", "Акт от 12026-11-03", "Акт от 03.11.20260",
    "Акт от .03.11.2026", "Акт от 2026--11-03", "Акт от 03..11.2026",
    "Акт от 2026-11-03-extra", "Акт от 03.11.2026.extra", "Акт от 03.11.2026..",
    "Акт от 2026-11-03/99", "Акт от 03.11.2026,99", "Акт от +2026-11-03",
    "Акт от - 2026-11-03", "Акт от 2026-11-03-", "Акт от 03.11.2026-",
    "Паспорт дата 29.02.2023", "Акт от 31.04.2026", "Акт от 2026-13-03",
    "Паспорт дата: 03.11.2026.99", "Паспорт дата: -2026-11-03",
    "Акт от 03.11.2026...99", "Акт от 2026-11-03--", "Акт от 2026-11-03a",
    "Акт от 03.11.2026а", "Акт от --2026-11-03", "Акт от 03.11.2026.0.0",
    "Акт дата: 2026-11-03_99", "Акт от 2026-11-03.№99", "Акт от 2026-11-03,99",
    "Акт от 2026-11-03--04-11-2026", "Акт от 2026-11-03..", "Акт от 03.11.2026,-99",
    "Акт от 03/11/2026", "Акт от 29.02.2100",
)
VALID_DATES = (
    "Акт проверки от 29.02.2024", "Паспорт дата 2024-02-29", "Акт от 03.11.2026.",
    "Паспорт от 2026-11-03, дефектов нет", "Свидетельство от 03.11.2026; замечаний нет",
    "Акт проверки от 03.11.2026. Дефектов нет", "Паспорт дата: 3.11.2026",
    "Акт от 29.02.2000", "Паспорт от 2026-11-03. ",
)
NATURAL_TITLES = (
    "Акт проверки и испытаний №42", "Паспорт четырёхветвевого стропа №123",
    "Акт приёмки и контрольных испытаний номер 42", "Паспорт цепного четырёхветвевого стропа N123",
    "Акт внеочередной технической проверки ID ACT-42", "Паспорт канатного стропа шифр ПС-123",
    "Акт приёмо-сдаточных испытаний рег. №РП-42", "Протокол очередных и повторных испытаний №TEST-ABC",
    "Сертификат соответствия грузозахватных приспособлений номер TR-123",
    "Паспорт текстильного двухветвевого стропа №123. Дефектов нет",
    "Акт визуального осмотра и проверки №42", "Паспорт стропов общего назначения №123",
    "Акт приёма-передачи грузозахватных приспособлений №ПП-123",
    "Паспорт для канатного четырехветвевого стропа №123",
    "Протокол безопасной эксплуатации и осмотра ID TEST-ABC",
    "Свидетельство о выполненной внеочередной проверке рег. номер РП-42",
    "Акт периодической проверки N.42", "Паспорт многоветвевого грузового стропа номер 123",
    "Паспорт: четырёхветвевого стропа №123", "Паспорт четырёхветвевого стропа (№123)",
    "Акт проверки и испытаний: №42",
)
UNLINKED_OR_MISSING = (
    "Акт проверки; и испытаний №42", "Паспорт четырёхветвевого. Стропа №123",
    "Акт проверки, и испытаний №42", "Паспорт четырёхветвевого стропа\n№123",
    "Акт проверки и испытаний отсутствует №42", "Паспорт непроверенного четырёхветвевого стропа №123",
    "Акт проверки и испытаний №42 отсутствует", "Паспорт четырёхветвевого стропа №123 нет",
    "Акт проверки и испытаний 42", "Паспорт четырёхветвевого стропа 123",
    "Акт проверки и испытаний — №42",
    "Акт проверки и испытаний (замечаний 0) №42",
)


class Round8Tests(unittest.TestCase):
    assert_documents = r7.Round7Tests.assert_documents
    assert_gui_atomic_rejection = r2.Round2Tests.assert_gui_atomic_rejection

    def test_entire_malformed_date_token_cannot_supply_document_identity(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_documents(project, scenario, INVALID_DATES, False)

    def test_complete_calendar_dates_and_sentence_punctuation_are_supported(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_documents(project, scenario, VALID_DATES, True)

    def test_explicit_references_accept_natural_same_clause_document_titles(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_documents(project, scenario, NATURAL_TITLES, True)

    def test_explicit_title_reference_cannot_cross_clauses_or_hide_missing_evidence(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_documents(project, scenario, UNLINKED_OR_MISSING, False)

    def test_bad_date_cards_are_pending_and_all_advanced_gui_saves_are_atomic(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate(INVALID_DATES[:3]):
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

    def test_natural_title_and_leap_date_controls_reach_physical_gui_production(self):
        controls = (NATURAL_TITLES[0], NATURAL_TITLES[1], VALID_DATES[0])
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate(controls):
                    with self.subTest(value=value):
                        project, scenario = r2.ready(root / str(index) / "fixture")
                        project.loads[0].sling_identification = "Строп 4СК-5,0 №123"
                        project.loads[0].rigging_evidence = value
                        project.pprk_release.status = ReleaseStatus.PRODUCTION
                        checked = r2.verify(project, scenario)
                        try:
                            require_saveable_release(prepare_release(project, scenario, checked), checked)
                        except ValueError as error:
                            self.fail(f"Complete linked title/date must be eligible: {error}")
                        output = r2.save_via_gui(project, scenario, checked, root / str(index) / "production")
                        card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                        self.assertIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                        self.assertIn(value, card)
                        self.assertIn("Строп 4СК-5,0 №123", card)
                        self.assertNotIn("НЕ ЗАПОЛНЕНО", card)


if __name__ == "__main__":
    unittest.main()

