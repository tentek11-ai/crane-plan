"""Загрузка и интерполяция грузовых характеристик."""

from __future__ import annotations

import json
from pathlib import Path

from .models import CraneConfiguration
from .user_cranes import load_user_cranes


def _configuration(item: dict) -> CraneConfiguration:
    return CraneConfiguration(
        id=item["id"], model=item["model"], priority=item["priority"],
        jib_length_m=item["jib_length_m"], max_capacity_kg=item["max_capacity_kg"],
        max_free_standing_hook_height_m=item["max_free_standing_hook_height_m"],
        capacity_curve=tuple((float(r), float(q)) for r, q in item["capacity_curve"]),
        source=item["source"],
    )


def load_catalog(
    path: str | Path,
    user_catalog_path: str | Path | None = None,
) -> list[CraneConfiguration]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    result = [_configuration(item) for item in data["configurations"]]
    if user_catalog_path is not None:
        known_ids = {item.id for item in result}
        for index, item in enumerate(load_user_cranes(user_catalog_path)):
            if item.get("id") in known_ids:
                raise ValueError(f"Повтор идентификатора крана: {item.get('id')}")
            protected = {
                **item,
                "priority": 1000 + index,
                "source": (
                    "USER_INPUT: характеристики введены пользователем; "
                    "требуется экспертная проверка"
                ),
            }
            result.append(_configuration(protected))
            known_ids.add(item["id"])
    return sorted(result, key=lambda c: c.priority)


def allowed_capacity_kg(config: CraneConfiguration, radius_m: float) -> float:
    curve = config.capacity_curve
    if radius_m < 0 or radius_m > curve[-1][0]:
        return 0.0
    if radius_m <= curve[0][0]:
        return min(config.max_capacity_kg, curve[0][1])
    for index in range(1, len(curve)):
        r1, q1 = curve[index - 1]
        r2, q2 = curve[index]
        if radius_m <= r2:
            ratio = (radius_m - r1) / (r2 - r1)
            return q1 + ratio * (q2 - q1)
    return 0.0
