from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "08_dissertation" / "04_article_1_crane_placement"
SCRIPT = ROOT / "04_experiments" / "build_ivdon_article_revision.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("ivdon_builder", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load article builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IvDonArticleClaimTests(unittest.TestCase):
    def setUp(self):
        self.builder = load_builder()
        self.evidence = {
            "retrospective": json.loads(
                (ARTICLE / "results" / "external_validation_attestation.json").read_text(encoding="utf-8")
            ),
            "novatorov": json.loads(
                (ARTICLE / "results" / "novatorov_v222_result.json").read_text(encoding="utf-8")
            ),
        }

    def test_public_manuscript_satisfies_claim_gate(self):
        manuscript = (ARTICLE / "manuscript" / "ARTICLE_RU.md").read_text(encoding="utf-8")
        self.assertEqual(self.builder.validate_article_claims(manuscript, self.evidence), [])

    def test_gate_rejects_internal_codes_raw_status_and_implementation_claim(self):
        bad = (
            "PPRK-005. PASS_WITH_CONDITIONS. Однокрановая схема внедрена и принята для реализации. "
            "Стоимость решения снижена."
        )
        errors = self.builder.validate_article_claims(bad, self.evidence)
        self.assertGreaterEqual(len(errors), 4)

    def test_duration_requires_lift_set_context(self):
        errors = self.builder.validate_article_claims("Расчет занял 1,774 дня.", self.evidence)
        self.assertTrue(any("160" in item for item in errors))

    def test_required_claim_and_three_named_objects_are_present(self):
        manuscript = (ARTICLE / "manuscript" / "ARTICLE_RU.md").read_text(encoding="utf-8")
        required = [
            "разработана и верифицирована на трех реальных объектах математическая модель",
            "Объект в Малом Знаменском переулке, г. Москва",
            "Строительство пристройки на 200 мест к зданию МОУ Карцевская школа",
            "Строительство неонатального корпуса на 76 коек",
            "решение допустимо при выполнении установленных условий безопасности",
            "письменн",
        ]
        lowered = manuscript.lower()
        for phrase in required:
            self.assertIn(phrase.lower(), lowered)


if __name__ == "__main__":
    unittest.main()
