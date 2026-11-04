import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.app import APP_TITLE  # noqa: E402
from crane_plan.engine.service import ENGINE_VERSION  # noqa: E402


class VersionConsistencyTests(unittest.TestCase):
    def test_release_engine_and_window_title_use_the_same_version(self):
        release_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

        self.assertEqual(release_version, ENGINE_VERSION)
        self.assertIn(release_version, APP_TITLE)


if __name__ == "__main__":
    unittest.main()
