import json
import tempfile
import unittest
from pathlib import Path

from crane_plan.library import load_library, resolve_local_file


class LibraryTests(unittest.TestCase):
    def test_manifest_entries_resolve_to_local_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library_root = root / "library" / "cranes"
            document = library_root / "brochures" / "crane.pdf"
            document.parent.mkdir(parents=True)
            document.write_bytes(b"%PDF-local-test")
            (library_root / "manifest.json").write_text(
                json.dumps({"entries": [{"local_file": "brochures/crane.pdf"}]}),
                encoding="utf-8",
            )

            loaded_root, data = load_library(root, "cranes")

            self.assertEqual(len(data["entries"]), 1)
            resolved = resolve_local_file(loaded_root, data["entries"][0]["local_file"])
            self.assertEqual(resolved, document.resolve())
            self.assertTrue(resolved.is_file())

    def test_path_traversal_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                resolve_local_file(root, "../outside.pdf")

    def test_invalid_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_dir = root / "library" / "cranes"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "manifest.json").write_text(json.dumps({"entries": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_library(root, "cranes")


if __name__ == "__main__":
    unittest.main()
