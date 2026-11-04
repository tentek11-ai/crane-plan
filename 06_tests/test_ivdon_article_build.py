from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from docx import Document
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "08_dissertation" / "04_article_1_crane_placement"
SCRIPT = ROOT / "04_experiments" / "build_ivdon_article_revision.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("ivdon_builder_for_docx", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load article builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IvDonArticleBuildTests(unittest.TestCase):
    def test_builds_article_and_editor_response_docx(self):
        builder = load_builder()
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            output = Path(temporary)
            files = builder.build_documents(ARTICLE, output)
            self.assertEqual(len(files), 2)
            for path in files:
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 10_000)

            article = Document(files[0])
            text = "\n".join(p.text for p in article.paragraphs)
            self.assertIn("Математическая модель", text)
            self.assertIn("Список литературы", text)
            self.assertIn("16 из 16", text)
            self.assertGreaterEqual(len(article.tables), 1)
            self.assertAlmostEqual(article.sections[0].page_width.mm, 210, places=1)

            response = Document(files[1])
            response_text = "\n".join(p.text for p in response.paragraphs)
            self.assertIn("Ответ на замечания редакции", response_text)
            self.assertIn("Обзор литературы", response_text)

    def test_builds_readable_a4_article_pdf(self):
        builder = load_builder()
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            output = Path(temporary) / "article.pdf"
            builder.build_article_pdf(ARTICLE, output)
            reader = PdfReader(output)
            self.assertGreaterEqual(len(reader.pages), 5)
            first = reader.pages[0]
            self.assertAlmostEqual(float(first.mediabox.width), 595.28, places=1)
            self.assertAlmostEqual(float(first.mediabox.height), 841.89, places=1)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Математическая модель", text)
            self.assertIn("16 из 16", text)
            self.assertNotIn("PPRK-005", text)


if __name__ == "__main__":
    unittest.main()
