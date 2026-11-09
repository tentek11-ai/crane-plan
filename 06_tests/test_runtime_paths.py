import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.runtime_paths import writable_temp_root


class RuntimePathTests(unittest.TestCase):
    def test_default_temp_root_supports_child_directory_creation(self):
        selected = writable_temp_root()

        with tempfile.TemporaryDirectory(dir=selected) as temporary:
            self.assertTrue(Path(temporary).is_dir())

    def test_writable_temp_root_skips_inaccessible_candidate(self):
        test_temp_root = ROOT / "tmp" / "test-temp"
        test_temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_temp_root) as temporary:
            root = Path(temporary)
            blocked = root / "blocked"
            blocked.write_text("this path cannot become a directory", encoding="utf-8")
            fallback = root / "fallback"

            selected = writable_temp_root((blocked, fallback))

            self.assertEqual(selected, fallback)
            self.assertTrue(fallback.is_dir())


if __name__ == "__main__":
    unittest.main()
