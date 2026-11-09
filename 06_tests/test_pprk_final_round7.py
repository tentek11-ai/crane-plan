"""A document reference links its identity, never an incidental numeric metric."""
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
from crane_plan.project_io import save_project, load_project


METRICS = (
    "Паспорт: дефектов 0", "Акт проверки (замечаний 0)", "Паспорт: дефектов 12",
    "Акт проверки замечаний 3", "Протокол испытаний (дефектов 0)",
    "Паспорт масса 500 кг", "Паспорт масса 5,0 т", "Паспорт грузоподъёмность 5,0",
    "Паспорт стропа 4СК-5,0", "Паспорт 5,0", "Паспорт 5 кг", "Паспорт 12 страниц",
    "Протокол страниц 5", "Сертификат листов 12", "Акт 4 проверки", "Акт проверки 5",
    "Паспорт 0", "Паспортов 5", "Протоколов 7", "Количество: паспорт 5",
    "Паспорт год выпуска 2026", "Акт температура 20", "Паспорт температура T20",
    "Паспорт дата осмотра 03.11.2026", "Паспорт: осмотр от 03.11.2026",
    "Паспорт: номер страниц 5", "Паспорт: номер стропа 4СК-5,0", "Акт проверки ID замечаний 0",
    "Паспорт №5,0", "Паспорт №4СК-5,0", "Акт от 0", "Акт от 31.02.2026",
    "Паспорт дата 13.13.2026", "Паспорт масса 5,0 кг №123",
    "Акт проверки (замечаний 0) от 03.11.2026", "Паспорт номер массы 500",
)
REFERENCES = (
    "Паспорт №123. Дефектов нет", "Акт №42 от 03.11.2026", "Акт проверки от 03.11.2026",
    "Протокол №TEST-ABC: рисков нет", "Паспорт номер 123", "Паспорт номер123",
    "Паспорт N123", "Паспорт N.123", "Паспорт ID PS-123", "Паспорт шифр ПС-123",
    "Паспорт рег. номер РП-42", "Паспорт регистрационный номер РП-42",
    "Сертификат №TR-ABC", "Свидетельство от 2026-11-03", "Паспорт дата: 03.11.2026",
    "По паспорту №123", "Протокол испытаний (№42)",
    "Паспорт №123 (дефектов 0)", "Паспорт №123. Масса 5,0 кг",
    "Испытательный паспорт 123", "Паспорт 123, испытание 04.11.2026",
    "Паспорт: ПРОВЕРЕННЫЙ №42", "ПАСПОРТ №１２３",
    "Паспорт рег. №42", "Паспорт рег. №РП-42",
)


class Round7Tests(unittest.TestCase):
    assert_gui_atomic_rejection = r2.Round2Tests.assert_gui_atomic_rejection

    def assert_documents(self, project, scenario, values, expected):
        checked = r2.verify(project, scenario)
        for value in values:
            with self.subTest(value=value):
                changed = deepcopy(project)
                changed.loads[0].rigging_evidence = value
                self.assertEqual(build_pprk_context(changed, scenario, checked).active_loads[0].confirmed, expected)

    def test_numeric_metrics_and_unlinked_dates_are_not_document_identity(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            self.assert_documents(project, scenario, METRICS, False)

    def test_explicit_reference_links_dates_and_direct_legacy_defaults_are_supported(self):
        with TemporaryDirectory() as tmp:
            project, scenario = r2.ready(Path(tmp) / "fixture")
            project.loads[0].sling_identification = "Строп 4СК-5,0 №123"
            self.assert_documents(project, scenario, REFERENCES, True)

    def test_loaded_metric_text_and_checkbox_are_preserved_without_inventing_identity(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, value in enumerate(METRICS[:2]):
                with self.subTest(value=value):
                    project, scenario = r2.ready(root / str(index) / "fixture")
                    project.loads[0].rigging_evidence = value
                    path = save_project(root / str(index) / "saved", project)
                    before = path.read_bytes()
                    loaded = load_project(path)
                    self.assertEqual(loaded.loads[0].rigging_evidence, value)
                    self.assertIs(loaded.loads[0].rigging_verified, True)
                    self.assertFalse(build_pprk_context(loaded, scenario, r2.verify(loaded, scenario)).active_loads[0].confirmed)
                    self.assertEqual(path.read_bytes(), before)

    def test_exact_metric_cards_are_pending_drafts_and_all_advanced_saves_are_atomic(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with verified_registry(root):
                for index, value in enumerate((METRICS[0], METRICS[1], "Паспорт грузоподъёмность 5,0")):
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
                            self.assertTrue(any(issue.code == "PPRK_RIGGING_EVIDENCE_REQUIRED" for issue in release.bundle.completeness_issues))
                            with self.assertRaises(ValueError):
                                require_saveable_release(release, checked)

    def test_named_reference_controls_reach_confirmed_physical_production(self):
        controls = ("Паспорт №123. Дефектов нет", "Акт №42 от 03.11.2026",
                    "Акт проверки от 03.11.2026", "Протокол №TEST-ABC: рисков нет")
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
                            self.fail(f"A linked document identity must be eligible: {error}")
                        output = r2.save_via_gui(project, scenario, checked, root / str(index) / "production")
                        card = next(p.extract_text() for p in PdfReader(output).pages if p.extract_text().startswith("Строповка:"))
                        self.assertIn("Подтверждение исходных данных\nПОДТВЕРЖДЕНО", card)
                        self.assertIn(value, card)
                        self.assertIn("Строп 4СК-5,0 №123", card)
                        self.assertNotIn("НЕ ЗАПОЛНЕНО", card)


if __name__ == "__main__":
    unittest.main()
