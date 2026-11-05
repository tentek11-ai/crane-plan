import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, PngImagePlugin


ROOT = Path(__file__).resolve().parents[1]


class PPRKAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new('RGB', (900, 600), 'white').save(self.root / 'clip.png')
        self.record = dict(asset_id='slinging', title='Строповка', category='slinging',
                           file_name='clip.png', source_page=51, crop_box=[0, 0, 300, 200],
                           sha256=hashlib.sha256((self.root / 'clip.png').read_bytes()).hexdigest(),
                           pixel_width=900, pixel_height=600, source_kind='reference_clip',
                           quality_status='verified')

    def validate(self, records=None):
        from crane_plan.pprk_assets import validate_asset_library
        (self.root / 'manifest.json').write_text(json.dumps(
            records if records is not None else [self.record], ensure_ascii=False), encoding='utf-8')
        return validate_asset_library(self.root)

    def test_valid_clip_and_default_library(self):
        from crane_plan.pprk_assets import load_asset_manifest, validate_asset_library
        self.assertEqual(self.validate(), [])
        records = load_asset_manifest()
        self.assertTrue(records)
        self.assertEqual({r.category for r in records}, {
            'slinging', 'fencing', 'safety_signs', 'hand_signals', 'storage', 'protective_screens'})
        self.assertEqual(validate_asset_library(ROOT / '05_src/crane_plan/assets/pprk'), [])

    def test_rejects_duplicate_ids(self):
        self.assertIn('duplicate_id', {i.code for i in self.validate([self.record, self.record])})

    def test_rejects_unsafe_paths(self):
        for filename in ['../clip.png', '/clip.png', 'C:/clip.png', '..\\clip.png', 'clip.png:stream']:
            with self.subTest(filename=filename):
                self.record['file_name'] = filename
                self.assertIn('unsafe_path', {i.code for i in self.validate()})

    def test_rejects_missing_tampered_and_unreadable_files(self):
        (self.root / 'clip.png').unlink()
        self.assertIn('missing_file', {i.code for i in self.validate()})
        (self.root / 'clip.png').write_bytes(b'not an image')
        codes = {i.code for i in self.validate()}
        self.assertIn('checksum', codes)
        self.assertIn('unreadable_image', codes)

    def test_rejects_dimensions_resolution_and_unverified_quality(self):
        for key, value, code in [('pixel_width', 0, 'dimensions'),
                                 ('pixel_height', 700, 'dimensions'),
                                 ('quality_status', 'unreadable', 'quality'),
                                 ('source_page', 0, 'source_page'),
                                 ('crop_box', [0, 0, 0, 2], 'crop_box'),
                                 ('source_kind', 'generated', 'source_kind')]:
            with self.subTest(key=key):
                original = self.record[key]
                self.record[key] = value
                self.assertIn(code, {i.code for i in self.validate()})
                self.record[key] = original
        Image.new('RGB', (100, 100)).save(self.root / 'clip.png')
        self.record.update(pixel_width=100, pixel_height=100,
                           sha256=hashlib.sha256((self.root / 'clip.png').read_bytes()).hexdigest())
        self.assertIn('resolution', {i.code for i in self.validate()})

    def test_rejects_forbidden_manifest_and_png_metadata(self):
        for text in ['ППР ЦЕНТР', '27.06-23', 'AUTODESK EDUCATIONAL PRODUCT']:
            with self.subTest(text=text):
                self.record['title'] = text
                self.assertIn('forbidden_text', {i.code for i in self.validate()})
        self.record['title'] = 'Строповка'
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('Comment', 'AUTODESK EDUCATIONAL PRODUCT')
        Image.new('RGB', (900, 600)).save(self.root / 'clip.png', pnginfo=metadata)
        self.record['sha256'] = hashlib.sha256((self.root / 'clip.png').read_bytes()).hexdigest()
        self.assertIn('forbidden_text', {i.code for i in self.validate()})

    def test_rejects_malformed_manifest_without_crashing(self):
        from crane_plan.pprk_assets import validate_asset_library
        for value in ['{', '{}', '[{}]', '[]']:
            with self.subTest(value=value):
                (self.root / 'manifest.json').write_text(value, encoding='utf-8')
                self.assertTrue(validate_asset_library(self.root))
        self.record['category'] = []
        self.assertIn('category', {i.code for i in self.validate()})

    def extraction_inputs(self):
        from reportlab.pdfgen import canvas
        source = self.root / 'source.pdf'
        c = canvas.Canvas(str(source), pagesize=(400, 400))
        c.drawString(20, 370, 'AUTODESK EDUCATIONAL PRODUCT')
        c.rect(30, 30, 300, 250)
        c.save()
        manifest = self.root / 'input.json'
        # Recorded approved bytes for this controlled PDF/crop with the pinned renderer.
        self.record.update(source_page=1, crop_box=[20, 100, 350, 380],
                           sha256='be2760e13ccb526a24ad52bacf81a18568f4b9caaa6b30204d8d1f1a2beee57e')
        manifest.write_text(json.dumps([self.record]), encoding='utf-8')
        return source, manifest

    def run_extraction(self, source, manifest, output):
        return subprocess.run([sys.executable, str(ROOT / 'tools/extract_pprk_reference_assets.py'),
                               '--source-pdf', str(source), '--manifest', str(manifest),
                               '--output-dir', str(output)], capture_output=True, text=True)

    def test_extraction_cli_reproducible_and_rejects_contaminated_crop(self):
        source, manifest = self.extraction_inputs()
        outputs = []
        for name in ['one', 'two']:
            output = self.root / name
            result = self.run_extraction(source, manifest, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append((output / 'clip.png').read_bytes())
            published = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))[0]
            self.assertEqual(published['sha256'], self.record['sha256'])
            self.assertEqual(published['quality_status'], 'verified')
        self.assertEqual(outputs[0], outputs[1])
        self.record['crop_box'] = [0, 0, 400, 400]
        manifest.write_text(json.dumps([self.record]), encoding='utf-8')
        result = self.run_extraction(source, manifest, self.root / 'bad')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'bad/clip.png').exists())

    def test_extraction_requires_new_visual_approval_for_changed_bytes(self):
        from reportlab.pdfgen import canvas
        for change in ['crop', 'source', 'unapproved_hash']:
            with self.subTest(change=change):
                source, manifest = self.extraction_inputs()
                if change == 'crop':
                    self.record['crop_box'] = [25, 100, 350, 380]
                elif change == 'source':
                    c = canvas.Canvas(str(source), pagesize=(400, 400))
                    c.rect(60, 60, 200, 200)
                    c.save()
                else:
                    self.record['sha256'] = '0' * 64
                manifest.write_text(json.dumps([self.record]), encoding='utf-8')
                output = self.root / change
                output.mkdir()
                (output / 'clip.png').write_bytes(b'previously approved bytes')
                result = self.run_extraction(source, manifest, output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('visual review', result.stderr.lower())
                self.assertEqual((output / 'clip.png').read_bytes(), b'previously approved bytes')
                self.assertFalse((output / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()

