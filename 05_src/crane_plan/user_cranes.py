"""Persistent user-entered crane configurations kept outside the application."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable


USER_CRANE_STATUS = "USER_INPUT_EXPERT_REVIEW"


def _positive_number(value: Any, label: str) -> float:
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: укажите число") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label}: значение должно быть положительным")
    return number


def parse_capacity_curve(text: str) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    for line_number, raw_line in enumerate(str(text).splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(";")]
        if len(parts) != 2:
            raise ValueError(
                f"Строка {line_number}: используйте формат «вылет; грузоподъёмность»"
            )
        points.append(
            (
                _positive_number(parts[0], f"Строка {line_number}, вылет"),
                _positive_number(parts[1], f"Строка {line_number}, грузоподъёмность"),
            )
        )
    if len(points) < 2:
        raise ValueError("Грузовая характеристика должна содержать минимум две точки")
    return tuple(points)


def validate_user_crane(payload: dict[str, Any]) -> dict[str, Any]:
    manufacturer = str(payload.get("manufacturer", "")).strip()
    model = str(payload.get("model", "")).strip()
    if not manufacturer:
        raise ValueError("Укажите изготовителя крана")
    if not model:
        raise ValueError("Укажите модель крана")

    jib_length = _positive_number(payload.get("jib_length_m"), "Длина стрелы")
    max_capacity = _positive_number(
        payload.get("max_capacity_kg"), "Максимальная грузоподъёмность"
    )
    free_height = _positive_number(
        payload.get("max_free_standing_hook_height_m"),
        "Высота свободного стояния",
    )
    raw_curve = payload.get("capacity_curve")
    curve = parse_capacity_curve(raw_curve) if isinstance(raw_curve, str) else tuple(
        (_positive_number(radius, "Вылет"), _positive_number(capacity, "Грузоподъёмность"))
        for radius, capacity in (raw_curve or ())
    )
    if len(curve) < 2:
        raise ValueError("Грузовая характеристика должна содержать минимум две точки")
    for previous, current in zip(curve, curve[1:]):
        if current[0] <= previous[0]:
            raise ValueError("Вылет в грузовой характеристике должен строго возрастать")
        if current[1] > previous[1]:
            raise ValueError("Грузоподъёмность должна уменьшаться или оставаться постоянной")
    if curve[-1][0] + 1e-9 < jib_length:
        raise ValueError("Последняя точка грузовой характеристики должна достигать длины стрелы")
    if any(capacity > max_capacity + 1e-9 for _radius, capacity in curve):
        raise ValueError("Грузовая характеристика превышает максимальную грузоподъёмность")

    return {
        "manufacturer": manufacturer,
        "model": model,
        "jib_length_m": jib_length,
        "max_capacity_kg": max_capacity,
        "max_free_standing_hook_height_m": free_height,
        "capacity_curve": [[radius, capacity] for radius, capacity in curve],
        "notes": str(payload.get("notes", "")).strip(),
        "brochure_file": str(payload.get("brochure_file", "")).strip(),
        "status": USER_CRANE_STATUS,
    }


def build_user_crane_payload(fields: dict[str, Any]) -> dict[str, Any]:
    """Convert editor fields into the normalized persistent representation."""
    return validate_user_crane(
        {
            "manufacturer": fields.get("manufacturer", ""),
            "model": fields.get("model", ""),
            "jib_length_m": fields.get("jib_length_m", ""),
            "max_capacity_kg": fields.get("max_capacity_kg", ""),
            "max_free_standing_hook_height_m": fields.get(
                "max_free_standing_hook_height_m", ""
            ),
            "capacity_curve": fields.get("capacity_curve", ""),
            "notes": fields.get("notes", ""),
        }
    )


def load_user_cranes(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("configurations"), list):
        raise ValueError("Неподдерживаемый формат пользовательского каталога кранов")
    return [dict(item) for item in data["configurations"]]


def save_user_cranes(path: str | Path, configurations: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "configurations": list(configurations)}
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _identifier_base(manufacturer: str, model: str, jib_length_m: float) -> str:
    raw = f"{manufacturer}-{model}-{jib_length_m:g}"
    slug = re.sub(r"[^0-9A-Za-zА-Яа-я]+", "-", raw).strip("-").upper()
    return f"USER-{slug or 'CRANE'}"


def add_user_crane(
    path: str | Path,
    payload: dict[str, Any],
    brochure_source: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(path)
    configurations = load_user_cranes(path)
    normalized = validate_user_crane(payload)
    base = _identifier_base(
        normalized["manufacturer"], normalized["model"], normalized["jib_length_m"]
    )
    existing_ids = {item.get("id") for item in configurations}
    identifier = base
    suffix = 2
    while identifier in existing_ids:
        identifier = f"{base}-{suffix}"
        suffix += 1

    copied_brochure: Path | None = None
    if brochure_source:
        source = Path(brochure_source)
        if source.suffix.lower() != ".pdf" or not source.is_file():
            raise ValueError("Брошюра должна быть существующим PDF-файлом")
        brochure_dir = path.parent / "brochures"
        brochure_dir.mkdir(parents=True, exist_ok=True)
        copied_brochure = brochure_dir / f"{identifier}.pdf"
        shutil.copy2(source, copied_brochure)
        normalized["brochure_file"] = str(Path("brochures") / copied_brochure.name)

    entry = {
        **normalized,
        "id": identifier,
        "priority": 1000 + len(configurations),
        "source": "USER_INPUT: характеристики введены пользователем; требуется экспертная проверка",
    }
    try:
        save_user_cranes(path, [*configurations, entry])
    except Exception:
        if copied_brochure and copied_brochure.exists():
            copied_brochure.unlink()
        raise
    return entry


def delete_user_crane(path: str | Path, identifier: str) -> bool:
    path = Path(path)
    configurations = load_user_cranes(path)
    kept = [item for item in configurations if item.get("id") != identifier]
    if len(kept) == len(configurations):
        return False
    removed = next(item for item in configurations if item.get("id") == identifier)
    save_user_cranes(path, kept)
    brochure = str(removed.get("brochure_file", "")).strip()
    if brochure:
        candidate = (path.parent / brochure).resolve()
        try:
            candidate.relative_to(path.parent.resolve())
        except ValueError:
            candidate = Path()
        if candidate.is_file():
            candidate.unlink()
    return True
