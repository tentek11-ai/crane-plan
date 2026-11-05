"""Extract unretouched 300 dpi PNG clips; never copy or modify the source PDF.

Manifest pages are one-based; crop_box is (left, top, right, bottom) in PDF
points in the displayed page orientation. Extraction preserves visual approval
only for bytes matching the approved input SHA-256. A changed clip is rejected
before publication and requires a new visual review and approved manifest hash.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile

import pypdfium2 as pdfium

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "05_src"))
from crane_plan.pprk_assets import (  # noqa: E402
    forbidden_text, load_asset_manifest, safe_asset_path, validate_asset_library,
)


def extract(source_pdf: Path, manifest: Path, output_dir: Path) -> None:
    records = load_asset_manifest(manifest)
    # Preflight before touching any output. No files are published on failure.
    with tempfile.TemporaryDirectory() as temporary, pdfium.PdfDocument(source_pdf) as pdf:
        staging = Path(temporary)
        result = []
        for record in records:
            destination = safe_asset_path(staging, record.file_name)
            if not 1 <= record.source_page <= len(pdf):
                raise ValueError(f"Invalid source page: {record.asset_id}")
            with closing(pdf[record.source_page - 1]) as page:
                width, height = page.get_size()
                left, top, right, bottom = record.crop_box
                if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                    raise ValueError(f"Crop outside page: {record.asset_id}")
                with closing(page.get_textpage()) as textpage:
                    text = textpage.get_text_bounded(left, height - bottom, right, height - top)
                    if forbidden_text(text):
                        raise ValueError(f"Forbidden text in crop: {record.asset_id}")
                # PDFium crops before rendering; no redrawing, erasing or retouching.
                bitmap = page.render(scale=300 / 72,
                                     crop=(left, height - bottom, width - right, top))
                image = bitmap.to_pil()
                destination.parent.mkdir(parents=True, exist_ok=True)
                image.save(destination, format="PNG", optimize=False, compress_level=9)
                actual_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
                dimensions = (image.width, image.height)
                bitmap.close()
                if actual_hash != record.sha256:
                    raise ValueError(
                        f"Visual review required for changed clip {record.asset_id}; "
                        f"candidate SHA-256: {actual_hash}. Update the approved manifest "
                        "hash only after reviewing the new clip. No files were published."
                    )
                result.append({**asdict(record), "pixel_width": dimensions[0],
                               "pixel_height": dimensions[1]})
        content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        (staging / "manifest.json").write_text(content, encoding="utf-8")
        issues = validate_asset_library(staging)
        if issues:
            raise ValueError("; ".join(f"{i.asset_id}: {i.code}: {i.message}" for i in issues))
        # Do not overwrite the PDF or an input manifest with extracted data.
        for path in staging.rglob("*"):
            if path.is_file():
                target = output_dir / path.relative_to(staging)
                if target.resolve() == source_pdf.resolve():
                    raise ValueError("Output would overwrite source PDF")
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                target = output_dir / path.relative_to(staging)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pdf", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        extract(args.source_pdf, args.manifest, args.output_dir)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Extraction failed: {exc}\n")


if __name__ == "__main__":
    main()

