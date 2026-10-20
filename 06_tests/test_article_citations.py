from __future__ import annotations

import csv
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LITERATURE_ROOT = (
    ROOT / "08_dissertation" / "04_article_1_crane_placement" / "literature"
)


class ArticleCitationTests(unittest.TestCase):
    def setUp(self):
        matrix_path = LITERATURE_ROOT / "LITERATURE_MATRIX.csv"
        self.assertTrue(matrix_path.is_file(), "literature matrix is missing")
        with matrix_path.open(encoding="utf-8", newline="") as handle:
            self.rows = list(csv.DictReader(handle))

    def test_used_source_set_meets_journal_minimums(self):
        used = [row for row in self.rows if row["used"].lower() == "yes"]
        self.assertGreaterEqual(len(used), 10)
        self.assertGreaterEqual(
            sum(row["language"].lower() == "english" for row in used), 2
        )
        self.assertLessEqual(
            sum(row["self_citation"].lower() == "yes" for row in used) / len(used),
            0.30,
        )

    def test_substantive_claims_have_verified_primary_locators(self):
        for row in self.rows:
            if row["used"].lower() != "yes":
                continue
            self.assertEqual(row["verification_status"], "VERIFIED_PRIMARY")
            self.assertTrue(row["verified_locator"].strip(), row["source_id"])
            self.assertTrue(row["article_claim"].strip(), row["source_id"])

    def test_citation_groups_are_claim_specific_and_have_at_most_three_sources(self):
        plan_path = LITERATURE_ROOT / "CITATION_PLAN.md"
        self.assertTrue(plan_path.is_file(), "citation plan is missing")
        text = plan_path.read_text(encoding="utf-8")
        groups = re.findall(r"\{cite:\s*(CORE-\d{3}[^}]*)\}", text)
        self.assertGreaterEqual(len(groups), 8)
        for group in groups:
            source_ids = re.findall(r"CORE-\d{3}", group)
            self.assertGreaterEqual(len(source_ids), 1)
            self.assertLessEqual(len(source_ids), 3, group)


if __name__ == "__main__":
    unittest.main()
