from __future__ import annotations

import re
import subprocess
import unittest
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTICLE_ROOT = ROOT / "08_dissertation" / "04_article_1_crane_placement"
PRIVATE_EVIDENCE = ROOT / "11_backups" / "article_1_evidence_private"

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")


def public_article_files(root: Path) -> list[Path]:
    suffixes = {".md", ".csv", ".json", ".txt"}
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


class ArticleEvidenceHygieneTests(unittest.TestCase):
    def test_private_evidence_directory_is_git_ignored(self):
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(PRIVATE_EVIDENCE)],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_public_article_tree_contains_no_email_or_phone(self):
        violations: list[str] = []
        for path in public_article_files(ARTICLE_ROOT):
            text = path.read_text(encoding="utf-8")
            if EMAIL_RE.search(text) or PHONE_RE.search(text):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(violations, [])

    def test_editorial_matrix_covers_all_rejection_reasons(self):
        matrix = ARTICLE_ROOT / "EDITORIAL_RESPONSE_MATRIX.md"
        terminology = ARTICLE_ROOT / "TERMINOLOGY.md"
        self.assertTrue(matrix.is_file(), "editorial response matrix is missing")
        self.assertTrue(terminology.is_file(), "terminology rules are missing")

        matrix_text = matrix.read_text(encoding="utf-8")
        required_codes = {
            "LITERATURE_REVIEW",
            "ABBREVIATION",
            "OBJECT_DESCRIPTION",
            "UNSUPPORTED_CLAIMS",
        }
        present_codes = set(re.findall(r"`([A-Z_]+)`", matrix_text))
        self.assertTrue(required_codes.issubset(present_codes))

        terminology_text = terminology.read_text(encoding="utf-8")
        self.assertIn("аннотации", terminology_text.lower())
        self.assertIn("основном тексте", terminology_text.lower())
        self.assertIn("проект производства работ кранами (ППРк)", terminology_text)

    def test_case_manifests_have_fixed_validation_statuses(self):
        expected_statuses = {
            "PPRK-005": "retrospective",
            "PPRK-006": "retrospective",
            "PPRK-007": "independent_pilot_accepted_for_implementation",
        }
        for case_id, expected_status in expected_statuses.items():
            path = ARTICLE_ROOT / "cases" / case_id / "case_manifest.json"
            self.assertTrue(path.is_file(), f"missing manifest for {case_id}")
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["case_id"], case_id)
            self.assertEqual(manifest["validation_status"], expected_status)
            for key in (
                "address_publication_status",
                "building",
                "site",
                "crane",
                "critical_operations",
                "source_files",
            ):
                self.assertIn(key, manifest)

    def test_numeric_source_values_have_units_and_locators(self):
        for case_id in ("PPRK-005", "PPRK-006", "PPRK-007"):
            path = ARTICLE_ROOT / "cases" / case_id / "source_register.csv"
            self.assertTrue(path.is_file(), f"missing source register for {case_id}")
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertGreater(len(rows), 0)
            for row in rows:
                self.assertIn(row["status"], {"CONFIRMED", "DIGITIZED", "USER_DEFINED", "UNKNOWN", "NOT_APPLICABLE"})
                if row["status"] == "UNKNOWN":
                    self.assertIn(row["value"], {"", "UNKNOWN"})
                    continue
                try:
                    float(row["value"].replace(",", "."))
                except ValueError:
                    continue
                self.assertTrue(row["unit"].strip(), f"numeric value lacks unit: {case_id}/{row['parameter']}")
                self.assertTrue(row["locator"].strip(), f"numeric value lacks locator: {case_id}/{row['parameter']}")

    def test_author_reported_2026_implementation_is_identity_specific(self):
        expected = {
            "PPRK-005": "Малый Знаменский",
            "PPRK-007": "Новаторов",
        }
        for case_id, address_fragment in expected.items():
            path = ARTICLE_ROOT / "cases" / case_id / "case_manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn(address_fragment, manifest["publication_address"])
            self.assertEqual(manifest["implementation"]["year"], 2026)
            self.assertEqual(
                manifest["implementation"]["status"],
                "AUTHOR_REPORTED_PENDING_DOCUMENTARY_CONFIRMATION",
            )
            self.assertRegex(
                manifest["implementation"]["attestation_sha256"],
                r"^[0-9a-f]{64}$",
            )


if __name__ == "__main__":
    unittest.main()
