"""Локальная работа с векторными PDF и калибровкой масштаба."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import hypot
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium


MAX_PDF_BYTES = 200 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_RENDER_SCALE = 4.0


def _validate_pdf_file(path: Path) -> None:
    if not path.is_file():
        raise ValueError("PDF-файл не найден")
    if path.stat().st_size > MAX_PDF_BYTES:
        raise ValueError("PDF превышает допустимый размер 200 МБ")


@dataclass(frozen=True)
class PdfInspection:
    path: str
    sha256: str
    pages: int
    vector_lines: int
    vector_rects: int
    text_chars: int
    likely_vector: bool


def inspect_pdf(path: str | Path) -> PdfInspection:
    path = Path(path)
    _validate_pdf_file(path)
    digest_builder = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest_builder.update(chunk)
    digest = digest_builder.hexdigest()
    lines = rects = text_chars = 0
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF содержит более {MAX_PDF_PAGES} страниц")
        for page in pdf.pages:
            lines += len(page.lines) + len(page.curves)
            rects += len(page.rects)
            text_chars += len(page.chars)
        pages = len(pdf.pages)
    return PdfInspection(str(path), digest, pages, lines, rects, text_chars, (lines + rects) >= 10)


def render_page(path: str | Path, page_index: int = 0, scale: float = 1.5):
    path = Path(path)
    _validate_pdf_file(path)
    if scale <= 0 or scale > MAX_RENDER_SCALE:
        raise ValueError(f"Масштаб рендеринга должен быть больше 0 и не более {MAX_RENDER_SCALE}")
    pdf = pdfium.PdfDocument(str(path))
    if len(pdf) > MAX_PDF_PAGES:
        pdf.close()
        raise ValueError(f"PDF содержит более {MAX_PDF_PAGES} страниц")
    page = bitmap = None
    try:
        if page_index < 0 or page_index >= len(pdf):
            raise IndexError("Номер страницы вне диапазона")
        page = pdf[page_index]
        bitmap = page.render(scale=scale)
        return bitmap.to_pil().copy()
    finally:
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        pdf.close()


def calibration_m_per_pixel(p1: tuple[float, float], p2: tuple[float, float], known_distance_m: float) -> float:
    pixel_distance = hypot(p2[0] - p1[0], p2[1] - p1[1])
    if pixel_distance <= 0 or known_distance_m <= 0:
        raise ValueError("Для масштаба нужны две разные точки и положительное расстояние")
    return known_distance_m / pixel_distance


def pixel_to_world(point: tuple[float, float], origin_px: tuple[float, float], m_per_pixel: float) -> tuple[float, float]:
    if m_per_pixel <= 0:
        raise ValueError("Масштаб должен быть положительным")
    return ((point[0] - origin_px[0]) * m_per_pixel, (origin_px[1] - point[1]) * m_per_pixel)


def suggest_vector_bounds(path: str | Path, page_index: int = 0) -> tuple[float, float, float, float]:
    """Предложить рамку чертежа в координатах PDF-точек.

    Это только геометрическая подсказка: рамка листа и штамп могут попасть в
    результат, поэтому пользователь обязан подтвердить или заменить контур.
    """
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[page_index]
        objects = list(page.lines) + list(page.rects) + list(page.curves)
        if not objects:
            raise ValueError("Векторные элементы для автоматического предложения не найдены")
        boxes = []
        for obj in objects:
            x0, x1 = obj.get("x0"), obj.get("x1")
            top, bottom = obj.get("top"), obj.get("bottom")
            if None not in (x0, x1, top, bottom):
                width, height = x1 - x0, bottom - top
                if width < page.width * 0.98 or height < page.height * 0.98:
                    boxes.append((x0, top, x1, bottom))
        if not boxes:
            raise ValueError("Найдена только рамка листа; требуется ручная разметка")
        return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)
