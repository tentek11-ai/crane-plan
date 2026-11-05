"""Modal editor and pure form conversion for height-aware restricted zones."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from uuid import uuid4

from .models import Point, RestrictedZone, RestrictedZoneKind


ZONE_KIND_LABELS = {
    RestrictedZoneKind.FULL_EXCLUSION: "Полный запрет",
    RestrictedZoneKind.LOAD_PROHIBITED: "Запрет проноса груза",
    RestrictedZoneKind.HEIGHT_OBSTACLE: "Высотное препятствие",
}
ZONE_LABEL_KINDS = {label: kind for kind, label in ZONE_KIND_LABELS.items()}


@dataclass(frozen=True)
class ZoneEditorResult:
    zone: RestrictedZone | None
    cancelled: bool


def _number(text: str, field_name: str) -> float:
    value = text.strip().replace(",", ".")
    if not value:
        raise ValueError(f"Заполните поле «{field_name}»")
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"Поле «{field_name}» должно содержать число") from error
    if number < 0:
        raise ValueError(f"Поле «{field_name}» не может быть отрицательным")
    return number


def zone_from_form(
    polygon: list[Point],
    *,
    name: str,
    kind_value: str,
    height_text: str,
    clearance_text: str,
    note: str,
    initial: RestrictedZone | None = None,
    verified: bool | None = None,
) -> RestrictedZone:
    """Validate form strings and build a domain object without requiring Tk."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Укажите название опасной зоны")
    try:
        kind = ZONE_LABEL_KINDS[kind_value] if kind_value in ZONE_LABEL_KINDS else RestrictedZoneKind(kind_value)
    except ValueError as error:
        raise ValueError("Выберите тип опасной зоны") from error
    height = _number(height_text, "Высота от 0, м")
    clearance = _number(clearance_text, "Горизонтальный запас, м")
    return RestrictedZone(
        id=initial.id if initial else f"zone-{uuid4().hex[:12]}",
        name=clean_name,
        kind=kind,
        polygon=list(polygon),
        height_m=height,
        horizontal_clearance_m=clearance,
        note=note.strip(),
        verified=(initial.verified if initial else True) if verified is None else bool(verified),
        source_refs=list(initial.source_refs) if initial else [],
    )


def edit_restricted_zone(
    parent: tk.Misc,
    polygon: list[Point],
    initial: RestrictedZone | None = None,
) -> ZoneEditorResult:
    """Open the zone card and return either a saved zone or an explicit cancel."""
    dialog = tk.Toplevel(parent)
    dialog.title("Карточка опасной зоны")
    dialog.transient(parent)
    dialog.resizable(False, False)

    default_kind = initial.kind if initial else RestrictedZoneKind.FULL_EXCLUSION
    name_var = tk.StringVar(value=initial.name if initial else "")
    kind_var = tk.StringVar(value=ZONE_KIND_LABELS[default_kind])
    height_var = tk.StringVar(value=f"{initial.height_m:g}" if initial else "0")
    clearance_var = tk.StringVar(value=f"{initial.horizontal_clearance_m:g}" if initial else "0")
    verified_var = tk.BooleanVar(value=initial.verified if initial else True)
    result = ZoneEditorResult(None, True)

    fields = (
        ("Название", name_var),
        ("Высота от отметки 0, м", height_var),
        ("Горизонтальный запас, м", clearance_var),
    )
    for row, (label, variable) in enumerate(fields):
        ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        ttk.Entry(dialog, textvariable=variable, width=36).grid(row=row, column=1, sticky="ew", padx=10, pady=5)
    ttk.Label(dialog, text="Тип зоны").grid(row=3, column=0, sticky="w", padx=10, pady=5)
    ttk.Combobox(
        dialog, textvariable=kind_var, values=tuple(ZONE_KIND_LABELS.values()),
        state="readonly", width=33,
    ).grid(row=3, column=1, sticky="ew", padx=10, pady=5)
    ttk.Label(dialog, text="Примечание").grid(row=4, column=0, sticky="nw", padx=10, pady=5)
    note_widget = tk.Text(dialog, width=36, height=4)
    note_widget.grid(row=4, column=1, sticky="ew", padx=10, pady=5)
    if initial:
        note_widget.insert("1.0", initial.note)
    ttk.Checkbutton(
        dialog,
        text="Тип, границы и высота зоны проверены по исходным данным",
        variable=verified_var,
    ).grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=5)

    def save() -> None:
        nonlocal result
        try:
            zone = zone_from_form(
                polygon,
                name=name_var.get(), kind_value=kind_var.get(),
                height_text=height_var.get(), clearance_text=clearance_var.get(),
                note=note_widget.get("1.0", "end-1c"), initial=initial,
                verified=verified_var.get(),
            )
        except ValueError as error:
            messagebox.showerror("Ошибка карточки зоны", str(error), parent=dialog)
            return
        result = ZoneEditorResult(zone, False)
        dialog.destroy()

    buttons = ttk.Frame(dialog)
    buttons.grid(row=6, column=0, columnspan=2, sticky="e", padx=10, pady=10)
    ttk.Button(buttons, text="Отмена", command=dialog.destroy).pack(side="right", padx=4)
    ttk.Button(buttons, text="Сохранить", command=save).pack(side="right", padx=4)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.grab_set()
    dialog.wait_window()
    return result
