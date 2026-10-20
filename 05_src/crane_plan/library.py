"""Локальные автономные библиотеки кранов и нормативных документов."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


LIBRARY_NAMES = {"cranes", "regulations"}


def load_library(resource_root: Path, library_name: str) -> tuple[Path, dict[str, Any]]:
    if library_name not in LIBRARY_NAMES:
        raise ValueError(f"Неизвестная библиотека: {library_name}")
    root = (Path(resource_root) / "library" / library_name).resolve()
    manifest_path = root / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data.get("entries"), list):
        raise ValueError(f"В {manifest_path} отсутствует список entries")
    return root, data


def resolve_local_file(library_root: Path, relative_path: str) -> Path:
    """Вернуть безопасный путь внутри библиотеки, не допуская ../."""
    root = Path(library_root).resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Путь документа выходит за пределы библиотеки") from exc
    return target


def open_local_path(path: Path) -> None:
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
