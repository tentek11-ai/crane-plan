import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_portable_release import build_portable_release  # noqa: E402


class PortableReleaseBuilderTests(unittest.TestCase):
    def test_build_contains_application_runtime_library_and_no_bytecode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            runtime = Path(tmp) / "runtime"
            output = Path(tmp) / "exports"
            for relative in (
                "02_processed_data/cranes",
                "05_src/crane_plan/__pycache__",
                "library/cranes",
                "07_docs",
            ):
                (root / relative).mkdir(parents=True, exist_ok=True)
            (root / "02_processed_data/cranes/catalog.json").write_text("{}", encoding="utf-8")
            (root / "05_src/main.py").write_text("print('ok')", encoding="utf-8")
            (root / "05_src/crane_plan/__pycache__/ignored.pyc").write_bytes(b"cache")
            (root / "library/cranes/manifest.json").write_text("{}", encoding="utf-8")
            (root / "07_docs/USER_GUIDE.md").write_text("guide", encoding="utf-8")
            (root / "README.md").write_text("readme", encoding="utf-8")
            (root / "requirements-lock.txt").write_text("", encoding="utf-8")
            (root / "VERSION").write_text("2.1.0\n", encoding="utf-8")
            (root / "Запустить КранПлан.bat").write_text("@echo off", encoding="utf-8")
            runtime.mkdir()
            (runtime / "python.exe").write_bytes(b"runtime")

            release_dir, archive = build_portable_release(root, runtime, output)

            self.assertEqual(release_dir.name, "CranePlan_Portable_2.1.0")
            self.assertTrue((release_dir / "app/05_src/main.py").is_file())
            self.assertTrue((release_dir / "app/library/cranes/manifest.json").is_file())
            self.assertTrue((release_dir / "runtime/python.exe").is_file())
            self.assertTrue((release_dir / "Руководство пользователя.md").is_file())
            self.assertFalse((release_dir / "app/05_src/crane_plan/__pycache__").exists())
            self.assertTrue(archive.is_file())
            with zipfile.ZipFile(archive) as package:
                names = set(package.namelist())
            self.assertIn(
                "CranePlan_Portable_2.1.0/app/05_src/main.py",
                names,
            )

    def test_missing_required_input_does_not_leave_partial_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            runtime = Path(tmp) / "runtime"
            output = Path(tmp) / "exports"
            (root / "02_processed_data").mkdir(parents=True)
            (root / "05_src").mkdir()
            (root / "VERSION").write_text("2.1.0\n", encoding="utf-8")
            runtime.mkdir()
            (runtime / "python.exe").write_bytes(b"runtime")

            with self.assertRaises(FileNotFoundError):
                build_portable_release(root, runtime, output)

            self.assertFalse((output / "CranePlan_Portable_2.1.0").exists())


if __name__ == "__main__":
    unittest.main()
