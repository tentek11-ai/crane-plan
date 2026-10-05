"""Создание, сохранение и восстановление переносимых папок проектов."""

from __future__ import annotations

import json
import re
import shutil
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .models import Load, ProjectInput, SiteInput, WorkPoint


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "_", value).strip(" .")
    return value or "Без названия"


def project_folder_name(project: ProjectInput) -> str:
    return safe_name(f"{project.year} — {project.city} — {project.name}")


def create_project_folder(root: str | Path, project: ProjectInput) -> Path:
    folder = Path(root) / project_folder_name(project)
    for child in ("sources", "revisions", "reports"):
        (folder / child).mkdir(parents=True, exist_ok=True)
    return folder


def save_project(folder: str | Path, project: ProjectInput, scenarios: list[dict] | None = None) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    payload = project.to_dict()
    payload["schema_version"] = 1
    payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
    payload["scenarios"] = scenarios or []
    target = folder / "project.json"
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    os.replace(temporary, target)
    revision = folder / "revisions" / f"project_{datetime.now():%Y%m%d_%H%M%S_%f}_{uuid4().hex[:8]}.json"
    revision.parent.mkdir(parents=True, exist_ok=True)
    revision.write_text(serialized, encoding="utf-8")
    return target


def copy_source_pdf(source: str | Path, folder: str | Path, role: str) -> Path:
    source = Path(source)
    target = Path(folder) / "sources" / f"{safe_name(role)}_{safe_name(source.name)}"
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def load_project(path: str | Path) -> ProjectInput:
    source = Path(path)
    if source.is_dir():
        source = source / "project.json"
    if not source.is_file():
        raise ValueError("Файл project.json не найден")
    if source.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("project.json превышает допустимый размер 20 МБ")
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema_version") not in (None, 1):
        raise ValueError(f"Неподдерживаемая версия проекта: {data.get('schema_version')}")
    for key in ("site", "loads", "work_points"):
        if key not in data:
            raise ValueError(f"Повреждённый проект: отсутствует раздел {key}")
    site_data = data["site"]
    site = SiteInput(
        boundary=[tuple(p) for p in site_data["boundary"]],
        building=[tuple(p) for p in site_data["building"]],
        restricted_zones=[[tuple(p) for p in zone] for zone in site_data.get("restricted_zones", [])],
        unloading_zone=[tuple(p) for p in site_data.get("unloading_zone", [])],
        storage_zones=[[tuple(p) for p in zone] for zone in site_data.get("storage_zones", [])],
        min_crane_to_building_m=site_data.get("min_crane_to_building_m", 1.0),
        max_crane_to_building_m=site_data.get("max_crane_to_building_m", 25.0),
    )
    fields = {key: value for key, value in data.items() if key in ProjectInput.__dataclass_fields__}
    fields["site"] = site
    fields["loads"] = [Load(**item) for item in data["loads"]]
    fields["work_points"] = [WorkPoint(**item) for item in data["work_points"]]
    return ProjectInput(**fields)
