"""Локальная работа с векторными PDF и калибровкой масштаба."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import hypot
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageEnhance, ImageOps


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


@dataclass
class PdfViewportTransform:
    """Независимое от Tk преобразование document <-> view.

    Разметка хранится в координатах документа; zoom и pan влияют
    только на её экранное представление.
    """

    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    def document_to_view(self, point: tuple[float, float]) -> tuple[float, float]:
        return point[0] * self.scale + self.offset_x, point[1] * self.scale + self.offset_y

    def view_to_document(self, point: tuple[float, float]) -> tuple[float, float]:
        if self.scale <= 0:
            raise ValueError("Масштаб вида должен быть положительным")
        return (point[0] - self.offset_x) / self.scale, (point[1] - self.offset_y) / self.scale

    def zoom_at(self, cursor: tuple[float, float], factor: float, minimum: float = 0.1, maximum: float = 8.0) -> None:
        if factor <= 0:
            raise ValueError("Коэффициент масштабирования должен быть положительным")
        document_point = self.view_to_document(cursor)
        self.scale = max(minimum, min(maximum, self.scale * factor))
        self.offset_x = cursor[0] - document_point[0] * self.scale
        self.offset_y = cursor[1] - document_point[1] * self.scale

    def pan_by(self, dx: float, dy: float) -> None:
        self.offset_x += dx
        self.offset_y += dy


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


def normalize_crop_box(crop_box: tuple[float, float, float, float] | list[float] | None) -> tuple[float, float, float, float]:
    """Validate a crop rectangle stored as fractions of the full PDF page."""
    if crop_box is None:
        return (0.0, 0.0, 1.0, 1.0)
    if len(crop_box) != 4:
        raise ValueError("Окно обрезки должно содержать четыре координаты")
    x0, y0, x1, y1 = (max(0.0, min(1.0, float(value))) for value in crop_box)
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1))
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        raise ValueError("Окно обрезки слишком мало; выделите более крупный фрагмент")
    return (x0, y0, x1, y1)


def crop_pixel_box(image_size: tuple[int, int], crop_box=None) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = normalize_crop_box(crop_box)
    width, height = image_size
    return (
        max(0, min(width - 1, round(x0 * width))),
        max(0, min(height - 1, round(y0 * height))),
        max(1, min(width, round(x1 * width))),
        max(1, min(height, round(y1 * height))),
    )


def fade_background(image: Image.Image, intensity: float = 0.35) -> Image.Image:
    """Make a drawing quiet while retaining enough linework for orientation."""
    intensity = float(intensity)
    if not 0.05 <= intensity <= 1.0:
        raise ValueError("Интенсивность подложки должна быть от 0,05 до 1,0")
    gray = ImageOps.grayscale(image).convert("RGB")
    gray = ImageEnhance.Contrast(gray).enhance(0.72)
    white = Image.new("RGB", gray.size, "white")
    return Image.blend(white, gray, intensity)


def render_page(
    path: str | Path,
    page_index: int = 0,
    scale: float = 1.5,
    crop_box: tuple[float, float, float, float] | list[float] | None = None,
    background_intensity: float | None = None,
):
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
        image = bitmap.to_pil().copy().convert("RGB")
        pixel_box = crop_pixel_box(image.size, crop_box)
        image = image.crop(pixel_box)
        return fade_background(image, background_intensity) if background_intensity is not None else image
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
