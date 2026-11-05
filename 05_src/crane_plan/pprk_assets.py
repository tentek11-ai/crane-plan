"""Verified, unretouched reference clips. Crop boxes use top-left PDF points.

``verified`` means a human/visual review of the exact hashed PNG was completed.
The validator checks machine-readable text only; it does not perform OCR.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath

from PIL import Image


ASSET_ROOT = Path(__file__).parent / "assets" / "pprk"
FORBIDDEN_STRINGS = ("ППР ЦЕНТР", "27.06-23", "AUTODESK EDUCATIONAL PRODUCT")
CATEGORIES = frozenset({"slinging", "fencing", "safety_signs", "hand_signals", "storage", "protective_screens"})


@dataclass(frozen=True)
class PPRKAssetRecord:
    asset_id: str
    title: str
    category: str
    file_name: str
    source_page: int
    crop_box: tuple[float, float, float, float]
    sha256: str
    pixel_width: int
    pixel_height: int
    source_kind: str
    quality_status: str


@dataclass(frozen=True)
class AssetIssue:
    asset_id: str
    code: str
    message: str


def forbidden_text(text: str) -> bool:
    normalized = " ".join(text.upper().split())
    return any(value in normalized for value in FORBIDDEN_STRINGS)


def safe_asset_path(root: Path, file_name: str) -> Path:
    """Reject traversal, Windows drives/streams and symlink escapes on any OS."""
    if not isinstance(file_name, str) or not file_name or "\\" in file_name or ":" in file_name:
        raise ValueError("Expected a safe relative PNG path")
    relative = PurePosixPath(file_name)
    if relative.is_absolute() or PureWindowsPath(file_name).drive or ".." in relative.parts:
        raise ValueError("Expected a safe relative PNG path")
    if relative.suffix.lower() != ".png":
        raise ValueError("Only PNG reference clips are accepted")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Asset path escapes the library")
    return path


def load_asset_manifest(manifest: Path | None = None) -> tuple[PPRKAssetRecord, ...]:
    """Load an exact-field JSON record array; malformed input raises ValueError."""
    data = json.loads((manifest or ASSET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    expected = {field.name for field in fields(PPRKAssetRecord)}
    if not isinstance(data, list) or not data:
        raise ValueError("Manifest must contain a nonempty record array")
    result = []
    for row in data:
        if not isinstance(row, dict) or set(row) != expected:
            raise ValueError("Manifest record fields do not match the asset contract")
        if not isinstance(row["crop_box"], list) or len(row["crop_box"]) != 4:
            raise ValueError("crop_box must contain four PDF point coordinates")
        result.append(PPRKAssetRecord(**{**row, "crop_box": tuple(row["crop_box"])}))
    return tuple(result)


def validate_asset_library(root: Path) -> list[AssetIssue]:
    """Fail closed for invalid records, files, resolution or detectable contamination.

    Usable resolution requires both sides >=300 pixels and >=144 dpi in each
    crop direction. Extraction uses 300 dpi. Raster-only text needs visual QA.
    """
    issues: list[AssetIssue] = []
    try:
        records = load_asset_manifest(Path(root) / "manifest.json")
    except (OSError, ValueError, TypeError) as exc:
        return [AssetIssue("", "manifest", str(exc))]
    ids = set()
    for record in records:
        def issue(code: str, message: str) -> None:
            issues.append(AssetIssue(str(record.asset_id), code, message))

        if not isinstance(record.asset_id, str) or not record.asset_id.strip():
            issue("asset_id", "Asset ID must be a nonempty string")
        elif record.asset_id in ids:
            issue("duplicate_id", "Asset ID must be unique")
        else:
            ids.add(record.asset_id)
        if not isinstance(record.title, str) or not record.title.strip():
            issue("title", "Asset title must be a nonempty string")
        if not isinstance(record.category, str) or record.category not in CATEGORIES:
            issue("category", "Unknown asset category")
        if forbidden_text(json.dumps(record.__dict__, ensure_ascii=False)):
            issue("forbidden_text", "Forbidden source text in manifest")
        if type(record.source_page) is not int or record.source_page < 1:
            issue("source_page", "Source pages are one-based positive integers")
        box = record.crop_box
        valid_box = all(type(v) in (int, float) and math.isfinite(v) for v in box)
        valid_box = valid_box and 0 <= box[0] < box[2] and 0 <= box[1] < box[3]
        if not valid_box:
            issue("crop_box", "Invalid top-left PDF point crop box")
        if record.source_kind != "reference_clip":
            issue("source_kind", "Only unchanged reference clips are accepted")
        if record.quality_status != "verified":
            issue("quality", "Visual review has not accepted this clip")
        dimensions = (record.pixel_width, record.pixel_height)
        if any(type(v) is not int or v <= 0 for v in dimensions):
            issue("dimensions", "Pixel dimensions must be positive integers")
        try:
            path = safe_asset_path(Path(root), record.file_name)
        except (ValueError, OSError) as exc:
            issue("unsafe_path", str(exc))
            continue
        if not path.is_file():
            issue("missing_file", "Referenced clip is missing")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.sha256:
            issue("checksum", "Clip does not match the verified SHA-256")
        try:
            with Image.open(path) as image:
                image.load()
                if image.format != "PNG":
                    issue("unreadable_image", "Clip must be a PNG image")
                if image.size != dimensions:
                    issue("dimensions", "Actual and manifest dimensions differ")
                if min(image.size) < 300 or (valid_box and (
                        image.width / (box[2] - box[0]) < 2 or
                        image.height / (box[3] - box[1]) < 2)):
                    issue("resolution", "Clip is below minimum usable resolution")
                if forbidden_text(str(image.info)):
                    issue("forbidden_text", "Forbidden source text in image metadata")
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            issue("unreadable_image", str(exc))
    return issues

