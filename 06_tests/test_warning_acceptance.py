import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.models import ProjectInput, SiteInput  # noqa: E402
from crane_plan.recalculation import accept_warning, current_warning_acceptances  # noqa: E402


class WarningAcceptanceTests(unittest.TestCase):
    def test_only_warning_can_be_accepted(self):
        with self.assertRaisesRegex(ValueError, "(?i)блокир"):
            accept_warning([], "BLOCK-1", "a" * 64, severity="blocker")

    def test_acceptance_is_bound_to_exact_input_hash(self):
        accepted = accept_warning([], "WARN-1", "a" * 64, severity="warning", comment="проверено")
        self.assertEqual(len(current_warning_acceptances(accepted, "a" * 64)), 1)
        self.assertEqual(current_warning_acceptances(accepted, "b" * 64), [])

    def test_empty_comment_is_not_published(self):
        acceptance = accept_warning([], "WARN-1", "a" * 64, severity="warning", comment="   ")[0]
        project = ProjectInput("", "", 2026, "", "", 0, 1, SiteInput([], []), [], [], warning_acceptances=[acceptance])
        self.assertEqual(
            project.to_dict()["warning_acceptances"],
            [{"warning_id": "WARN-1", "input_sha256": "a" * 64}],
        )


if __name__ == "__main__":
    unittest.main()
