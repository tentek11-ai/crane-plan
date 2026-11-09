"""Writable runtime locations for the portable desktop application."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable
from uuid import uuid4


def _default_temp_candidates() -> tuple[Path, ...]:
    configured = os.environ.get("CRANEPLAN_TEMP")
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend((
        Path(tempfile.gettempdir()),
        Path.home() / "Documents" / "КранПлан проекты" / ".temp",
        Path.cwd() / ".craneplan-temp",
        Path(sys.executable).resolve().parent / ".craneplan-temp",
    ))
    return tuple(candidates)


def writable_temp_root(candidates: Iterable[str | Path] | None = None) -> Path:
    """Return the first candidate that can create and remove a probe file."""

    failures: list[str] = []
    seen: set[Path] = set()
    for candidate in candidates or _default_temp_candidates():
        root = Path(candidate).expanduser()
        try:
            root = root.resolve()
        except OSError:
            root = root.absolute()
        if root in seen:
            continue
        seen.add(root)
        probe: Path | None = None
        probe_file: Path | None = None
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = Path(tempfile.mkdtemp(dir=root, prefix=f".craneplan-write-probe-{uuid4().hex}-"))
            probe_file = probe / "probe"
            probe_file.write_bytes(b"")
            probe_file.unlink()
            probe.rmdir()
            return root
        except OSError as exc:
            failures.append(f"{root}: {exc}")
            try:
                if probe_file is not None:
                    probe_file.unlink(missing_ok=True)
                if probe is not None:
                    probe.rmdir()
            except OSError:
                pass
    details = "; ".join(failures)
    raise OSError(f"Не найдена доступная папка для временных файлов CranePlan. {details}")
