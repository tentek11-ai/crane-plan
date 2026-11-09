"""Русский настольный интерфейс первой версии Crane Plan."""

from __future__ import annotations

import json
import hashlib
import math
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import filedialog, messagebox, simpledialog, ttk
from uuid import uuid4

from PIL import ImageTk

from .catalog import load_catalog
from .geometry import point_in_polygon, polygon_inside_polygon, section_contour_height, validate_polygon
from .engine import (
    IntegrationStatus,
    ScenarioVerificationV21,
    default_release_index,
    load_catalog_v3,
    save_protocol_atomic,
    verify_scenarios_v21,
)
from .library import load_library, open_local_path, resolve_local_file
from .models import Load, ProjectInput, RestrictedZone, RestrictedZoneKind, ScenarioResult, SiteInput, WorkPoint
from .optimizer import optimize
from .pdf_workspace import calibration_m_per_pixel, crop_pixel_box, display_size, inspect_pdf, normalize_crop_box, pixel_to_world, render_page, suggest_vector_bounds
from .project_io import copy_source_pdf, create_project_folder, load_project, save_project
from .recalculation import CalculationState, RecalculationCoordinator, accept_warning, current_warning_acceptances
from .pprk_models import ApprovalSlot, ExternalDocument, PPRKReleaseConfig, ReleaseStatus, TemplateOverride
from .pprk_merge import verify_external_revision
from .pprk_templates import load_template_catalog
from .pprk_release_workflow import (
    RELEASE_FIELDS, approval_rows, edit_release_fields, issue_action, prepare_release,
    publish_release, release_fingerprint, require_selected_protocol, require_saveable_release, source_digest,
)
from .report import generate_report
from .restricted_zones import validate_zone
from .runtime_paths import writable_temp_root
from .sozr_canvas import build_sozr_canvas_primitives, draw_sozr_canvas
from .user_cranes import add_user_crane, build_user_crane_payload, delete_user_crane, load_user_cranes
from .zone_editor import ZONE_KIND_LABELS, edit_restricted_zone


APP_VERSION = "3.0.2"
APP_TITLE = f"КранПлан {APP_VERSION} — BIM-среда предварительной расстановки башенных кранов"


def _load_editor_values(load):
    return (load.name, load.load_kg, load.rigging_kg, load.length_m, load.width_m,
            load.height_m, load.lifts, "да" if load.active else "нет", load.rigging_type,
            "" if load.rigging_branch_count is None else load.rigging_branch_count,
            load.sling_identification, "" if load.rigging_capacity_kg is None else load.rigging_capacity_kg,
            load.rigging_evidence, "да" if load.rigging_verified else "нет")


@dataclass
class _CalculationBundle:
    project: ProjectInput
    reminders: list[str]
    scenarios: list
    verifications: list

    @property
    def status(self) -> str:
        if not self.scenarios or self.scenarios[0].status == "BLOCKED":
            return "NO_SOLUTION"
        if any(item.status is IntegrationStatus.EXPERT_REVIEW_REQUIRED for item in self.verifications):
            return "EXPERT_REVIEW"
        return "CURRENT"


def _sector_text(start, end):
    if start is None or end is None:
        return ""
    if end-start >= 359.999:
        return "0°…360°"
    raw_end=end; start=start%360; finish=end%360
    if start<=finish and raw_end<=360:
        return f"{start:.1f}°…{finish:.1f}°"
    return f"{start:.1f}°…360°; 0°…{finish:.1f}°"

UI = {
    "window": "#20252b",
    "chrome": "#252b31",
    "ribbon": "#3a4148",
    "panel": "#2d333a",
    "panel_alt": "#343b43",
    "workspace": "#1e242a",
    "field": "#242a30",
    "border": "#505861",
    "text": "#eef2f5",
    "muted": "#aeb7c0",
    "accent": "#2f80c9",
    "accent_hover": "#4595dc",
    "selection": "#28659a",
    "cyan": "#4fc3f7",
}

DRAW_COLORS = {
    "site": "#263238",
    "building": "#008dd2",
    "restricted": "#e53945",
    "unloading": "#f59e0b",
    "storage": "#8b5cf6",
    "workpoint": "#00a878",
    "section": "#8b5cf6",
}


APPROVAL_FIELDS = dict(zip(ApprovalSlot.__dataclass_fields__, ("Организация", "Должность", "ФИО", "Подпись", "Дата", "Роль (Проверил / Утвердил)")))
EXTERNAL_FIELDS = {"document_id": "ID", "title": "Название", "required": "Обязателен", "present": "В наличии",
                   "number": "Номер", "date": "Дата", "organization": "Организация", "verification_status": "Проверка",
                   "attachment_path": "Локальный PDF", "appendix_order": "Порядок"}
OVERRIDE_FIELDS = {"paragraph_id": "ID абзаца", "base_version": "Версия шаблона", "replacement_text": "Текст замены"}


class CranePlanApp(tk.Tk):
    def __init__(self, resource_root: Path | None = None):
        super().__init__()
        self.title(APP_TITLE)
        screen_w=max(960,self.winfo_screenwidth()-40); screen_h=max(600,self.winfo_screenheight()-90)
        self.geometry(f"{min(1480,screen_w)}x{min(900,screen_h)}")
        self.minsize(960, 600)
        self.configure(bg=UI["window"])
        self.resource_root = resource_root or Path(__file__).parents[2]
        self.catalog_path = self.resource_root / "02_processed_data/cranes/crane_configurations.json"
        self.catalog_v3_path = self.resource_root / "02_processed_data/cranes/crane_configurations_v3.json"
        self.loads_path = self.resource_root / "02_processed_data/loads/standard_monolithic_loads.json"
        self.project_root = Path.home() / "Documents" / "КранПлан проекты"
        self.user_crane_root = self.project_root / "Библиотека пользователя" / "краны"
        self.user_catalog_path = self.user_crane_root / "user_cranes.json"
        self.plan_pdf = ""
        self.section_pdf = ""
        self.plan_crop_box = (0.0, 0.0, 1.0, 1.0)
        self.section_crop_box = (0.0, 0.0, 1.0, 1.0)
        self.plan_background_intensity = tk.StringVar(value="35")
        self.section_background_intensity = tk.StringVar(value="35")
        self.plan_crop_active = False
        self.section_crop_active = False
        self.crop_drag_start = None
        self.crop_rect_id = None
        self.plan_image = None
        self.plan_photo = None
        self.section_image = None
        self.section_photo = None
        self.section_image_scale = 1.0
        self.section_calibration_points: list[tuple[float, float]] = []
        self.section_m_per_pixel: float | None = None
        self.section_origin_px: tuple[float, float] | None = None
        self.section_axis: tuple[float, float] = (0.0, -1.0)
        self.section_mode = "calibration"
        self.section_building_points: list[tuple[float,float]] = []
        self.section_contour_pixels: list[tuple[float,float]] = []
        self.section_contour_closed = False
        self.image_scale = 1.0
        self.plan_zoom = 1.0
        self.section_zoom = 1.0
        self.plan_fit_scale = 1.0
        self.section_fit_scale = 1.0
        self.calibration_points: list[tuple[float, float]] = []
        self.m_per_pixel: float | None = None
        self.origin_px: tuple[float, float] | None = None
        self.mode = "calibration"
        self.site_points: list[tuple[float, float]] = []
        self.building_points: list[tuple[float, float]] = []
        self.current_zone_points: list[tuple[float, float]] = []
        self.restricted_zones: list[RestrictedZone] = []
        self.selected_restricted_zone_id: str | None = None
        self.unloading_points: list[tuple[float, float]] = []
        self.current_storage_points: list[tuple[float, float]] = []
        self.storage_zones: list[list[tuple[float, float]]] = []
        self.contour_pixels: dict[str, list[tuple[float, float]]] = {"site": [], "building": [], "restricted": [], "unloading": [], "storage": []}
        self.closed_contours: set[str] = set()
        self.work_points: list[WorkPoint] = []
        self.scenarios = []
        self.scenario_verifications = []
        self.selected_release_index: int | None = None
        self.calculation_input_snapshot: str | None = None
        self.loads_verified = tk.BooleanVar(value=False)
        self.warning_acceptances = []
        self.release_variant_var = tk.StringVar(value="")
        self.report_page_order: list[int] | None = None
        self.report_excluded_pages: set[int] = set()
        self.loads = self._default_loads()
        self._configure_revit_theme()
        self._build_ui()
        self._configure_text_editing()
        self._configure_recalculation()

    def _default_loads(self) -> list[Load]:
        data = json.loads(self.loads_path.read_text(encoding="utf-8"))
        return [Load(name=x["name"], load_kg=x["load_kg"], rigging_kg=x["rigging_kg"], length_m=x["length_m"], width_m=x["width_m"], height_m=x["height_m"], lifts=10) for x in data["loads"]]

    def _configure_revit_theme(self):
        """Единая тёмная тема в логике интерфейса Autodesk Revit 2025."""
        style = ttk.Style(self)
        style.theme_use("clam")
        self.option_add("*Font", "{Segoe UI} 9")
        self.option_add("*TCombobox*Listbox.font", "{Segoe UI} 9")
        self.option_add("*TCombobox*Listbox.background", UI["field"])
        self.option_add("*TCombobox*Listbox.foreground", UI["text"])
        style.configure(".", background=UI["panel"], foreground=UI["text"], font=("Segoe UI", 9))
        style.configure("TFrame", background=UI["panel"])
        style.configure("Workspace.TFrame", background=UI["workspace"])
        style.configure("TLabel", background=UI["panel"], foreground=UI["text"])
        style.configure("Muted.TLabel", foreground=UI["muted"])
        style.configure("TLabelFrame", background=UI["panel"], bordercolor=UI["border"], relief="solid")
        style.configure("TLabelFrame.Label", background=UI["panel"], foreground=UI["text"], font=("Segoe UI Semibold", 9))
        style.configure("TEntry", fieldbackground=UI["field"], foreground=UI["text"], bordercolor=UI["border"], insertcolor=UI["text"], padding=5)
        style.map("TEntry", bordercolor=[("focus", UI["accent"])], fieldbackground=[("disabled", UI["chrome"])])
        style.configure("TCombobox", fieldbackground=UI["field"], foreground=UI["text"], arrowcolor=UI["text"], bordercolor=UI["border"], padding=4)
        style.configure("TCheckbutton", background=UI["panel"], foreground=UI["text"])
        style.configure("TRadiobutton", background=UI["panel"], foreground=UI["text"])
        style.map("TCheckbutton", background=[("active", UI["panel_alt"])], foreground=[("disabled", UI["muted"])])
        style.map("TRadiobutton", background=[("active", UI["panel_alt"])])
        style.configure("TButton", background=UI["panel_alt"], foreground=UI["text"], bordercolor=UI["border"], padding=(10, 6), relief="flat")
        style.map("TButton", background=[("active", "#46505a"), ("pressed", UI["selection"])], bordercolor=[("focus", UI["accent"])])
        style.configure("Accent.TButton", background=UI["accent"], foreground="#ffffff", font=("Segoe UI Semibold", 9), padding=(14, 8))
        style.map("Accent.TButton", background=[("active", UI["accent_hover"]), ("pressed", "#23679f")])
        style.configure("Ribbon.TButton", background=UI["ribbon"], foreground=UI["text"], bordercolor=UI["ribbon"], padding=(9, 5))
        style.map("Ribbon.TButton", background=[("active", "#505963"), ("pressed", UI["selection"])])
        style.configure("TNotebook", background=UI["workspace"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background=UI["chrome"], foreground=UI["muted"], padding=(14, 7), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", UI["panel_alt"]), ("active", "#3d464f")], foreground=[("selected", "#ffffff"), ("active", "#ffffff")])
        style.configure("Treeview", background=UI["field"], fieldbackground=UI["field"], foreground=UI["text"], bordercolor=UI["border"], rowheight=24)
        style.map("Treeview", background=[("selected", UI["selection"])], foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading", background=UI["panel_alt"], foreground=UI["text"], relief="flat", padding=(6, 6), font=("Segoe UI Semibold", 9))
        style.map("Treeview.Heading", background=[("active", "#46505a")])
        style.configure("TSeparator", background=UI["border"])

    def _configure_text_editing(self):
        """Надёжные команды редактирования, включая русскую раскладку Windows."""
        self._edit_context_widget = None
        self._edit_context_menu = tk.Menu(
            self,
            tearoff=False,
            bg=UI["panel_alt"],
            fg=UI["text"],
            activebackground=UI["selection"],
            activeforeground="#ffffff",
        )
        for label, action in (
            ("Вырезать", "cut"),
            ("Копировать", "copy"),
            ("Вставить", "paste"),
            ("Выделить всё", "select_all"),
        ):
            self._edit_context_menu.add_command(
                label=label,
                command=lambda selected_action=action: self._text_edit_action(
                    self._edit_context_widget, selected_action
                ),
            )
        self.bind_all("<Control-KeyPress>", self._handle_text_shortcut, add="+")
        for widget_class in ("Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"):
            self.bind_class(widget_class, "<Button-3>", self._show_text_context_menu, add="+")

    @staticmethod
    def _is_text_widget(widget):
        return widget is not None and widget.winfo_class() in {
            "Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"
        }

    @staticmethod
    def _widget_is_writable(widget):
        try:
            return str(widget.cget("state")) not in {"disabled", "readonly"}
        except tk.TclError:
            return True

    @staticmethod
    def _selected_text(widget):
        try:
            if widget.winfo_class() == "Text":
                return widget.get("sel.first", "sel.last")
            return widget.get()[widget.index("sel.first"):widget.index("sel.last")]
        except (tk.TclError, ValueError):
            return ""

    @staticmethod
    def _delete_selection(widget):
        try:
            if widget.winfo_class() == "Text":
                widget.delete("sel.first", "sel.last")
            else:
                widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

    def _text_edit_action(self, widget, action):
        if not self._is_text_widget(widget):
            return None
        if action in {"paste", "cut"} and not self._widget_is_writable(widget):
            return "break"
        if action == "select_all":
            if widget.winfo_class() == "Text":
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "end-1c")
            else:
                widget.selection_range(0, "end")
                widget.icursor("end")
            return "break"
        if action in {"copy", "cut"}:
            selected = self._selected_text(widget)
            if selected:
                self.clipboard_clear()
                self.clipboard_append(selected)
                if action == "cut":
                    self._delete_selection(widget)
            return "break"
        if action == "paste":
            try:
                value = self.clipboard_get()
            except tk.TclError:
                return "break"
            if widget.winfo_class() != "Text":
                value = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
            self._delete_selection(widget)
            widget.insert("insert", value)
            return "break"
        return None

    def _handle_text_shortcut(self, event):
        if not event.state & 0x0004 or not self._is_text_widget(event.widget):
            return None
        by_keycode = {65: "select_all", 67: "copy", 86: "paste", 88: "cut"}
        by_keysym = {"a": "select_all", "c": "copy", "v": "paste", "x": "cut"}
        action = by_keycode.get(event.keycode) or by_keysym.get(str(event.keysym).lower())
        return self._text_edit_action(event.widget, action) if action else None

    def _show_text_context_menu(self, event):
        if not self._is_text_widget(event.widget):
            return None
        self._edit_context_widget = event.widget
        event.widget.focus_set()
        self._edit_context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _build_ui(self):
        self._build_title_and_ribbon()
        work = tk.PanedWindow(self, orient="horizontal", bg=UI["border"], sashwidth=4, bd=0, relief="flat")
        work.pack(fill="both", expand=True)

        left = tk.Frame(work, bg=UI["panel"], width=235, bd=0)
        center = ttk.Frame(work, style="Workspace.TFrame")
        right = tk.Frame(work, bg=UI["panel"], width=265, bd=0)
        work.add(left, minsize=150, width=220)
        work.add(center, minsize=500, stretch="always")
        work.add(right, minsize=170, width=245)

        self._build_project_browser(left)
        self.notebook = ttk.Notebook(center)
        self.notebook.pack(fill="both", expand=True)
        self.tabs = {name: ttk.Frame(self.notebook) for name in ("1. Проект", "2. План", "3. Разрез", "4. Грузы", "5. Расчёт", "6. Отчёт")}
        for name, frame in self.tabs.items():
            self.notebook.add(frame, text=name)
        self._build_project_tab()
        self._build_plan_tab()
        self._build_section_tab()
        self._build_loads_tab()
        self._build_calculation_tab()
        self._build_report_tab()
        self._build_properties_panel(right)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.status = tk.StringVar(value="Создайте проект и загрузите векторный PDF-план.")
        status_bar = tk.Frame(self, bg="#181c20", height=25)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)
        tk.Label(status_bar, text="КРАНПЛАН", bg=UI["accent"], fg="white", font=("Segoe UI Semibold", 8), padx=12).pack(side="left", fill="y")
        tk.Label(status_bar, textvariable=self.status, bg="#181c20", fg=UI["muted"], anchor="w", padx=10).pack(side="left", fill="both", expand=True)
        tk.Label(status_bar, text="Готов  |  локальный режим", bg="#181c20", fg=UI["muted"], padx=12).pack(side="right", fill="y")
        self.after_idle(self._update_properties)

    def _build_title_and_ribbon(self):
        title_bar = tk.Frame(self, bg="#171b1f", height=32)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="К", bg=UI["accent"], fg="white", width=3, font=("Segoe UI Semibold", 11)).pack(side="left", fill="y")
        tk.Label(title_bar, text=f"КранПлан {APP_VERSION}", bg="#171b1f", fg=UI["text"], font=("Segoe UI Semibold", 10), padx=10).pack(side="left")
        tk.Label(title_bar, text="Предварительная расстановка башенных кранов", bg="#171b1f", fg=UI["muted"], font=("Segoe UI", 9)).pack(side="left", padx=8)
        tk.Label(title_bar, text="BIM / ППРк", bg="#171b1f", fg=UI["muted"], font=("Segoe UI", 8), padx=12).pack(side="right")

        menu_bar = tk.Frame(self, bg=UI["chrome"], height=29)
        menu_bar.pack(fill="x")
        menu_bar.pack_propagate(False)
        for index, label in enumerate(("Файл", "Проект", "Разметка", "Краны", "Расчёт", "Документация", "Вид", "Управление")):
            tk.Label(menu_bar, text=label, bg=UI["accent"] if index == 0 else UI["chrome"], fg="white" if index == 0 else UI["text"], padx=13, font=("Segoe UI", 9)).pack(side="left", fill="y")

        ribbon = tk.Frame(self, bg=UI["ribbon"], height=91, highlightthickness=0)
        ribbon.pack(fill="x")
        ribbon.pack_propagate(False)

        def group(title, commands):
            box = tk.Frame(ribbon, bg=UI["ribbon"], padx=6, pady=5)
            box.pack(side="left", fill="y")
            body = tk.Frame(box, bg=UI["ribbon"])
            body.pack(fill="both", expand=True)
            for text, command in commands:
                ttk.Button(body, text=text, command=command, style="Ribbon.TButton").pack(side="left", padx=2, fill="y")
            tk.Label(box, text=title, bg=UI["ribbon"], fg=UI["muted"], font=("Segoe UI", 8)).pack(side="bottom")
            tk.Frame(ribbon, bg=UI["border"], width=1).pack(side="left", fill="y", pady=7)

        group("Проект", (("Открыть", self.open_project), ("План PDF", self.choose_plan), ("Разрез PDF", self.choose_section)))
        group("Виды", (("Стройгенплан", lambda: self._show_tab(1)), ("Разрез", lambda: self._show_tab(2)), ("Грузы", lambda: self._show_tab(3))))
        group("Модель", (("Граница", lambda: self._activate_plan_mode("site")), ("Здание", lambda: self._activate_plan_mode("building")), ("Запретная зона", lambda: self._activate_plan_mode("restricted"))))
        group("Анализ", (("Рассчитать", self.run_calculation), ("Результаты", lambda: self._show_tab(4))))
        group("Справочники", (("Каталог кранов", lambda: self.show_library("cranes")), ("Нормативы", lambda: self.show_library("regulations"))))
        group("Выпуск", (("Предпросмотр", self.preview_report_pages), ("Сформировать ППРк", self.save_and_report)))

    def _build_project_browser(self, parent):
        tk.Label(parent, text="ДИСПЕТЧЕР ПРОЕКТА", bg=UI["chrome"], fg=UI["text"], anchor="w", padx=10, pady=7, font=("Segoe UI Semibold", 9)).pack(fill="x")
        search = tk.Entry(parent, bg=UI["field"], fg=UI["muted"], insertbackground=UI["text"], relief="flat", bd=0, font=("Segoe UI", 9))
        search.insert(0, "  Поиск")
        search.pack(fill="x", padx=7, pady=7, ipady=5)
        self.nav_tree = ttk.Treeview(parent, show="tree", selectmode="browse")
        self.nav_tree.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        root = self.nav_tree.insert("", "end", iid="project_root", text="▾ КранПлан — проект", open=True)
        views = self.nav_tree.insert(root, "end", iid="views_root", text="▾ Рабочие виды", open=True)
        for index, text in enumerate(("Карточка объекта", "Стройгенплан", "Высотная привязка", "Ведомость грузов", "Варианты кранов", "Комплект ППРк")):
            self.nav_tree.insert(views, "end", iid=f"tab_{index}", text=f"   {text}")
        data = self.nav_tree.insert(root, "end", text="▾ Данные проекта", open=True)
        self.nav_tree.insert(data, "end", iid="library_cranes", text="   Каталог кранов")
        self.nav_tree.insert(data, "end", iid="library_regulations", text="   Нормативные документы")
        self.nav_tree.insert(data, "end", text="   Сохранённые варианты")
        self.nav_tree.selection_set("tab_0")
        self.nav_tree.bind("<<TreeviewSelect>>", self._on_project_browser_select)

    def _build_properties_panel(self, parent):
        tk.Label(parent, text="СВОЙСТВА", bg=UI["chrome"], fg=UI["text"], anchor="w", padx=10, pady=7, font=("Segoe UI Semibold", 9)).pack(fill="x")
        self.property_values = {}
        sections = (
            ("Вид", (("Активный вид", "view"), ("Режим", "mode"), ("Масштаб плана", "scale"))),
            ("Объект", (("Название", "project"), ("Город", "city"), ("План", "plan"), ("Разрез", "section"))),
            ("Расчёт", (("Варианты", "scenarios"), ("Приоритет", "priority"), ("Рабочее время", "hours"))),
        )
        for section, rows in sections:
            tk.Label(parent, text=section, bg=UI["panel_alt"], fg=UI["text"], anchor="w", padx=9, pady=4, font=("Segoe UI Semibold", 8)).pack(fill="x", pady=(5, 0))
            for label, key in rows:
                row = tk.Frame(parent, bg=UI["panel"])
                row.pack(fill="x", padx=8, pady=3)
                tk.Label(row, text=label, bg=UI["panel"], fg=UI["muted"], anchor="w", width=14, font=("Segoe UI", 8)).pack(side="left")
                value = tk.Label(row, text="—", bg=UI["field"], fg=UI["text"], anchor="w", padx=6, pady=3, font=("Segoe UI", 8))
                value.pack(side="left", fill="x", expand=True)
                self.property_values[key] = value

    def _show_tab(self, index):
        self.notebook.select(index)

    def _activate_plan_mode(self, mode):
        self._show_tab(1)
        self.set_mode(mode)

    def _on_project_browser_select(self, _event=None):
        selected = self.nav_tree.selection()
        if selected and selected[0].startswith("tab_"):
            self._show_tab(int(selected[0].split("_", 1)[1]))
        elif selected and selected[0] == "library_cranes":
            self.show_library("cranes")
            self.after_idle(self._restore_current_tab_selection)
        elif selected and selected[0] == "library_regulations":
            self.show_library("regulations")
            self.after_idle(self._restore_current_tab_selection)

    def _restore_current_tab_selection(self):
        index = self.notebook.index(self.notebook.select())
        iid = f"tab_{index}"
        if self.nav_tree.exists(iid):
            self.nav_tree.selection_set(iid)

    def show_library(self, library_name: str):
        try:
            library_root, data = load_library(self.resource_root, library_name)
        except Exception as exc:
            messagebox.showerror("Локальная библиотека", f"Не удалось загрузить библиотеку:\n{exc}")
            return

        dialog = tk.Toplevel(self)
        dialog.title(data.get("title", "Локальная библиотека"))
        dialog.geometry("1040x640")
        dialog.minsize(860, 520)
        dialog.configure(bg=UI["window"])
        dialog.transient(self)

        head = tk.Frame(dialog, bg=UI["chrome"], padx=18, pady=14)
        head.pack(fill="x")
        tk.Label(head, text=data.get("title", "Локальная библиотека"), bg=UI["chrome"], fg=UI["text"], font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(head, text=data.get("description", ""), bg=UI["chrome"], fg=UI["muted"], font=("Segoe UI", 9), wraplength=930, justify="left").pack(anchor="w", pady=(4, 0))

        body = tk.PanedWindow(dialog, orient="horizontal", bg=UI["border"], sashwidth=4, bd=0)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        left = tk.Frame(body, bg=UI["panel"])
        right = tk.Frame(body, bg=UI["panel"], padx=16, pady=14)
        body.add(left, minsize=520, stretch="always")
        body.add(right, minsize=300, width=360)

        tree = ttk.Treeview(left, columns=("category", "status"), show="tree headings", selectmode="browse")
        tree.heading("#0", text="Документ / модель")
        tree.heading("category", text="Раздел")
        tree.heading("status", text="Статус")
        tree.column("#0", width=330, minwidth=240)
        tree.column("category", width=150, minwidth=110)
        tree.column("status", width=210, minwidth=140)
        scroll = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        entries = data["entries"]
        by_iid = {}
        for index, entry in enumerate(entries):
            iid = f"doc_{index}"
            by_iid[iid] = entry
            tree.insert("", "end", iid=iid, text=entry.get("title", "Без названия"), values=(entry.get("category", ""), entry.get("status", "")))

        title_var = tk.StringVar(value="Выберите документ")
        category_var = tk.StringVar(value="")
        path_var = tk.StringVar(value="")
        tk.Label(right, textvariable=title_var, bg=UI["panel"], fg=UI["text"], font=("Segoe UI Semibold", 13), wraplength=325, justify="left").pack(anchor="w")
        tk.Label(right, textvariable=category_var, bg=UI["panel"], fg=UI["cyan"], font=("Segoe UI Semibold", 9), wraplength=325, justify="left").pack(anchor="w", pady=(8, 12))
        notes = tk.Text(right, height=12, bg=UI["field"], fg=UI["text"], insertbackground=UI["text"], relief="flat", wrap="word", padx=10, pady=10, font=("Segoe UI", 9))
        notes.pack(fill="both", expand=True)
        notes.configure(state="disabled")
        tk.Label(right, textvariable=path_var, bg=UI["panel"], fg=UI["muted"], font=("Segoe UI", 8), wraplength=325, justify="left").pack(anchor="w", pady=(10, 8))

        selected_entry = {"value": None}

        def show_selected(_event=None):
            selection = tree.selection()
            if not selection:
                return
            entry = by_iid[selection[0]]
            selected_entry["value"] = entry
            title_var.set(entry.get("title", ""))
            category_var.set(f"{entry.get('category', '')}  •  {entry.get('status', '')}")
            local_path = resolve_local_file(library_root, entry.get("local_file", ""))
            path_var.set(f"Локальный файл: {local_path.name}" if local_path.exists() else f"Файл не найден: {local_path.name}")
            details = entry.get("notes", "")
            source = entry.get("source_url", "")
            if source:
                details += f"\n\nИсточник загрузки / официальная карточка:\n{source}"
            notes.configure(state="normal")
            notes.delete("1.0", "end")
            notes.insert("1.0", details)
            notes.configure(state="disabled")

        def open_selected():
            entry = selected_entry["value"]
            if not entry:
                messagebox.showinfo("Локальная библиотека", "Сначала выберите документ.", parent=dialog)
                return
            try:
                open_local_path(resolve_local_file(library_root, entry.get("local_file", "")))
            except Exception as exc:
                messagebox.showerror("Локальная библиотека", f"Не удалось открыть файл:\n{exc}", parent=dialog)

        actions = tk.Frame(right, bg=UI["panel"])
        actions.pack(fill="x")
        ttk.Button(actions, text="Открыть документ", command=open_selected, style="Accent.TButton").pack(side="left", padx=(0, 7))
        if library_name == "cranes":
            ttk.Button(
                actions,
                text="Добавить кран вручную",
                command=lambda: self.show_user_crane_editor(dialog),
            ).pack(side="left", padx=(0, 7))
        ttk.Button(actions, text="Открыть весь список", command=lambda: open_local_path(resolve_local_file(library_root, data.get("index_file", "index.html")))).pack(side="left")
        ttk.Button(actions, text="Открыть папку", command=lambda: open_local_path(library_root)).pack(side="right")

        tree.bind("<<TreeviewSelect>>", show_selected)
        tree.bind("<Double-1>", lambda _event: open_selected())
        if entries:
            tree.selection_set("doc_0")
            show_selected()
        self.status.set(f"Открыта локальная библиотека: {data.get('title', '')}.")

    def show_user_crane_editor(self, parent=None):
        dialog = tk.Toplevel(self)
        dialog.title("Пользовательский каталог башенных кранов")
        dialog.geometry("1120x720")
        dialog.minsize(940, 620)
        dialog.configure(bg=UI["window"])
        dialog.transient(parent or self)

        head = tk.Frame(dialog, bg=UI["chrome"], padx=18, pady=12)
        head.pack(fill="x")
        tk.Label(
            head,
            text="Добавление башенного крана вручную",
            bg=UI["chrome"], fg=UI["text"], font=("Segoe UI Semibold", 15),
        ).pack(anchor="w")
        tk.Label(
            head,
            text=("Введённые характеристики сразу участвуют в предварительном подборе, "
                  "но результат всегда требует экспертной проверки по паспорту крана."),
            bg=UI["chrome"], fg="#ffd166", font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

        body = tk.PanedWindow(dialog, orient="horizontal", bg=UI["border"], sashwidth=4, bd=0)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        list_frame = tk.Frame(body, bg=UI["panel"])
        form = tk.Frame(body, bg=UI["panel"], padx=16, pady=12)
        body.add(list_frame, minsize=430, stretch="always")
        body.add(form, minsize=460, width=560)

        tree = ttk.Treeview(
            list_frame,
            columns=("jib", "capacity", "height"),
            show="tree headings",
            selectmode="browse",
        )
        tree.heading("#0", text="Изготовитель / модель")
        tree.heading("jib", text="Стрела, м")
        tree.heading("capacity", text="Макс., кг")
        tree.heading("height", text="Своб. высота, м")
        tree.column("#0", width=245, minwidth=180)
        tree.column("jib", width=75, anchor="center")
        tree.column("capacity", width=90, anchor="e")
        tree.column("height", width=100, anchor="center")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        variables = {
            "manufacturer": tk.StringVar(),
            "model": tk.StringVar(),
            "jib_length_m": tk.StringVar(),
            "max_capacity_kg": tk.StringVar(),
            "max_free_standing_hook_height_m": tk.StringVar(),
        }
        labels = (
            ("Изготовитель", "manufacturer"),
            ("Модель", "model"),
            ("Длина стрелы, м", "jib_length_m"),
            ("Максимальная грузоподъёмность, кг", "max_capacity_kg"),
            ("Максимальная высота свободного стояния, м", "max_free_standing_hook_height_m"),
        )
        form.columnconfigure(1, weight=1)
        for row, (label, key) in enumerate(labels):
            tk.Label(form, text=label, bg=UI["panel"], fg=UI["text"], anchor="w").grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=4
            )
            ttk.Entry(form, textvariable=variables[key]).grid(row=row, column=1, sticky="ew", pady=4)

        curve_row = len(labels)
        tk.Label(
            form,
            text="Грузовая характеристика: одна строка «вылет, м; груз, кг»",
            bg=UI["panel"], fg=UI["text"], anchor="w",
        ).grid(row=curve_row, column=0, columnspan=2, sticky="w", pady=(10, 4))
        curve_text = tk.Text(
            form, height=10, bg=UI["field"], fg=UI["text"], insertbackground=UI["text"],
            relief="flat", font=("Consolas", 9), padx=8, pady=8,
        )
        curve_text.grid(row=curve_row + 1, column=0, columnspan=2, sticky="nsew")
        form.rowconfigure(curve_row + 1, weight=1)

        tk.Label(form, text="Примечание / источник", bg=UI["panel"], fg=UI["text"]).grid(
            row=curve_row + 2, column=0, columnspan=2, sticky="w", pady=(10, 4)
        )
        notes_text = tk.Text(
            form, height=4, bg=UI["field"], fg=UI["text"], insertbackground=UI["text"],
            relief="flat", wrap="word", padx=8, pady=8,
        )
        notes_text.grid(row=curve_row + 3, column=0, columnspan=2, sticky="ew")

        brochure_var = tk.StringVar()
        brochure_line = tk.Frame(form, bg=UI["panel"])
        brochure_line.grid(row=curve_row + 4, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        brochure_line.columnconfigure(0, weight=1)
        ttk.Entry(brochure_line, textvariable=brochure_var, state="readonly").grid(row=0, column=0, sticky="ew")

        def choose_brochure():
            path = filedialog.askopenfilename(
                title="Выберите PDF-брошюру крана", filetypes=[("PDF", "*.pdf")], parent=dialog
            )
            if path:
                brochure_var.set(path)

        ttk.Button(brochure_line, text="Выбрать PDF-брошюру", command=choose_brochure).grid(
            row=0, column=1, padx=(8, 0)
        )

        entries_by_iid = {}

        def reload_entries(select_id=None):
            tree.delete(*tree.get_children())
            entries_by_iid.clear()
            try:
                entries = load_user_cranes(self.user_catalog_path)
            except Exception as exc:
                messagebox.showerror("Каталог не открыт", str(exc), parent=dialog)
                return
            for index, entry in enumerate(entries):
                iid = f"user_{index}"
                entries_by_iid[iid] = entry
                tree.insert(
                    "", "end", iid=iid,
                    text=f"{entry.get('manufacturer', '')} {entry.get('model', '')}".strip(),
                    values=(
                        f"{float(entry.get('jib_length_m', 0)):g}",
                        f"{float(entry.get('max_capacity_kg', 0)):g}",
                        f"{float(entry.get('max_free_standing_hook_height_m', 0)):g}",
                    ),
                )
                if entry.get("id") == select_id:
                    tree.selection_set(iid)
                    tree.see(iid)

        def save_entry():
            fields = {key: variable.get() for key, variable in variables.items()}
            fields["capacity_curve"] = curve_text.get("1.0", "end")
            fields["notes"] = notes_text.get("1.0", "end")
            try:
                payload = build_user_crane_payload(fields)
                entry = add_user_crane(
                    self.user_catalog_path,
                    payload,
                    brochure_var.get().strip() or None,
                )
            except Exception as exc:
                messagebox.showerror("Кран не добавлен", str(exc), parent=dialog)
                return
            reload_entries(entry["id"])
            self._reset_calculation_results()
            self.status.set(f"Добавлен пользовательский кран: {entry['model']}.")
            messagebox.showinfo(
                "Кран добавлен",
                "Конфигурация включена в предварительный подбор. Перед выпуском ППРк "
                "обязательно проверьте грузовую характеристику по паспорту изготовителя.",
                parent=dialog,
            )

        def selected_entry():
            selection = tree.selection()
            return entries_by_iid.get(selection[0]) if selection else None

        def remove_selected():
            entry = selected_entry()
            if not entry:
                messagebox.showinfo("Удаление", "Выберите пользовательский кран.", parent=dialog)
                return
            if not messagebox.askyesno(
                "Удалить конфигурацию",
                f"Удалить {entry.get('manufacturer', '')} {entry.get('model', '')}?",
                parent=dialog,
            ):
                return
            try:
                delete_user_crane(self.user_catalog_path, entry["id"])
            except Exception as exc:
                messagebox.showerror("Кран не удалён", str(exc), parent=dialog)
                return
            reload_entries()
            self._reset_calculation_results()
            self.status.set("Пользовательская конфигурация крана удалена.")

        def open_brochure():
            entry = selected_entry()
            if not entry or not entry.get("brochure_file"):
                messagebox.showinfo("Брошюра", "Для выбранного крана PDF-брошюра не приложена.", parent=dialog)
                return
            try:
                open_local_path(resolve_local_file(self.user_crane_root, entry["brochure_file"]))
            except Exception as exc:
                messagebox.showerror("Брошюра не открыта", str(exc), parent=dialog)

        buttons = tk.Frame(form, bg=UI["panel"])
        buttons.grid(row=curve_row + 5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Добавить в каталог", command=save_entry, style="Accent.TButton").pack(side="left")
        ttk.Button(buttons, text="Открыть брошюру", command=open_brochure).pack(side="left", padx=8)
        ttk.Button(buttons, text="Удалить выбранный", command=remove_selected).pack(side="right")
        reload_entries()

    def _on_tab_changed(self, _event=None):
        index = self.notebook.index(self.notebook.select())
        if index == 5 and "release_tabs" in self.__dict__:
            self._refresh_completeness()
        iid = f"tab_{index}"
        if self.nav_tree.exists(iid):
            self.nav_tree.selection_set(iid)
            self.nav_tree.see(iid)
        self._update_properties()

    def _update_properties(self):
        if not hasattr(self, "property_values"):
            return
        index = self.notebook.index(self.notebook.select()) if hasattr(self, "notebook") else 0
        names = ("Карточка объекта", "Стройгенплан", "Высотная привязка", "Ведомость грузов", "Варианты кранов", "Комплект ППРк")
        values = {
            "view": names[index],
            "mode": getattr(self, "mode", "—"),
            "scale": f"{self.m_per_pixel:.4f} м/пикс" if self.m_per_pixel else "не задан",
            "project": self.project_name.get() if hasattr(self, "project_name") and self.project_name.get() else "не задано",
            "city": self.city.get() if hasattr(self, "city") and self.city.get() else "не задан",
            "plan": Path(self.plan_pdf).name if self.plan_pdf else "не загружен",
            "section": Path(self.section_pdf).name if self.section_pdf else "не загружен",
            "scenarios": str(len(self.scenarios)),
            "priority": "стоимость" if hasattr(self, "priority") and self.priority.get() == "cost" else "скорость",
            "hours": f"{self.hours.get()} ч/сут" if hasattr(self, "hours") else "—",
        }
        for key, value in values.items():
            self.property_values[key].configure(text=value)

    def _field(self, parent, row, label, default="", width=45):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        var = tk.StringVar(value=str(default))
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        return var

    def _scrollable_tab_body(self, frame):
        """Вертикально прокручиваемая область для экранов небольшой высоты."""
        host=ttk.Frame(frame); host.pack(fill="both",expand=True)
        canvas=tk.Canvas(host,bg=UI["panel"],highlightthickness=0)
        scroll=ttk.Scrollbar(host,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")
        body=ttk.Frame(canvas); window=canvas.create_window((0,0),window=body,anchor="nw")
        body.bind("<Configure>",lambda _event:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda event:canvas.itemconfigure(window,width=event.width))
        def wheel(event): canvas.yview_scroll(int(-event.delta/120),"units"); return "break"
        body.bind("<Enter>",lambda _event:canvas.bind_all("<MouseWheel>",wheel))
        body.bind("<Leave>",lambda _event:canvas.unbind_all("<MouseWheel>"))
        return body

    def _build_project_tab(self):
        frame = self._scrollable_tab_body(self.tabs["1. Проект"])
        form = ttk.LabelFrame(frame, text="Карточка объекта")
        form.pack(fill="x", padx=12, pady=12)
        form.columnconfigure(1, weight=1)
        ttk.Button(form, text="Открыть сохранённый проект", command=self.open_project).grid(row=0,column=2,rowspan=2,padx=8,pady=4,sticky="n")
        self.project_name = self._field(form, 0, "Название объекта")
        self.city = self._field(form, 1, "Город")
        self.year = self._field(form, 2, "Год", "2026")
        self.author = self._field(form, 3, "Автор / разработчик ППРк")
        self.email = self._field(form, 4, "E-mail")
        self.pit_bottom = self._field(form, 5, "Отметка низа котлована, м", "0")
        self.parapet = self._field(form, 6, "Отметка верха парапета, м", "45")
        self.organization = self._field(form, 7, "Организация")
        self.project_code = self._field(form, 8, "Шифр проекта")
        self.project_stage = self._field(form, 9, "Стадия", "ППРк")
        self.checked_by = self._field(form, 10, "Проверил")
        self.approved_by = self._field(form, 11, "Утвердил")
        pdfs = ttk.LabelFrame(frame, text="Исходные PDF")
        pdfs.pack(fill="x", padx=12, pady=8)
        self.plan_label = ttk.Label(pdfs, text="План не выбран")
        self.plan_label.grid(row=0, column=1, sticky="w", padx=6, pady=5)
        ttk.Button(pdfs, text="Выбрать план PDF", command=self.choose_plan).grid(row=0, column=0, padx=6, pady=5)
        self.section_label = ttk.Label(pdfs, text="Разрез не выбран")
        self.section_label.grid(row=1, column=1, sticky="w", padx=6, pady=5)
        ttk.Button(pdfs, text="Выбрать разрез PDF", command=self.choose_section).grid(row=1, column=0, padx=6, pady=5)
        ttk.Label(frame, text="Разрез используется для высотной привязки. В первой версии отметки вводятся вручную и проверяются по выбранному PDF.", wraplength=900).pack(anchor="w", padx=18, pady=8)

    def _build_plan_tab(self):
        frame = self.tabs["2. План"]
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", padx=6, pady=5)
        self.distance_var = tk.StringVar(value="10")
        ttk.Label(toolbar, text="Известное расстояние, м:").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.distance_var, width=8).pack(side="left", padx=4)
        ttk.Button(toolbar, text="1. Масштаб: выбрать 2 точки", command=lambda: self.set_mode("calibration")).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Авто: предложить границу", command=self.auto_suggest_boundary).pack(side="left", padx=3)
        viewbar=ttk.Frame(frame); viewbar.pack(fill="x",padx=6,pady=(0,5))
        ttk.Button(viewbar, text="Окно подложки", command=self.start_plan_crop).pack(side="left", padx=3)
        ttk.Button(viewbar, text="Вся страница", command=self.reset_plan_crop).pack(side="left", padx=3)
        ttk.Label(viewbar, text="Фон, %:").pack(side="left", padx=(12,2))
        ttk.Entry(viewbar, textvariable=self.plan_background_intensity, width=5).pack(side="left")
        ttk.Button(viewbar, text="Применить", command=self.apply_plan_background).pack(side="left", padx=3)
        ttk.Button(viewbar, text="−", width=3, command=lambda:self._zoom_plan(1/1.2)).pack(side="left", padx=(12,2))
        ttk.Button(viewbar, text="+", width=3, command=lambda:self._zoom_plan(1.2)).pack(side="left", padx=2)
        ttk.Button(viewbar, text="100%", command=lambda:self._set_plan_zoom(1.0)).pack(side="left", padx=2)
        ttk.Button(viewbar, text="Вписать", command=self._fit_plan).pack(side="left", padx=2)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", padx=6, pady=(0, 5))
        ttk.Button(actions, text="2. Граница площадки", command=lambda: self.set_mode("site")).pack(side="left", padx=3)
        ttk.Button(actions, text="3. Контур здания", command=lambda: self.set_mode("building")).pack(side="left", padx=3)
        ttk.Button(actions, text="4. Запретная зона", command=lambda: self.set_mode("restricted")).pack(side="left", padx=3)
        ttk.Button(actions, text="Замкнуть контур", command=self.finish_contour).pack(side="left", padx=3)
        ttk.Button(actions, text="Отменить сегмент", command=self.undo_contour_point).pack(side="left", padx=3)
        ttk.Button(actions, text="5. Точки подачи грузов", command=lambda: self.set_mode("workpoint")).pack(side="left", padx=3)
        ttk.Button(actions, text="Очистить разметку", command=self.clear_markup).pack(side="right", padx=3)
        zones = ttk.Frame(frame)
        zones.pack(fill="x", padx=6, pady=(0, 5))
        ttk.Button(zones, text="6. Зона разгрузки", command=lambda: self.set_mode("unloading")).pack(side="left", padx=3)
        ttk.Button(zones, text="7. Зона складирования", command=lambda: self.set_mode("storage")).pack(side="left", padx=3)
        self.no_restricted_confirmed=tk.BooleanVar(value=False)
        ttk.Checkbutton(zones,text="Запретных зон нет (проверено)",variable=self.no_restricted_confirmed).pack(side="left",padx=8)
        ttk.Label(zones, text="Точка подачи — место на здании, куда кран должен доставить груз. Для зон укажите вершины и замкните контур.").pack(side="left", padx=10)
        canvas_frame=ttk.Frame(frame,style="Workspace.TFrame"); canvas_frame.pack(fill="both",expand=True,padx=6,pady=5)
        canvas_frame.rowconfigure(0,weight=1); canvas_frame.columnconfigure(0,weight=1)
        self.canvas = tk.Canvas(canvas_frame, bg=UI["workspace"], cursor="crosshair", highlightthickness=1, highlightbackground=UI["border"])
        plan_x=ttk.Scrollbar(canvas_frame,orient="horizontal",command=self.canvas.xview); plan_y=ttk.Scrollbar(canvas_frame,orient="vertical",command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=plan_x.set,yscrollcommand=plan_y.set)
        self.canvas.grid(row=0,column=0,sticky="nsew"); plan_y.grid(row=0,column=1,sticky="ns"); plan_x.grid(row=1,column=0,sticky="ew")
        zone_panel=ttk.LabelFrame(canvas_frame,text="Опасные зоны")
        zone_panel.grid(row=0,column=2,rowspan=2,sticky="ns",padx=(6,0))
        self.zone_tree=ttk.Treeview(zone_panel,columns=("type","height"),show="tree headings",height=12)
        self.zone_tree.heading("#0",text="Имя"); self.zone_tree.heading("type",text="Тип"); self.zone_tree.heading("height",text="H, м")
        self.zone_tree.column("#0",width=120); self.zone_tree.column("type",width=150); self.zone_tree.column("height",width=55,anchor="e")
        self.zone_tree.pack(fill="both",expand=True,padx=5,pady=5)
        self.zone_tree.bind("<<TreeviewSelect>>",self._on_zone_table_select)
        zone_buttons=ttk.Frame(zone_panel); zone_buttons.pack(fill="x",padx=5,pady=(0,5))
        ttk.Button(zone_buttons,text="Изменить",command=self.edit_selected_restricted_zone).pack(side="left",padx=2)
        ttk.Button(zone_buttons,text="Удалить",command=self.delete_selected_restricted_zone).pack(side="left",padx=2)
        self.canvas.bind("<ButtonPress-1>", self._on_plan_press)
        self.canvas.bind("<B1-Motion>", self._on_plan_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_plan_release)
        self.canvas.bind("<MouseWheel>", self._on_plan_wheel)
        self.canvas.bind("<ButtonPress-2>", lambda e:self.canvas.scan_mark(e.x,e.y))
        self.canvas.bind("<B2-Motion>", lambda e:self.canvas.scan_dragto(e.x,e.y,gain=1))

    def _build_section_tab(self):
        frame = self.tabs["3. Разрез"]
        toolbar = ttk.Frame(frame); toolbar.pack(fill="x", padx=6, pady=5)
        self.section_distance_var = tk.StringVar(value="50")
        ttk.Label(toolbar, text="Высота между двумя точками, м:").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.section_distance_var, width=8).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Выбрать низ и верх на разрезе", command=self.start_section_calibration).pack(side="left", padx=3)
        viewbar=ttk.Frame(frame); viewbar.pack(fill="x",padx=6,pady=(0,5))
        ttk.Button(viewbar, text="Окно подложки", command=self.start_section_crop).pack(side="left", padx=3)
        ttk.Button(viewbar, text="Вся страница", command=self.reset_section_crop).pack(side="left", padx=3)
        ttk.Label(viewbar, text="Фон, %:").pack(side="left", padx=(12,2))
        ttk.Entry(viewbar, textvariable=self.section_background_intensity, width=5).pack(side="left")
        ttk.Button(viewbar, text="Применить", command=self.apply_section_background).pack(side="left", padx=3)
        ttk.Button(viewbar, text="−", width=3, command=lambda:self._zoom_section(1/1.2)).pack(side="left", padx=(12,2))
        ttk.Button(viewbar, text="+", width=3, command=lambda:self._zoom_section(1.2)).pack(side="left", padx=2)
        ttk.Button(viewbar, text="100%", command=lambda:self._set_section_zoom(1.0)).pack(side="left", padx=2)
        ttk.Button(viewbar, text="Вписать", command=self._fit_section).pack(side="left", padx=2)
        tiebar=ttk.Frame(frame); tiebar.pack(fill="x",padx=6,pady=(0,5))
        self.floors=tk.StringVar(value="20"); self.tie_length=tk.StringVar(value="12"); self.tie_angle=tk.StringVar(value="60"); self.tie_ins_possible=tk.BooleanVar(value=True)
        ttk.Label(tiebar,text="Этажей:").pack(side="left"); ttk.Entry(tiebar,textvariable=self.floors,width=5).pack(side="left",padx=(2,8))
        ttk.Checkbutton(tiebar,text="Допускаются пристёжки",variable=self.tie_ins_possible).pack(side="left",padx=4)
        ttk.Label(tiebar,text="Тяга, м:").pack(side="left",padx=(8,2)); ttk.Entry(tiebar,textvariable=self.tie_length,width=5).pack(side="left")
        ttk.Label(tiebar,text="Угол, °:").pack(side="left",padx=(8,2)); ttk.Entry(tiebar,textvariable=self.tie_angle,width=5).pack(side="left")
        ttk.Button(tiebar,text="Контур здания",command=self.start_section_building_contour).pack(side="left",padx=(14,3))
        ttk.Button(tiebar,text="Замкнуть",command=self.finish_section_building_contour).pack(side="left",padx=3)
        ttk.Button(tiebar,text="Отменить точку",command=self.undo_section_contour_point).pack(side="left",padx=3)
        ttk.Button(tiebar,text="Очистить контур",command=self.clear_section_building_contour).pack(side="left",padx=3)
        section_frame=ttk.Frame(frame,style="Workspace.TFrame"); section_frame.pack(fill="both",expand=True,padx=6,pady=5)
        section_frame.rowconfigure(0,weight=1); section_frame.columnconfigure(0,weight=1)
        self.section_canvas = tk.Canvas(section_frame, bg=UI["workspace"], cursor="crosshair", highlightthickness=1, highlightbackground=UI["border"])
        section_x=ttk.Scrollbar(section_frame,orient="horizontal",command=self.section_canvas.xview); section_y=ttk.Scrollbar(section_frame,orient="vertical",command=self.section_canvas.yview)
        self.section_canvas.configure(xscrollcommand=section_x.set,yscrollcommand=section_y.set)
        self.section_canvas.grid(row=0,column=0,sticky="nsew"); section_y.grid(row=0,column=1,sticky="ns"); section_x.grid(row=1,column=0,sticky="ew")
        self.section_canvas.bind("<ButtonPress-1>", self._on_section_press)
        self.section_canvas.bind("<B1-Motion>", self._on_section_drag)
        self.section_canvas.bind("<ButtonRelease-1>", self._on_section_release)
        self.section_canvas.bind("<MouseWheel>", self._on_section_wheel)
        self.section_canvas.bind("<ButtonPress-2>", lambda e:self.section_canvas.scan_mark(e.x,e.y))
        self.section_canvas.bind("<B2-Motion>", lambda e:self.section_canvas.scan_dragto(e.x,e.y,gain=1))

    def _build_loads_tab(self):
        frame = self.tabs["4. Грузы"]
        ttk.Label(frame, text="Стандартные стартовые массы необходимо подтвердить или отредактировать. Укажите нестандартное оборудование для кровли отдельной строкой.", wraplength=1000).pack(anchor="w", padx=10, pady=8)
        columns = ("name", "load", "rigging", "length", "width", "height", "lifts", "active")
        self.load_tree = ttk.Treeview(frame, columns=columns, show="headings", height=16)
        labels = ("Груз", "Масса, кг", "Оснастка, кг", "Длина, м", "Ширина, м", "Высота, м", "Подъёмов", "В проекте")
        for col, label in zip(columns, labels):
            self.load_tree.heading(col, text=label)
            self.load_tree.column(col, width=125 if col == "name" else 90)
        self.load_tree.pack(fill="both", expand=True, padx=10, pady=5)
        for load in self.loads:
            self.load_tree.insert("", "end", values=_load_editor_values(load))
        buttons = ttk.Frame(frame); buttons.pack(fill="x", padx=10, pady=5)
        ttk.Button(buttons, text="Редактировать выбранный", command=self.edit_load).pack(side="left")
        ttk.Button(buttons, text="Добавить нестандартный груз", command=lambda: self.edit_load(new=True)).pack(side="left", padx=6)
        ttk.Button(buttons, text="Удалить выбранный груз", command=self.delete_load).pack(side="left", padx=6)
        ttk.Checkbutton(
            frame,
            text="Массы грузов и оснастки сверены с проектными документами",
            variable=self.loads_verified,
            command=self._reset_calculation_results,
        ).pack(anchor="w", padx=10, pady=(4, 10))

    def _build_calculation_tab(self):
        frame = self.tabs["5. Расчёт"]
        options = ttk.LabelFrame(frame, text="Настройки")
        options.pack(fill="x", padx=10, pady=10)
        self.priority = tk.StringVar(value="cost")
        ttk.Label(options, text="Что важнее?").grid(row=0, column=0, padx=5, pady=5)
        ttk.Radiobutton(options, text="Минимум кранов / стоимость при наличии КП", variable=self.priority, value="cost").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(options, text="Скорость (показывать два крана)", variable=self.priority, value="speed").grid(row=0, column=2, sticky="w")
        self.hours = self._field(options, 1, "Рабочих часов в сутки", "24", 10)
        self.utilization = self._field(options, 2, "Коэффициент использования", "0.7", 10)
        self.min_distance = self._field(options, 3, "Минимум от здания, м", "1", 10)
        self.max_distance = self._field(options, 4, "Максимум от здания, м", "25", 10)
        self.screen_possible = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Возможно защитное ограждение на монтажном горизонте", variable=self.screen_possible).grid(row=5, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Label(options, text="?  Положительный ответ не отменяет отдельный проект и повторную проверку опасной зоны.").grid(row=6, column=1, columnspan=2, sticky="w")
        self.commercial_offer = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Есть коммерческое предложение", variable=self.commercial_offer).grid(row=7,column=1,columnspan=2,sticky="w",pady=4)
        self.daily_cost = self._field(options, 8, "Стоимость одного крана в сутки, руб.", "0", 14)
        calculation_bar=ttk.Frame(frame); calculation_bar.pack(fill="x",padx=10,pady=8)
        ttk.Button(calculation_bar, text="ПЕРЕСЧИТАТЬ СЕЙЧАС", command=self.run_calculation, style="Accent.TButton").pack(side="left")
        self.calculation_state_var=tk.StringVar(value="Нет актуального расчёта")
        ttk.Label(calculation_bar,textvariable=self.calculation_state_var).pack(side="left",padx=12)
        ttk.Button(calculation_bar,text="Игнорировать предупреждение",command=self.accept_selected_warning).pack(side="right")
        release_bar = ttk.Frame(frame)
        release_bar.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Label(release_bar, text="Вариант для выпуска:").pack(side="left")
        self.release_variant_combo = ttk.Combobox(
            release_bar,
            textvariable=self.release_variant_var,
            values=(),
            state="readonly",
            width=52,
        )
        self.release_variant_combo.pack(side="left", padx=8)
        self.release_variant_combo.bind("<<ComboboxSelected>>", self._on_release_variant_selected)
        self.results = tk.Text(frame, height=24, wrap="word", bg=UI["field"], fg=UI["text"], insertbackground=UI["text"], selectbackground=UI["selection"], relief="flat", padx=10, pady=8)
        self.results.pack(fill="both", expand=True, padx=10, pady=8)

    def _build_report_tab(self):
        frame = self.tabs["6. Отчёт"]
        self.release_config = PPRKReleaseConfig()
        self.preview_fingerprint = None
        self._release_refresh_job = None
        self.release_vars = {}
        self.report_selection_var = tk.StringVar(value="Предпросмотр ещё не сформирован")
        self.report_path_var = tk.StringVar()
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", padx=6, pady=4)
        ttk.Button(buttons, text="Предпросмотр", command=self.preview_report_pages).pack(side="left")
        ttk.Button(buttons, text="Сохранить проект и PDF", command=self.save_and_report).pack(side="left", padx=4)
        ttk.Label(frame, textvariable=self.report_selection_var).pack(anchor="w", padx=8)
        ttk.Style(self).map("Release.TCombobox", fieldbackground=[("readonly", UI["field"])], foreground=[("readonly", UI["text"])])
        self.release_tabs = ttk.Notebook(frame)
        self.release_tabs.pack(fill="both", expand=True, padx=4)
        panels = {}
        for title in ("Реквизиты", "Согласования", "Разделы", "Приложения", "Комплектность"):
            panels[title] = ttk.Frame(self.release_tabs)
            self.release_tabs.add(panels[title], text=title)
        fields = self._scrollable_tab_body(panels["Реквизиты"])
        fields.columnconfigure(1, weight=1)
        for row, (key, label) in enumerate(RELEASE_FIELDS.items()):
            self.release_vars[key] = self._field(fields, row, label, width=16)
        self.approval_tree = self._release_table(panels["Согласования"],
            ("№", "Организация", "Должность", "ФИО", "Подпись", "Дата", "Роль"), 8,
            (30, 110, 95, 110, 80, 75, 80))
        bar = ttk.Frame(panels["Согласования"])
        bar.pack(fill="x")
        for action, label in (("edit", "Изменить"), ("add", "Добавить"), ("remove", "Удалить"), ("reset", "Очистить все")):
            ttk.Button(bar, text=label, command=lambda a=action: self._edit_approval(a)).pack(side="left")
        self.approval_tree.bind("<Double-1>", lambda _: self._edit_approval("edit"))

        sections = self._scrollable_tab_body(panels["Разделы"])
        sections.columnconfigure(1, weight=1)
        self.release_vars["included_section_ids"] = self._field(sections, 0, "Включить (ID через запятую)", width=16)
        self.release_vars["excluded_section_ids"] = self._field(sections, 1, "Исключить (ID через запятую)", width=16)
        table_frame = ttk.Frame(sections)
        table_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.section_tree = self._release_table(table_frame, ("ID", "Раздел", "Включён", "Причина"), 6,
                                                (145, 210, 65, 340))
        override_frame = ttk.LabelFrame(sections, text="Ручные правки абзацев")
        override_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.override_tree = self._release_table(override_frame, ("ID абзаца", "Версия", "Текст"), 3, (170, 70, 300))
        self._record_buttons(override_frame, "overrides")

        self.external_tree = self._release_table(panels["Приложения"],
            tuple(EXTERNAL_FIELDS.values()), 7, (120, 160, 65, 65, 80, 90, 120, 100, 260, 65))
        self._record_buttons(panels["Приложения"], "external_documents")
        checks = panels["Комплектность"]
        status_bar = ttk.Frame(checks)
        status_bar.pack(anchor="w", pady=3)
        ttk.Label(status_bar, text="Запросить статус").pack(side="left")
        self.release_status_var = tk.StringVar(value=ReleaseStatus.PRELIMINARY.value)
        ttk.Combobox(status_bar, style="Release.TCombobox", textvariable=self.release_status_var, state="readonly", width=16,
                     values=[s.value for s in ReleaseStatus]).pack(side="left", padx=4)
        ttk.Button(status_bar, text="Проверить", command=self._refresh_completeness).pack(side="left")
        self.release_summary = ttk.Label(checks, text="Выберите вариант расчёта", wraplength=465)
        self.release_summary.pack(anchor="w", padx=4)
        self.issue_text = tk.Text(checks, wrap="word", height=6, width=40, bg=UI["field"], fg=UI["text"])
        issue_scroll = ttk.Scrollbar(checks, command=self.issue_text.yview)
        self.issue_text.configure(yscrollcommand=issue_scroll.set)
        issue_scroll.pack(side="right", fill="y")
        self.issue_text.pack(fill="both", expand=True)
        ttk.Label(frame, textvariable=self.report_path_var, wraplength=480).pack(anchor="w", padx=6)
        self._load_release_config(self.release_config)
        for var in (*self.release_vars.values(), self.release_status_var, self.release_variant_var):
            var.trace_add("write", self._invalidate_release)

    @staticmethod
    def _release_table(parent, columns, height, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
        for name, width in zip(columns, widths):
            tree.heading(name, text=name)
            tree.column(name, width=width, stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        for orientation, command, row, column, sticky in (
            ("horizontal", tree.xview, 1, 0, "ew"), ("vertical", tree.yview, 0, 1, "ns")
        ):
            scroll = ttk.Scrollbar(frame, orient=orientation, command=command)
            scroll.grid(row=row, column=column, sticky=sticky)
            tree.configure(**{("xscrollcommand" if orientation == "horizontal" else "yscrollcommand"): scroll.set})
        return tree

    def _load_release_config(self, config):
        self.release_config = replace(config, approvals=approval_rows(config.approvals))
        for key, var in self.release_vars.items():
            value = getattr(config, key)
            var.set(", ".join(value) if isinstance(value, list) else "" if value is None else str(value))
        self.release_status_var.set(config.status.value)
        self._refresh_release_records()

    def _editor_config(self):
        config = edit_release_fields(self.release_config, {key: var.get() for key, var in self.release_vars.items()})
        return replace(config, status=ReleaseStatus(self.release_status_var.get()))

    def _refresh_release_records(self):
        for tree, records in ((self.approval_tree, self.release_config.approvals),
                              (self.override_tree, self.release_config.overrides),
                              (self.external_tree, self.release_config.external_documents)):
            tree.delete(*tree.get_children())
            for index, record in enumerate(records):
                values = [("да" if value else "нет") if isinstance(value, bool) else value or ""
                          for value in vars(record).values()]
                if tree is self.approval_tree:
                    values.insert(0, index + 1)
                tree.insert("", "end", iid=str(index), values=values)

    def _invalidate_release(self, *_args):
        if "release_tabs" not in self.__dict__:
            return
        self.preview_fingerprint = None
        self.report_selection_var.set("Предпросмотр устарел — сформируйте комплект заново")
        if self._release_refresh_job is not None:
            self.after_cancel(self._release_refresh_job)
        self._release_refresh_job = self.after(250, self._refresh_completeness)

    def _refresh_completeness(self):
        self._release_refresh_job = None
        if self.notebook.select() != str(self.tabs["6. Отчёт"]):
            return
        self.section_tree.delete(*self.section_tree.get_children())
        try:
            project = self._project(require_geometry=False)
            project.pprk_release = self._editor_config()
            index = self._selected_release_index()
            current = index is not None and index < len(self.scenarios) and self._calculation_is_current(project)
            if current:
                scenario, verification = self.scenarios[index], self.scenario_verifications[index]
                require_selected_protocol(index, verification)
            else:
                scenario = ScenarioResult("BLOCKED", [], [], [])
                verification = ScenarioVerificationV21(-1, IntegrationStatus.REJECTED, False, (), None, None)
            view = prepare_release(project, scenario, verification)
            self.release_summary.configure(text=f"Запрошен {view.bundle.requested_status.value}  •  Доступен {view.bundle.effective_status.value}")
            for key, title, included, reason in view.sections:
                self.section_tree.insert("", "end", values=(key, title, "да" if included else "нет", reason))
            lines = [] if current else ["Расчёт • выполните актуальный расчёт и выберите вариант."]
            for issue in view.issues:
                prefix = "Блокирует" if issue.blocking else "Замечание"
                lines.append(f"{prefix} • {issue.field_id}\n{issue.message}\n{issue_action(issue)}")
            if verification.messages:
                lines.extend(verification.messages)
            text = "\n\n".join(lines) or "Замечаний нет."
        except (ValueError, OSError) as exc:
            self.release_summary.configure(text=f"Запрошен {self.release_status_var.get()}  •  Выпуск недоступен")
            text = f"Блокирует • {exc}"
        self.issue_text.configure(state="normal")
        self.issue_text.delete("1.0", "end")
        self.issue_text.insert("1.0", text)
        self.issue_text.configure(state="disabled")

    def _record_buttons(self, panel, field):
        bar = ttk.Frame(panel)
        bar.pack(fill="x")
        for label, action in (("Добавить", "add"), ("Изменить", "edit"), ("Удалить", "remove")):
            ttk.Button(bar, text=label, command=lambda a=action: self._edit_record(field, a)).pack(side="left")

    def _edit_approval(self, action):
        rows = self.release_config.approvals
        selected = self.approval_tree.selection()
        if action == "add":
            index = next((i for i, row in enumerate(rows) if not any(vars(row).values())), None)
            if index is None:
                messagebox.showinfo("Согласования", "Все восемь строк заняты. Выберите строку для изменения.")
                return
        elif action == "reset":
            if not messagebox.askyesno("Согласования", "Очистить все восемь строк?"):
                return
            index = None
        elif selected:
            index = int(selected[0])
        else:
            return
        if action in ("edit", "add"):
            values = self._record_dialog("Согласование", APPROVAL_FIELDS, rows[index])
            if values is None:
                return
            rows[index] = ApprovalSlot(**values)
        else:
            self.release_config.approvals = approval_rows(rows, action, index)
        self._refresh_release_records()
        self._invalidate_release()

    def _edit_record(self, field, action):
        external = field == "external_documents"
        tree = self.external_tree if external else self.override_tree
        records = getattr(self.release_config, field)
        selected = tree.selection()
        if not selected and action != "add":
            return
        index = len(records) if action == "add" else int(selected[0])
        if action == "remove":
            del records[index]
        else:
            if action == "add":
                record = ExternalDocument("", "") if external else TemplateOverride("", "", "")
            else:
                record = records[index]
            values = self._record_dialog("Внешний документ" if external else "Правка абзаца",
                                         EXTERNAL_FIELDS if external else OVERRIDE_FIELDS, record)
            if values is None:
                return
            result = type(record)(**values)
            if action == "add":
                records.append(result)
            else:
                records[index] = result
        self._refresh_release_records()
        self._invalidate_release()

    def _record_dialog(self, title, labels, record):
        paragraphs = {}
        if isinstance(record, TemplateOverride):
            try:
                paragraphs = {p.paragraph_id: p for section in load_template_catalog() for p in section.paragraphs}
            except ValueError as exc:
                messagebox.showwarning(title, f"Проверьте каталог шаблонов. {exc}")
                return None
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)
        variables = {}
        confirmed_digest = getattr(record, "verified_sha256", "")
        result = []
        for row, (key, label) in enumerate(labels.items()):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)
            value = getattr(record, key)
            if isinstance(value, bool):
                var = tk.BooleanVar(dialog, value=value)
                widget = ttk.Checkbutton(dialog, variable=var)
            elif key == "replacement_text":
                widget = tk.Text(dialog, height=7, width=45, wrap="word")
                widget.insert("1.0", value)
                var = None
                replacement = widget
            else:
                var = tk.StringVar(dialog, value="" if value is None else str(value))
                if key == "paragraph_id":
                    widget = ttk.Combobox(dialog, textvariable=var, values=tuple(paragraphs), width=37)
                    def select_paragraph(_event):
                        paragraph = paragraphs[variables["paragraph_id"].get()]
                        variables["base_version"].set(paragraph.version)
                        replacement.delete("1.0", "end")
                        replacement.insert("1.0", paragraph.text)
                    widget.bind("<<ComboboxSelected>>", select_paragraph)
                elif key == "verification_status":
                    widget = ttk.Combobox(dialog, style="Release.TCombobox", textvariable=var, values=("UNVERIFIED", "VERIFIED"), state="readonly")
                    def confirm_revision(_event):
                        nonlocal confirmed_digest
                        confirmed_digest = ""
                        if variables["verification_status"].get() == "VERIFIED":
                            try:
                                selected = replace(record, present=variables["present"].get(),
                                                   attachment_path=variables["attachment_path"].get())
                                confirmed_digest = verify_external_revision(selected).verified_sha256
                            except ValueError as exc:
                                variables["verification_status"].set("UNVERIFIED")
                                messagebox.showwarning(title, str(exc), parent=dialog)
                    widget.bind("<<ComboboxSelected>>", confirm_revision)
                else:
                    widget = ttk.Entry(dialog, textvariable=var, width=37)
            widget.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
            variables[key] = var
            if key == "attachment_path":
                def choose_pdf():
                    path = filedialog.askopenfilename(parent=dialog, filetypes=[("PDF", "*.pdf")])
                    if path:
                        variables["attachment_path"].set(path)
                        variables["present"].set(True)
                var.trace_add("write", lambda *_: variables["verification_status"].set("UNVERIFIED"))
                ttk.Button(dialog, text="PDF…", command=choose_pdf).grid(row=row, column=2)
        def apply():
            values = {k: var.get() if var is not None else replacement.get("1.0", "end-1c")
                      for k, var in variables.items()}
            if "appendix_order" in values:
                values["verified_sha256"] = confirmed_digest if values["verification_status"] == "VERIFIED" else ""
                if values["verification_status"] == "VERIFIED" and (
                    not values["verified_sha256"] or values["verified_sha256"] != source_digest(values["attachment_path"])
                ):
                    variables["verification_status"].set("UNVERIFIED")
                    messagebox.showwarning(title, "PDF изменился. Подтвердите проверку текущей ревизии.", parent=dialog)
                    return
                try:
                    values["appendix_order"] = int(values["appendix_order"]) if values["appendix_order"].strip() else None
                except ValueError:
                    messagebox.showwarning(title, "Укажите целое число для порядка приложения.", parent=dialog)
                    return
                if not values["document_id"].strip() or not values["title"].strip():
                    messagebox.showwarning(title, "Заполните ID и название документа.", parent=dialog)
                    return
            result.append(values)
            dialog.destroy()
        ttk.Button(dialog, text="Сохранить", command=apply).grid(row=len(labels), column=1, sticky="e", pady=5)
        self.wait_window(dialog)
        return result[0] if result else None

    def _current_release_inputs(self):
        index = self._selected_release_index()
        if index is None or index >= len(self.scenarios):
            raise ValueError("Выполните расчёт и выберите вариант для выпуска.")
        require_selected_protocol(index, self.scenario_verifications[index])
        project = self._project()
        if not self._calculation_is_current(project):
            raise ValueError("Данные изменились после расчёта. Выполните расчёт повторно.")
        if "release_vars" in self.__dict__:
            project.pprk_release = self._editor_config()
        return project, self.scenarios[index], self.scenario_verifications[index], index

    def _current_release_fingerprint(self):
        return release_fingerprint(*self._current_release_inputs())

    def _watch_preview_sources(self, fingerprint):
        if self.preview_fingerprint != fingerprint:
            return
        try:
            current = self._current_release_fingerprint()
        except (OSError, ValueError):
            current = None
        if current != fingerprint:
            self._invalidate_release()
        else:
            self.after(1500, lambda: self._watch_preview_sources(fingerprint))


    def open_project(self):
        path=filedialog.askopenfilename(title="Открыть проект КранПлан",filetypes=[("Проект КранПлан","project.json"),("JSON","*.json")])
        if not path: return
        try:
            project=load_project(path)
            self._load_release_config(project.pprk_release)
            for var,value in (
                (self.project_name,project.name),(self.city,project.city),(self.year,project.year),(self.author,project.author),(self.email,project.email),
                (self.pit_bottom,project.pit_bottom_m),(self.parapet,project.parapet_m),(self.organization,project.organization),(self.project_code,project.project_code),
                (self.project_stage,project.project_stage),(self.checked_by,project.checked_by),(self.approved_by,project.approved_by),(self.hours,project.hours_per_day),
                (self.utilization,project.utilization),(self.min_distance,project.site.min_crane_to_building_m),(self.max_distance,project.site.max_crane_to_building_m),
                (self.daily_cost,project.commercial_offer_daily_cost),
                (self.floors,project.floors),(self.tie_length,project.tie_length_m),(self.tie_angle,project.tie_angle_deg),
            ): var.set(str(value))
            self.priority.set(project.priority); self.screen_possible.set(project.protective_screen_possible); self.commercial_offer.set(project.commercial_offer_present); self.tie_ins_possible.set(project.tie_ins_possible); self.loads_verified.set(project.loads_verified)
            self.site_points=list(project.site.boundary); self.building_points=list(project.site.building); self.restricted_zones=list(project.site.restricted_zones)
            self.unloading_points=list(project.site.unloading_zone); self.storage_zones=[list(z) for z in project.site.storage_zones]; self.work_points=list(project.work_points)
            self.current_zone_points=[]; self.current_storage_points=[]; self.closed_contours={"site","building"}
            if self.unloading_points: self.closed_contours.add("unloading")
            self.m_per_pixel=project.plan_m_per_pixel or None; self.origin_px=(project.plan_origin_x_px,project.plan_origin_y_px) if self.m_per_pixel else None
            self.section_m_per_pixel=project.section_m_per_pixel or None
            self.section_origin_px=(project.section_origin_x_px,project.section_origin_y_px) if self.section_m_per_pixel else None
            self.section_axis=(project.section_axis_dx,project.section_axis_dy)
            self.section_building_points=list(project.section_building_contour); self.section_contour_closed=bool(self.section_building_points)
            self._normalize_section_building_reference()
            self.plan_crop_box=normalize_crop_box(project.plan_crop_box); self.section_crop_box=normalize_crop_box(project.section_crop_box)
            self.plan_background_intensity.set(str(round(project.plan_background_intensity*100)))
            self.section_background_intensity.set(str(round(project.section_background_intensity*100)))
            self.plan_pdf=project.source_plan_pdf if project.source_plan_pdf and Path(project.source_plan_pdf).is_file() else ""
            self.section_pdf=project.source_section_pdf if project.source_section_pdf and Path(project.source_section_pdf).is_file() else ""
            self.load_tree.delete(*self.load_tree.get_children())
            for load in project.loads: self.load_tree.insert("","end",values=_load_editor_values(load))
            self.no_restricted_confirmed.set(project.restricted_zones_confirmed)
            self.warning_acceptances=list(project.warning_acceptances)
            self._refresh_zone_table()
            if self.plan_pdf:
                self.plan_label.config(text=Path(self.plan_pdf).name); self._show_plan(); self._redraw_loaded_markup()
            else: self.plan_label.config(text="Исходный план не найден; выберите PDF повторно")
            if self.section_pdf:
                self.section_label.config(text=Path(self.section_pdf).name); self._show_section(); self._redraw_section_calibration()
            else: self.section_label.config(text="Исходный разрез не найден; выберите PDF повторно")
            self._reset_calculation_results(); self.report_page_order=None; self.report_excluded_pages.clear()
            self.status.set(f"Проект открыт: {Path(path).parent}")
        except Exception as exc: messagebox.showerror("Проект не открыт",str(exc))

    def _world_to_canvas(self, point):
        px=self.origin_px[0]+point[0]/self.m_per_pixel; py=self.origin_px[1]-point[1]/self.m_per_pixel
        return px*self.image_scale,py*self.image_scale

    def _redraw_loaded_markup(self):
        if not self.origin_px or not self.m_per_pixel: return
        self.contour_pixels={"site":[],"building":[],"restricted":[],"unloading":[],"storage":[]}
        def draw_polygon(points,color,tag):
            if not points: return
            pixels=[self._world_to_canvas(p) for p in points]; coords=[v for p in pixels for v in p]
            self.canvas.create_polygon(*coords,outline=color,fill="",width=2,tags=("markup",tag)); return pixels
        self.contour_pixels["site"]=draw_polygon(self.site_points,DRAW_COLORS["site"],"draw_site") or []
        self.contour_pixels["building"]=draw_polygon(self.building_points,DRAW_COLORS["building"],"draw_building") or []
        self.contour_pixels["unloading"]=draw_polygon(self.unloading_points,DRAW_COLORS["unloading"],"draw_unloading") or []
        for i,zone in enumerate(self.restricted_zones): self._draw_restricted_zone(zone,i)
        for i,zone in enumerate(self.storage_zones): draw_polygon(zone,DRAW_COLORS["storage"],f"draw_storage_{i}")
        for i,wp in enumerate(self.work_points,1):
            x,y=self._world_to_canvas(wp.point); self.canvas.create_oval(x-4,y-4,x+4,y+4,fill=DRAW_COLORS["workpoint"],tags="markup"); self.canvas.create_text(x+7,y-7,text=str(i),anchor="w",fill=DRAW_COLORS["workpoint"],tags="markup")
        self._draw_selected_sozr()
        self.canvas.tag_raise("markup")

    def _on_release_variant_selected(self,_event=None) -> None:
        self._selected_release_index()
        self._draw_selected_sozr()

    def _draw_selected_sozr(self) -> None:
        if "canvas" not in self.__dict__:
            return
        self.canvas.delete("sozr")
        index=self._selected_release_index()
        if index is None or index>=len(self.scenarios) or not self.origin_px or not self.m_per_pixel:
            return
        primitives=[]
        for placement in self.scenarios[index].placements:
            if placement.sozr_plan is not None:
                primitives.extend(build_sozr_canvas_primitives(placement.sozr_plan,self._world_to_canvas))
        draw_sozr_canvas(self.canvas,primitives)

    def _draw_restricted_zone(self, zone: RestrictedZone, index: int) -> None:
        if not zone.polygon or not self.origin_px or not self.m_per_pixel:
            return
        pixels=[self._world_to_canvas(point) for point in zone.polygon]
        coords=[value for point in pixels for value in point]
        selected=zone.id==self.selected_restricted_zone_id
        color="#ff9d2e" if zone.kind is RestrictedZoneKind.HEIGHT_OBSTACLE else DRAW_COLORS["restricted"]
        stipple={
            RestrictedZoneKind.FULL_EXCLUSION:"",
            RestrictedZoneKind.LOAD_PROHIBITED:"gray25",
            RestrictedZoneKind.HEIGHT_OBSTACLE:"gray50",
        }[zone.kind]
        fill=color
        tag=f"draw_restricted_{index}"
        self.canvas.create_polygon(
            *coords,outline=color,fill=fill,stipple=stipple,width=4 if selected else 2,
            tags=("markup",tag,f"restricted_zone_{zone.id}"),
        )
        cx=sum(point[0] for point in pixels)/len(pixels); cy=sum(point[1] for point in pixels)/len(pixels)
        label=zone.name
        label+=f"\nH={zone.height_m:g} м"
        self.canvas.create_text(cx,cy,text=label,fill=color,justify="center",tags=("markup",tag))

    def _refresh_zone_table(self) -> None:
        if not hasattr(self,"zone_tree"):
            return
        self.zone_tree.delete(*self.zone_tree.get_children())
        for zone in self.restricted_zones:
            self.zone_tree.insert("","end",iid=zone.id,text=zone.name,values=(ZONE_KIND_LABELS[zone.kind],f"{zone.height_m:g}"))
        if self.selected_restricted_zone_id in {zone.id for zone in self.restricted_zones}:
            self.zone_tree.selection_set(self.selected_restricted_zone_id)

    def _on_zone_table_select(self, _event=None) -> None:
        selection=self.zone_tree.selection()
        if selection:
            self.select_restricted_zone(selection[0])

    def select_restricted_zone(self, zone_id: str) -> None:
        self.selected_restricted_zone_id=zone_id
        self.canvas.delete("markup")
        self._redraw_loaded_markup()

    def edit_selected_restricted_zone(self) -> None:
        zone=next((item for item in self.restricted_zones if item.id==self.selected_restricted_zone_id),None)
        if zone is None:
            messagebox.showinfo("Опасные зоны","Выберите зону в таблице.")
            return
        result=edit_restricted_zone(self,zone.polygon,zone)
        if result.cancelled or result.zone is None:
            return
        self.restricted_zones=[result.zone if item.id==zone.id else item for item in self.restricted_zones]
        self._refresh_zone_table(); self.canvas.delete("markup"); self._redraw_loaded_markup()
        self._mark_calculation_changed()

    def delete_selected_restricted_zone(self) -> None:
        zone=next((item for item in self.restricted_zones if item.id==self.selected_restricted_zone_id),None)
        if zone is None:
            messagebox.showinfo("Опасные зоны","Выберите зону в таблице.")
            return
        if not messagebox.askyesno("Удаление зоны",f"Удалить зону «{zone.name}»?"):
            return
        self.restricted_zones=[item for item in self.restricted_zones if item.id!=zone.id]
        self.selected_restricted_zone_id=None
        self._refresh_zone_table(); self.canvas.delete("markup"); self._redraw_loaded_markup()
        self._mark_calculation_changed()

    def _redraw_section_calibration(self):
        if not self.section_origin_px or not self.section_m_per_pixel: return
        if len(self.section_calibration_points) >= 2:
            p1,p2=self.section_calibration_points[:2]
        else:
            p1=self.section_origin_px; distance=float(self.parapet.get())-float(self.pit_bottom.get())
            p2=(p1[0]+self.section_axis[0]*distance/self.section_m_per_pixel,p1[1]+self.section_axis[1]*distance/self.section_m_per_pixel)
        for p in (p1,p2):
            x,y=p[0]*self.section_image_scale,p[1]*self.section_image_scale; self.section_canvas.create_oval(x-4,y-4,x+4,y+4,fill=DRAW_COLORS["section"],tags="section_markup")
        self.section_canvas.create_line(p1[0]*self.section_image_scale,p1[1]*self.section_image_scale,p2[0]*self.section_image_scale,p2[1]*self.section_image_scale,fill=DRAW_COLORS["section"],width=2,tags="section_markup")
        self._redraw_section_building_contour()

    def _section_pixel_to_world(self,point):
        dx=point[0]-self.section_origin_px[0]; dy=point[1]-self.section_origin_px[1]; ux,uy=self.section_axis
        return ((dx*uy-dy*ux)*self.section_m_per_pixel,(dx*ux+dy*uy)*self.section_m_per_pixel)

    def _section_world_to_pixel(self,point):
        horizontal,height=point; ux,uy=self.section_axis
        return (self.section_origin_px[0]+(height*ux+horizontal*uy)/self.section_m_per_pixel,self.section_origin_px[1]+(height*uy-horizontal*ux)/self.section_m_per_pixel)

    def _normalize_section_building_reference(self):
        """Use the contour bottom as height zero without moving its PDF overlay."""
        if not self.section_building_points or not self.section_origin_px or not self.section_m_per_pixel:
            return
        bottom=min(height for _,height in self.section_building_points)
        if abs(bottom)<=1e-9:
            return
        ux,uy=self.section_axis; shift=bottom/self.section_m_per_pixel
        self.section_origin_px=(self.section_origin_px[0]+ux*shift,self.section_origin_px[1]+uy*shift)
        self.section_building_points=[(horizontal,height-bottom) for horizontal,height in self.section_building_points]

    def _redraw_section_building_contour(self):
        self.section_canvas.delete("section_building")
        if not self.section_origin_px or not self.section_m_per_pixel or not self.section_building_points: return
        pixels=[self._section_world_to_pixel(point) for point in self.section_building_points]; self.section_contour_pixels=[(x*self.section_image_scale,y*self.section_image_scale) for x,y in pixels]
        for index,(x,y) in enumerate(self.section_contour_pixels):
            if index: self.section_canvas.create_line(*self.section_contour_pixels[index-1],x,y,fill="#00bcd4",width=3,tags="section_building")
            self.section_canvas.create_oval(x-3,y-3,x+3,y+3,fill="#00bcd4",outline="#00bcd4",tags="section_building")
        if self.section_contour_closed and len(self.section_contour_pixels)>=3:
            self.section_canvas.create_line(*self.section_contour_pixels[-1],*self.section_contour_pixels[0],fill="#00bcd4",width=3,tags="section_building")

    def choose_plan(self):
        path = filedialog.askopenfilename(title="Выберите PDF-план", filetypes=[("PDF", "*.pdf")])
        if not path: return
        try:
            inspection = inspect_pdf(path)
            if not inspection.likely_vector:
                messagebox.showwarning(
                    "Растровая PDF-подложка",
                    "В документе недостаточно распознаваемых векторных элементов. "
                    "PDF будет загружен как подложка: выполните обрезку и масштабирование вручную.",
                )
            self.plan_pdf = path
            self._mark_calculation_changed()
            self.plan_crop_box=(0.0,0.0,1.0,1.0); self._clear_plan_geometry()
            self.plan_label.config(text=f"{Path(path).name}; страниц: {inspection.pages}; векторных элементов: {inspection.vector_lines + inspection.vector_rects}")
            self._show_plan()
            self.status.set("План загружен. Выберите две точки с известным расстоянием.")
            self._update_properties()
        except Exception as exc:
            messagebox.showerror("Ошибка PDF", str(exc))

    def choose_section(self):
        path = filedialog.askopenfilename(title="Выберите PDF-разрез", filetypes=[("PDF", "*.pdf")])
        if path:
            self.section_pdf = path
            self._mark_calculation_changed()
            self.section_crop_box=(0.0,0.0,1.0,1.0); self._clear_section_calibration()
            self.section_label.config(text=Path(path).name)
            self._show_section()
            self.status.set("Разрез загружен. На вкладке «3. Разрез» задайте нижнюю и верхнюю отметки.")
            self._update_properties()

    def _background_value(self, variable):
        value=float(variable.get())/100.0
        if not 0.05 <= value <= 1.0: raise ValueError("Интенсивность фона должна быть от 5 до 100 %")
        return value

    def _show_plan(self, full_page=False):
        if not self.plan_pdf: return
        crop=None if full_page else self.plan_crop_box
        image = render_page(self.plan_pdf, 0, 1.5, crop, self._background_value(self.plan_background_intensity))
        self.canvas.update_idletasks()
        max_w=max(320,self.canvas.winfo_width()-4); max_h=max(240,self.canvas.winfo_height()-4)
        self.plan_fit_scale=min(max_w/image.width,max_h/image.height,1.0)
        factor=max(0.05,min(8.0,self.plan_fit_scale*self.plan_zoom))
        self.image_scale = factor
        if factor != 1:
            image = image.resize(display_size(image.size, factor))
        self.plan_image = image
        self.plan_photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.plan_photo, anchor="nw", tags="pdf")
        self.canvas.configure(scrollregion=(0,0,image.width,image.height))

    def _show_section(self, full_page=False):
        if not self.section_pdf: return
        crop=None if full_page else self.section_crop_box
        image = render_page(self.section_pdf, 0, 1.5, crop, self._background_value(self.section_background_intensity))
        self.section_canvas.update_idletasks()
        max_w=max(320,self.section_canvas.winfo_width()-4); max_h=max(240,self.section_canvas.winfo_height()-4)
        self.section_fit_scale=min(max_w/image.width,max_h/image.height,1.0)
        factor=max(0.05,min(8.0,self.section_fit_scale*self.section_zoom))
        self.section_image_scale = factor
        if factor != 1:
            image = image.resize(display_size(image.size, factor))
        self.section_image = image; self.section_photo = ImageTk.PhotoImage(image)
        self.section_canvas.delete("all")
        self.section_canvas.create_image(0, 0, image=self.section_photo, anchor="nw", tags="pdf")
        self.section_canvas.configure(scrollregion=(0,0,image.width,image.height))

    def _set_plan_zoom(self,value,anchor=None):
        if not self.plan_pdf: return
        old_scale=self.image_scale; canvas=self.canvas
        x,y=anchor or (canvas.winfo_width()/2,canvas.winfo_height()/2)
        doc=(canvas.canvasx(x)/old_scale,canvas.canvasy(y)/old_scale) if old_scale else (0,0)
        self.plan_zoom=max(.1,min(8.0,float(value))); self._show_plan(full_page=self.plan_crop_active); self._redraw_loaded_markup()
        canvas.update_idletasks(); width=max(1,self.plan_image.width); height=max(1,self.plan_image.height)
        canvas.xview_moveto(max(0,min(1,(doc[0]*self.image_scale-x)/width))); canvas.yview_moveto(max(0,min(1,(doc[1]*self.image_scale-y)/height)))
        self.status.set(f"Масштаб плана: {self.plan_zoom*100:.0f}%")

    def _zoom_plan(self,factor,anchor=None): self._set_plan_zoom(self.plan_zoom*factor,anchor)
    def _fit_plan(self): self.plan_zoom=1.0; self._show_plan(full_page=self.plan_crop_active); self._redraw_loaded_markup(); self.canvas.xview_moveto(0); self.canvas.yview_moveto(0)
    def _on_plan_wheel(self,event):
        if self.plan_crop_active: return "break"
        self._zoom_plan(1.2 if event.delta>0 else 1/1.2,(event.x,event.y)); return "break"

    def _set_section_zoom(self,value,anchor=None):
        if not self.section_pdf: return
        old_scale=self.section_image_scale; canvas=self.section_canvas
        x,y=anchor or (canvas.winfo_width()/2,canvas.winfo_height()/2)
        doc=(canvas.canvasx(x)/old_scale,canvas.canvasy(y)/old_scale) if old_scale else (0,0)
        self.section_zoom=max(.1,min(8.0,float(value))); self._show_section(full_page=self.section_crop_active); self._redraw_section_calibration()
        canvas.update_idletasks(); width=max(1,self.section_image.width); height=max(1,self.section_image.height)
        canvas.xview_moveto(max(0,min(1,(doc[0]*self.section_image_scale-x)/width))); canvas.yview_moveto(max(0,min(1,(doc[1]*self.section_image_scale-y)/height)))
        self.status.set(f"Масштаб разреза: {self.section_zoom*100:.0f}%")

    def _zoom_section(self,factor,anchor=None): self._set_section_zoom(self.section_zoom*factor,anchor)
    def _fit_section(self): self.section_zoom=1.0; self._show_section(full_page=self.section_crop_active); self._redraw_section_calibration(); self.section_canvas.xview_moveto(0); self.section_canvas.yview_moveto(0)
    def _on_section_wheel(self,event):
        if self.section_crop_active: return "break"
        self._zoom_section(1.2 if event.delta>0 else 1/1.2,(event.x,event.y)); return "break"

    def _clear_plan_geometry(self):
        self.calibration_points.clear(); self.m_per_pixel=None; self.origin_px=None
        self.site_points.clear(); self.building_points.clear(); self.current_zone_points.clear(); self.restricted_zones.clear(); self.work_points.clear()
        self.unloading_points.clear(); self.current_storage_points.clear(); self.storage_zones.clear()
        self.contour_pixels={"site":[],"building":[],"restricted":[],"unloading":[],"storage":[]}; self.closed_contours.clear(); self.scenarios=[]

    def _clear_section_calibration(self):
        self.section_calibration_points.clear(); self.section_m_per_pixel=None; self.section_origin_px=None; self.section_axis=(0.0,-1.0)
        self.section_building_points.clear(); self.section_contour_pixels.clear(); self.section_contour_closed=False; self.section_mode="calibration"; self.scenarios=[]

    def _confirm_crop_reset(self, section=False):
        has_data=(self.section_m_per_pixel is not None) if section else (self.m_per_pixel is not None or bool(self.site_points or self.building_points or self.work_points))
        return not has_data or messagebox.askyesno("Изменить окно подложки", "Изменение окна пересчитает систему координат. Текущая калибровка%s будет сохранена и привязана к новому окну. Продолжить?" % (" разреза" if section else " и разметка плана"))

    def start_plan_crop(self):
        if not self.plan_pdf:
            messagebox.showwarning("Нет плана","Сначала загрузите PDF-план."); return
        if not self._confirm_crop_reset(): return
        self.plan_crop_active=True; self.crop_drag_start=None; self._show_plan(full_page=True)
        self.status.set("Обрезка плана: протяните рамку вокруг нужного фрагмента страницы.")

    def start_section_crop(self):
        if not self.section_pdf:
            messagebox.showwarning("Нет разреза","Сначала загрузите PDF-разрез."); return
        if not self._confirm_crop_reset(section=True): return
        self.section_crop_active=True; self.crop_drag_start=None; self._show_section(full_page=True)
        self.status.set("Обрезка разреза: протяните рамку вокруг нужного фрагмента страницы.")

    def _crop_press(self, canvas, event):
        self.crop_drag_start=(canvas.canvasx(event.x),canvas.canvasy(event.y))
        if self.crop_rect_id: canvas.delete(self.crop_rect_id)
        self.crop_rect_id=canvas.create_rectangle(*self.crop_drag_start,*self.crop_drag_start,outline=UI["cyan"],width=2,dash=(6,3),tags="crop_preview")

    def _crop_drag(self, canvas, event):
        if self.crop_drag_start and self.crop_rect_id:
            canvas.coords(self.crop_rect_id,*self.crop_drag_start,canvas.canvasx(event.x),canvas.canvasy(event.y))

    def _finish_crop(self, event, section=False):
        canvas=self.section_canvas if section else self.canvas; scale=self.section_image_scale if section else self.image_scale
        if not self.crop_drag_start: return
        x0,y0=self.crop_drag_start; x1,y1=canvas.canvasx(event.x),canvas.canvasy(event.y); self.crop_drag_start=None
        image=self.section_image if section else self.plan_image
        full_w=image.width/scale; full_h=image.height/scale
        try:
            box=normalize_crop_box((x0/scale/full_w,y0/scale/full_h,x1/scale/full_w,y1/scale/full_h))
        except Exception as exc:
            messagebox.showwarning("Окно не принято",str(exc)); canvas.delete("crop_preview"); return
        if section:
            self._rebase_crop(section=True,new_box=box); self.section_crop_active=False; self._show_section(); self._redraw_section_calibration()
            self.status.set("Окно разреза принято; калибровка и контур сохранены.")
        else:
            self._rebase_crop(section=False,new_box=box); self.plan_crop_active=False; self._show_plan(); self._redraw_loaded_markup()
            self.status.set("Окно плана принято; масштаб, точки и границы сохранены.")
        self.crop_rect_id=None

    def _rebase_crop(self,section,new_box):
        path=self.section_pdf if section else self.plan_pdf
        old_box=self.section_crop_box if section else self.plan_crop_box
        full=render_page(path,0,1.5)
        old_left,old_top,_,_=crop_pixel_box(full.size,old_box); new_left,new_top,_,_=crop_pixel_box(full.size,new_box)
        dx=old_left-new_left; dy=old_top-new_top
        if section:
            if self.section_origin_px: self.section_origin_px=(self.section_origin_px[0]+dx,self.section_origin_px[1]+dy)
            self.section_calibration_points=[(x+dx,y+dy) for x,y in self.section_calibration_points]
            self.section_crop_box=new_box
        else:
            if self.origin_px: self.origin_px=(self.origin_px[0]+dx,self.origin_px[1]+dy)
            self.calibration_points=[(x+dx,y+dy) for x,y in self.calibration_points]
            self.plan_crop_box=new_box

    def _on_plan_press(self,event):
        if self.plan_crop_active: self._crop_press(self.canvas,event)
        else:
            self.on_canvas_click(event)
            self._mark_calculation_changed()

    def _on_plan_drag(self,event):
        if self.plan_crop_active: self._crop_drag(self.canvas,event)

    def _on_plan_release(self,event):
        if self.plan_crop_active:
            self._finish_crop(event)
            self._mark_calculation_changed()

    def _on_section_press(self,event):
        if self.section_crop_active: self._crop_press(self.section_canvas,event)
        else:
            self.on_section_click(event)
            self._mark_calculation_changed()

    def _on_section_drag(self,event):
        if self.section_crop_active: self._crop_drag(self.section_canvas,event)

    def _on_section_release(self,event):
        if self.section_crop_active:
            self._finish_crop(event,section=True)
            self._mark_calculation_changed()

    def reset_plan_crop(self):
        if not self.plan_pdf or not self._confirm_crop_reset(): return
        self._rebase_crop(False,(0.0,0.0,1.0,1.0)); self._show_plan(); self._redraw_loaded_markup(); self.status.set("План возвращён к полной странице без потери разметки.")
        self._mark_calculation_changed()

    def reset_section_crop(self):
        if not self.section_pdf or not self._confirm_crop_reset(section=True): return
        self._rebase_crop(True,(0.0,0.0,1.0,1.0)); self._show_section(); self._redraw_section_calibration(); self.status.set("Разрез возвращён к полной странице без потери калибровки.")
        self._mark_calculation_changed()

    def apply_plan_background(self):
        try: self._show_plan(); self._redraw_loaded_markup(); self.status.set("Интенсивность подложки плана обновлена.")
        except Exception as exc: messagebox.showerror("Фон не изменён",str(exc))

    def apply_section_background(self):
        try: self._show_section(); self._redraw_section_calibration(); self.status.set("Интенсивность подложки разреза обновлена.")
        except Exception as exc: messagebox.showerror("Фон не изменён",str(exc))

    def start_section_calibration(self):
        if not self.section_pdf:
            messagebox.showwarning("Нет разреза", "Сначала выберите PDF-разрез на вкладке проекта.")
            return
        self.section_mode="calibration"; self.section_calibration_points.clear(); self.section_canvas.delete("section_markup")
        self.status.set("На разрезе укажите нижнюю, затем верхнюю точку с известной разностью отметок.")

    def on_section_click(self, event):
        if not self.section_pdf: return
        vx,vy=self.section_canvas.canvasx(event.x),self.section_canvas.canvasy(event.y)
        point=(vx/self.section_image_scale,vy/self.section_image_scale)
        if self.section_mode=="building":
            if not self.section_origin_px or not self.section_m_per_pixel:
                messagebox.showwarning("Сначала масштаб","Сначала задайте низ и верх на разрезе."); return
            if self.section_contour_closed:
                messagebox.showinfo("Контур замкнут","Очистите контур, чтобы нанести его заново."); return
            world=self._section_pixel_to_world(point); self.section_building_points.append(world); self.section_contour_pixels.append((vx,vy))
            if len(self.section_contour_pixels)>1: self.section_canvas.create_line(*self.section_contour_pixels[-2],vx,vy,fill="#00bcd4",width=3,tags="section_building")
            self.section_canvas.create_oval(vx-3,vy-3,vx+3,vy+3,fill="#00bcd4",outline="#00bcd4",tags="section_building")
            self.status.set(f"Контур здания на разрезе: {len(self.section_building_points)} точек. После последней нажмите «Замкнуть»."); return
        if len(self.section_calibration_points)>=2: self.start_section_calibration()
        self.section_calibration_points.append(point)
        self.section_canvas.create_oval(vx-4,vy-4,vx+4,vy+4,fill=DRAW_COLORS["section"],tags="section_markup")
        if len(self.section_calibration_points)==2:
            try:
                p1,p2=self.section_calibration_points; distance=float(self.section_distance_var.get())
                contour_pixels=(
                    [self._section_world_to_pixel(point) for point in self.section_building_points]
                    if self.section_building_points and self.section_origin_px and self.section_m_per_pixel
                    else []
                )
                self.section_m_per_pixel=calibration_m_per_pixel(p1,p2,distance); self.section_origin_px=p1
                length=math.hypot(p2[0]-p1[0],p2[1]-p1[1]); self.section_axis=((p2[0]-p1[0])/length,(p2[1]-p1[1])/length)
                if contour_pixels:
                    self.section_building_points=[self._section_pixel_to_world(point) for point in contour_pixels]
                    self._normalize_section_building_reference()
                    self._redraw_section_building_contour()
                height_sync_note=""
                try:
                    if "pit_bottom" in self.__dict__ and "parapet" in self.__dict__:
                        pit=float(self.pit_bottom.get().replace(",",".")); parapet=float(self.parapet.get().replace(",","."))
                        if abs((parapet-pit)-distance)>.5:
                            self.parapet.set(f"{pit+distance:g}")
                            height_sync_note=" Отметка верха парапета синхронизирована с выбранной высотой."
                except ValueError:
                    pass
                self.section_canvas.create_line(p1[0]*self.section_image_scale,p1[1]*self.section_image_scale,p2[0]*self.section_image_scale,p2[1]*self.section_image_scale,fill=DRAW_COLORS["section"],width=2,tags="section_markup")
                self.status.set(f"Масштаб разреза принят: {self.section_m_per_pixel:.5f} м/пиксель. Высотная схема попадёт в ППРк.{height_sync_note}")
            except Exception as exc:
                messagebox.showerror("Ошибка масштаба разреза",str(exc)); self.section_calibration_points.clear()

    def start_section_building_contour(self):
        if not self.section_m_per_pixel:
            messagebox.showwarning("Сначала масштаб","Сначала откалибруйте разрез по двум точкам."); return
        self.section_mode="building"; self.status.set("Режим: контур здания на разрезе. Нанесите вершины по порядку.")

    def finish_section_building_contour(self):
        if self.section_mode!="building" or len(self.section_building_points)<3:
            messagebox.showwarning("Недостаточно точек","Для контура здания требуется минимум три точки."); return
        self._normalize_section_building_reference()
        self.section_contour_closed=True; self._redraw_section_building_contour(); self.scenarios=[]; self.status.set("Контур здания на разрезе замкнут.")
        self._mark_calculation_changed()

    def undo_section_contour_point(self):
        if self.section_contour_closed or not self.section_building_points: return
        self.section_building_points.pop(); self._redraw_section_building_contour(); self.scenarios=[]
        self._mark_calculation_changed()

    def clear_section_building_contour(self):
        self.section_building_points.clear(); self.section_contour_pixels.clear(); self.section_contour_closed=False; self.section_canvas.delete("section_building"); self.scenarios=[]; self.status.set("Контур здания на разрезе очищен.")
        self._mark_calculation_changed()

    def set_mode(self, mode):
        if mode != "calibration" and self.m_per_pixel is None:
            messagebox.showwarning("Сначала масштаб", "Сначала выберите две точки масштаба.")
            return
        self.mode = mode
        names = {"calibration":"масштаб", "site":"граница площадки", "building":"контур здания", "restricted":"запретная зона", "workpoint":"точки подачи грузов на здание", "unloading":"зона разгрузки", "storage":"зона складирования"}
        instruction = " Щёлкайте вершины по порядку: линии строятся автоматически, затем нажмите «Замкнуть контур»." if mode in self.contour_pixels else " Щёлкните требуемые точки."
        self.status.set(f"Режим: {names[mode]}.{instruction}")
        self._update_properties()

    def on_canvas_click(self, event):
        if not self.plan_pdf: return
        vx,vy=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        point_px = (vx / self.image_scale, vy / self.image_scale)
        if self.mode == "calibration":
            self.calibration_points.append(point_px)
            self.canvas.create_oval(vx-4,vy-4,vx+4,vy+4,fill="#ff8800",tags="markup")
            if len(self.calibration_points) == 2:
                try:
                    self.m_per_pixel = calibration_m_per_pixel(*self.calibration_points, float(self.distance_var.get()))
                    self.origin_px = self.calibration_points[0]
                    self.status.set(f"Масштаб принят: {self.m_per_pixel:.5f} м/пиксель. Нанесите границу площадки.")
                except Exception as exc:
                    messagebox.showerror("Ошибка масштаба", str(exc)); self.calibration_points.clear()
            elif len(self.calibration_points) > 2:
                self.calibration_points = [point_px]
            return
        world = pixel_to_world(point_px, self.origin_px, self.m_per_pixel)
        if self.mode in self.contour_pixels and self.mode in self.closed_contours:
            messagebox.showinfo("Контур уже замкнут", "Очистите разметку, если требуется нарисовать этот контур заново.")
            return
        if self.mode == "site": self.site_points.append(world); color=DRAW_COLORS["site"]
        elif self.mode == "building": self.building_points.append(world); color=DRAW_COLORS["building"]
        elif self.mode == "restricted": self.current_zone_points.append(world); color=DRAW_COLORS["restricted"]
        elif self.mode == "unloading": self.unloading_points.append(world); color=DRAW_COLORS["unloading"]
        elif self.mode == "storage": self.current_storage_points.append(world); color=DRAW_COLORS["storage"]
        else:
            self._add_work_point_dialog(world, (vx, vy))
            return
        pixels = self.contour_pixels[self.mode]
        draw_tag = self._current_contour_tag()
        if pixels:
            x0, y0 = pixels[-1]
            self.canvas.create_line(x0, y0, vx, vy, fill=color, width=2, tags=("markup", draw_tag))
        pixels.append((vx, vy))
        self.canvas.create_oval(vx-3,vy-3,vx+3,vy+3,fill=color,outline=color,tags=("markup", draw_tag))

    def _current_contour_tag(self):
        if self.mode == "restricted":
            return f"draw_restricted_{len(self.restricted_zones)}"
        if self.mode == "storage":
            return f"draw_storage_{len(self.storage_zones)}"
        return f"draw_{self.mode}"

    def finish_contour(self):
        if self.mode not in self.contour_pixels:
            messagebox.showinfo("Выберите контур", "Сначала выберите границу площадки, контур здания или запретную зону.")
            return
        pixels = self.contour_pixels[self.mode]
        if len(pixels) < 3:
            messagebox.showwarning("Недостаточно точек", "Для замкнутого контура требуется минимум три вершины.")
            return
        self.canvas.create_line(*pixels[-1], *pixels[0], fill=DRAW_COLORS[self.mode], width=2, tags=("markup", self._current_contour_tag()))
        if self.mode == "restricted":
            polygon=self.current_zone_points[:]
            result=edit_restricted_zone(self,polygon)
            self.canvas.delete(self._current_contour_tag())
            self.current_zone_points.clear()
            self.contour_pixels["restricted"] = []
            if result.cancelled or result.zone is None:
                self.status.set("Добавление опасной зоны отменено.")
                return
            self.restricted_zones.append(result.zone)
            self.selected_restricted_zone_id=result.zone.id
            self._refresh_zone_table()
            self._draw_restricted_zone(result.zone,len(self.restricted_zones)-1)
            self.status.set(f"Опасная зона «{result.zone.name}» добавлена. Всего зон: {len(self.restricted_zones)}.")
            self._mark_calculation_changed()
        elif self.mode == "storage":
            self.storage_zones.append(self.current_storage_points[:]); self.current_storage_points.clear(); self.contour_pixels["storage"]=[]
            self._mark_calculation_changed()
            self.status.set(f"Зона складирования замкнута. Всего зон: {len(self.storage_zones)}. Можно рисовать следующую.")
        else:
            self.closed_contours.add(self.mode)
            label = {"site":"Граница площадки","building":"Контур здания","unloading":"Зона разгрузки"}[self.mode]
            self.status.set(f"{label} замкнут. Выберите следующий вид разметки.")

    def undo_contour_point(self):
        if self.mode not in self.contour_pixels or self.mode in self.closed_contours:
            messagebox.showinfo("Отмена недоступна", "Отменять можно вершины текущего незамкнутого контура.")
            return
        pixels = self.contour_pixels[self.mode]
        if not pixels:
            return
        pixels.pop()
        points = {"site":self.site_points,"building":self.building_points,"restricted":self.current_zone_points,"unloading":self.unloading_points,"storage":self.current_storage_points}[self.mode]
        if points:
            points.pop()
        draw_tag = self._current_contour_tag()
        self.canvas.delete(draw_tag)
        color = DRAW_COLORS[self.mode]
        for index, (x, y) in enumerate(pixels):
            if index:
                self.canvas.create_line(*pixels[index-1], x, y, fill=color, width=2, tags=("markup", draw_tag))
            self.canvas.create_oval(x-3,y-3,x+3,y+3,fill=color,outline=color,tags=("markup", draw_tag))
        self.status.set(f"Последняя вершина отменена. Осталось: {len(pixels)}.")
        self._mark_calculation_changed()

    def clear_markup(self):
        self._clear_plan_geometry()
        self._show_plan(); self.status.set("Разметка очищена. Выберите две точки масштаба.")
        self._mark_calculation_changed()

    def auto_suggest_boundary(self):
        if not self.plan_pdf or self.m_per_pixel is None:
            messagebox.showwarning("Недостаточно данных", "Загрузите план и задайте масштаб по двум точкам.")
            return
        try:
            x0, y0, x1, y1 = suggest_vector_bounds(self.plan_pdf)
            # PDFium рендерится с scale=1.5; переводим PDF-точки в пиксели исходного рендера.
            full_image=render_page(self.plan_pdf,0,1.5); crop_left,crop_top,_,_=crop_pixel_box(full_image.size,self.plan_crop_box)
            points_px = [(x0*1.5-crop_left,y0*1.5-crop_top),(x1*1.5-crop_left,y0*1.5-crop_top),(x1*1.5-crop_left,y1*1.5-crop_top),(x0*1.5-crop_left,y1*1.5-crop_top)]
            if any(px<0 or py<0 or px>self.plan_image.width/self.image_scale or py>self.plan_image.height/self.image_scale for px,py in points_px):
                raise ValueError("Автоматически найденная рамка выходит за выбранное окно подложки; нанесите границу площадки вручную")
            proposed = [pixel_to_world(point,self.origin_px,self.m_per_pixel) for point in points_px]
            if messagebox.askyesno("Автоматическое предложение", "Предложена рамка по векторным элементам. Использовать её как черновую границу площадки? После этого обязательно проверьте все точки."):
                self.site_points = proposed
                self._mark_calculation_changed()
                self.contour_pixels["site"] = [(px*self.image_scale,py*self.image_scale) for px,py in points_px]
                self.closed_contours.add("site")
                coords=[]
                for px,py in points_px: coords += [px*self.image_scale,py*self.image_scale]
                self.canvas.create_polygon(*coords,outline=DRAW_COLORS["site"],fill="",width=2,tags="markup")
                self.status.set("Автоматическая граница добавлена как черновик. Проверьте её; при ошибке очистите и нанесите вручную.")
        except Exception as exc:
            messagebox.showerror("Автоматическое предложение не выполнено",str(exc))

    def edit_load(self, new=False):
        selected = self.load_tree.selection()
        values = ("Новый груз",1000,100,1,1,1,10,"да") if new or not selected else self.load_tree.item(selected[0], "values")
        dialog = tk.Toplevel(self); dialog.title("Параметры груза"); dialog.configure(bg=UI["panel"]); dialog.transient(self); dialog.grab_set()
        vars_=[]
        for row,(label,value) in enumerate(zip(("Название","Масса, кг","Оснастка, кг","Длина, м","Ширина, м","Высота, м","Подъёмов"),values[:7])):
            ttk.Label(dialog,text=label).grid(row=row,column=0,padx=5,pady=3,sticky="w"); var=tk.StringVar(value=value); vars_.append(var); ttk.Entry(dialog,textvariable=var).grid(row=row,column=1,padx=5,pady=3)
        active_var=tk.BooleanVar(value=str(values[7]).lower() in ("да","true","1"))
        ttk.Checkbutton(dialog,text="Используется в этом проекте",variable=active_var).grid(row=7,column=0,columnspan=2,pady=4)
        extra = tuple(values[8:14]) if len(values) >= 14 else ("", "", "", "", "", "нет")
        rig_vars = []
        for index, (label, value) in enumerate(zip(("Тип оснастки", "Число ветвей", "Марка / номер стропа",
                "Допустимая масса по паспорту, кг", "Документ, подтверждающий оснастку"), extra[:5]), 8):
            var = tk.StringVar(value=value)
            rig_vars.append(var)
            ttk.Label(dialog, text=label).grid(row=index, column=0, padx=5, pady=3, sticky="w")
            ttk.Entry(dialog, textvariable=var, width=40).grid(row=index, column=1, padx=5, pady=3)
        rig_verified = tk.BooleanVar(value=str(extra[5]).lower() in ("да", "true", "1"))
        ttk.Checkbutton(dialog, text="Паспорт и схема строповки проверены разработчиком", variable=rig_verified).grid(row=13,column=0,columnspan=2,pady=4)
        def apply():
            try:
                row=(vars_[0].get().strip(),)+tuple(float(v.get()) for v in vars_[1:6])+(int(float(vars_[6].get())),)+("да" if active_var.get() else "нет",)
                if not row[0] or row[1]<=0 or row[2]<0 or min(row[3:6])<=0 or row[6]<=0: raise ValueError("Проверьте название, массы, габариты и количество подъёмов")
                rig = tuple(v.get().strip() for v in rig_vars)
                if rig[1] and int(rig[1]) <= 0:
                    raise ValueError("Число ветвей должно быть положительным целым")
                if rig[3] and (not math.isfinite(float(rig[3])) or float(rig[3]) <= 0):
                    raise ValueError("Паспортная грузоподъёмность должна быть положительной")
                if rig_verified.get() and (not all(rig) or float(rig[3]) < row[1] + row[2]):
                    raise ValueError("Заполните подтверждение оснастки и проверьте допустимую массу")
                row += rig + ("да" if rig_verified.get() else "нет",)
                if new or not selected: self.load_tree.insert("","end",values=row)
                else: self.load_tree.item(selected[0],values=row)
                dialog.destroy(); self._invalidate_load_confirmation()
            except Exception as exc: messagebox.showerror("Груз не сохранён",str(exc),parent=dialog)
        ttk.Button(dialog,text="Сохранить",command=apply).grid(row=14,column=0,columnspan=2,pady=8)

    def delete_load(self):
        selected=self.load_tree.selection()
        if not selected:
            messagebox.showinfo("Выберите груз","Выберите строку груза для удаления.")
            return
        index=self.load_tree.index(selected[0])
        self.load_tree.delete(selected[0])
        for wp in self.work_points:
            if wp.load_index==index: wp.load_index=0
            elif wp.load_index>index: wp.load_index-=1
        self._invalidate_load_confirmation()
        self.status.set("Груз удалён. Точки, относившиеся к нему, переназначены на первый груз; проверьте их.")

    def _invalidate_load_confirmation(self) -> None:
        self.loads_verified.set(False)
        self._reset_calculation_results()

    def _configure_recalculation(self) -> None:
        self._calculation_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="crane-plan-calculation")
        self.recalculation=RecalculationCoordinator(
            snapshot_factory=self._automatic_calculation_snapshot,
            calculate=self._calculate_snapshot,
            schedule=lambda delay,callback:self.after(delay,callback),
            cancel_schedule=self.after_cancel,
            submit=self._calculation_executor.submit,
            on_state=self._show_calculation_state,
            on_result=self._apply_automatic_calculation,
        )
        excluded={
            id(self.status),id(self.release_variant_var),id(self.report_selection_var),
            id(self.report_path_var),id(self.calculation_state_var),id(self.release_status_var),
        }
        self._recalculation_traces=[]
        seen=set()
        for value in self.__dict__.values():
            if isinstance(value,tk.Variable) and id(value) not in excluded and id(value) not in seen:
                seen.add(id(value))
                token=value.trace_add("write",lambda *_args:self._mark_calculation_changed())
                self._recalculation_traces.append((value,token))

    def _mark_calculation_changed(self) -> None:
        self._invalidate_release()
        if "recalculation" in self.__dict__:
            self.recalculation.mark_changed()

    def _show_calculation_state(self,state: CalculationState) -> None:
        labels={
            CalculationState.MISSING_INPUT:"Не хватает исходных данных",
            CalculationState.STALE:"Данные изменены — ожидается перерасчёт",
            CalculationState.RUNNING:"Выполняется расчёт…",
            CalculationState.CURRENT:"Расчёт актуален",
            CalculationState.NO_SOLUTION:"Вариант не найден — см. причины ниже",
            CalculationState.EXPERT_REVIEW:"Требуется экспертная проверка",
        }
        self.calculation_state_var.set(labels[state])

    def _automatic_calculation_snapshot(self):
        blockers,reminders=self._input_issues()
        if blockers:
            self._show_input_check(blockers,reminders)
            raise ValueError("; ".join(blockers))
        project=self._project()
        serialized=self._project_snapshot(project)
        digest=hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return digest,(project,reminders)

    def _calculate_snapshot(self,snapshot) -> _CalculationBundle:
        project,reminders=snapshot
        catalog=load_catalog(self.catalog_path,self.user_catalog_path)
        scenarios=optimize(project,catalog,3,2.0)
        verifications=[]
        if scenarios and scenarios[0].status!="BLOCKED":
            run_id=f"GUI-{datetime.now().astimezone():%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"
            created_at=datetime.now().astimezone().isoformat(timespec="seconds")
            try:
                verifications=list(verify_scenarios_v21(project,scenarios,load_catalog_v3(self.catalog_v3_path),run_id=run_id,created_at=created_at))
            except Exception as exc:
                verifications=[ScenarioVerificationV21(index,IntegrationStatus.EXPERT_REVIEW_REQUIRED,False,(f"V3_CATALOG_UNAVAILABLE: каталог V3 не загружен: {exc}",),None,None) for index,_scenario in enumerate(scenarios)]
        return _CalculationBundle(project,reminders,list(scenarios),verifications)

    def _apply_automatic_calculation(self,result) -> None:
        if isinstance(result,Exception):
            self.results.delete("1.0","end")
            self.results.insert("end",f"Расчёт не выполнен: {result}")
            return
        current_hash=hashlib.sha256(self._project_snapshot(result.project).encode("utf-8")).hexdigest()
        self.warning_acceptances=current_warning_acceptances(self.warning_acceptances,current_hash)
        result.project.warning_acceptances=list(self.warning_acceptances)
        self.scenarios=result.scenarios; self.scenario_verifications=result.verifications
        self.calculation_input_snapshot=self._project_snapshot(result.project)
        self.report_page_order=None; self.report_excluded_pages.clear()
        self.report_selection_var.set("Состав листов: полный комплект по умолчанию")
        self.results.delete("1.0","end")
        if not self.scenarios or self.scenarios[0].status=="BLOCKED":
            self.results.insert("end","ПОДХОДЯЩИЙ ВАРИАНТ НЕ НАЙДЕН\n\nПочему расчёт не прошёл:\n")
            for text in (self.scenarios[0].reasons if self.scenarios else ["Расчёт не вернул вариантов"]): self.results.insert("end",f"  • {text}\n")
            return
        self._refresh_release_variant_choices()
        for index,scenario in enumerate(self.scenarios,1):
            self.results.insert("end",f"ВАРИАНТ {index}: {scenario.status}\n")
            for crane_index,placement in enumerate(scenario.placements,1):
                self.results.insert("end",f"  К{crane_index} {placement.model}: X={placement.x:.1f}, Y={placement.y:.1f}; стрела {placement.jib_length_m:.1f} м; крюк {placement.required_hook_height_m:.1f} м\n")
            for text in scenario.warnings+scenario.reasons: self.results.insert("end",f"  • {text}\n")
            if index-1<len(self.scenario_verifications): self.results.insert("end",self._render_scenario_verification(self.scenario_verifications[index-1]))
            self.results.insert("end","\n")
        if result.reminders:
            self.results.insert("end","ДОПОЛНИТЬ ДЛЯ ПОЛНОГО ППРк:\n")
            for text in result.reminders:self.results.insert("end",f"  • {text}\n")

    def accept_selected_warning(self) -> None:
        index=self._selected_release_index()
        if index is None or index>=len(self.scenarios):
            messagebox.showinfo("Предупреждения","Сначала выполните расчёт и выберите вариант.")
            return
        warnings=self.scenarios[index].warnings
        if not warnings:
            messagebox.showinfo("Предупреждения","У выбранного варианта нет предупреждений, которые можно принять.")
            return
        warning_index=0
        if len(warnings)>1:
            lines="\n".join(f"{number}. {text}" for number,text in enumerate(warnings,1))
            selected=simpledialog.askinteger(
                "Выбор предупреждения",f"Выберите предупреждение:\n\n{lines}",
                parent=self,minvalue=1,maxvalue=len(warnings),
            )
            if selected is None:return
            warning_index=selected-1
        warning=warnings[warning_index]
        snapshot=self.calculation_input_snapshot or ""
        input_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        warning_id=hashlib.sha256(warning.encode("utf-8")).hexdigest()[:16]
        comment=simpledialog.askstring("Принятие предупреждения",f"{warning}\n\nКомментарий (необязательно):",parent=self)
        if comment is None:return
        self.warning_acceptances=accept_warning(self.warning_acceptances,warning_id,input_hash,severity="warning",comment=comment)
        acceptance_rows=tuple((item.warning_id,item.input_sha256,item.comment) for item in current_warning_acceptances(self.warning_acceptances,input_hash))
        if index<len(self.scenario_verifications):
            verification=self.scenario_verifications[index]
            protocol=replace(verification.protocol,warning_acceptances=acceptance_rows) if verification.protocol else None
            engine_result=replace(verification.engine_result,protocol=protocol) if verification.engine_result else None
            self.scenario_verifications[index]=replace(
                verification,status=IntegrationStatus.EXPERT_REVIEW_REQUIRED,release_allowed=True,
                messages=verification.messages+(f"WARNING_ACCEPTED: {warning_id}",),
                engine_result=engine_result,protocol=protocol,
            )
            choices=tuple(
                f"Вариант {number + 1} — {item.status.value}"
                for number,item in enumerate(self.scenario_verifications)
            )
            self.release_variant_combo.configure(values=choices)
            self.selected_release_index=index
            self.release_variant_var.set(choices[index])
            self._draw_selected_sozr()
            if "calculation_state_var" in self.__dict__:
                self.calculation_state_var.set("Требуется экспертная проверка принятого предупреждения")
        self.status.set("Предупреждение принято для текущей ревизии; выпуск требует экспертной проверки.")

    def _reset_calculation_results(self) -> None:
        self._invalidate_release()
        self.scenarios = []
        self.scenario_verifications = []
        self.selected_release_index = None
        self.calculation_input_snapshot = None
        if "release_variant_var" in self.__dict__:
            self.release_variant_var.set("")
        if "release_variant_combo" in self.__dict__:
            self.release_variant_combo.configure(values=())

    def _selected_release_index(self) -> int | None:
        value = self.release_variant_var.get().strip() if "release_variant_var" in self.__dict__ else ""
        if value.startswith("Вариант "):
            token = value.split(" ", 2)[1]
            try:
                candidate = int(token) - 1
            except ValueError:
                candidate = -1
            if 0 <= candidate < len(self.scenario_verifications):
                self.selected_release_index = candidate
        if self.selected_release_index is None or not 0 <= self.selected_release_index < len(self.scenario_verifications):
            return None
        return self.selected_release_index

    @staticmethod
    def _project_snapshot(project: ProjectInput) -> str:
        data=project.to_dict()
        # Expert acknowledgements are bound to the engineering input hash but
        # are not themselves engineering inputs; excluding them avoids a
        # circular hash change immediately after accepting a warning.
        data["warning_acceptances"]=[]
        data.pop("pprk_release", None)
        for key in ("source_plan_pdf", "source_section_pdf"):
            if data.get(key):
                data[key + "_sha256"] = source_digest(data[key])
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _calculation_is_current(self, project: ProjectInput) -> bool:
        return self.calculation_input_snapshot == self._project_snapshot(project)

    def _refresh_release_variant_choices(self) -> None:
        choices = tuple(
            f"Вариант {index + 1} — {verification.status.value}"
            for index, verification in enumerate(self.scenario_verifications)
        )
        self.release_variant_combo.configure(values=choices)
        self.selected_release_index = default_release_index(self.scenario_verifications)
        self.release_variant_var.set(
            choices[self.selected_release_index] if self.selected_release_index is not None else ""
        )
        self._draw_selected_sozr()

    def _render_scenario_verification(self, verification: ScenarioVerificationV21) -> str:
        labels = {
            IntegrationStatus.VERIFIED: "ПРОВЕРЕН",
            IntegrationStatus.VERIFIED_WITH_CONDITIONS: "ПРОВЕРЕН С УСЛОВИЯМИ",
            IntegrationStatus.EXPERT_REVIEW_REQUIRED: "ТРЕБУЕТСЯ ЭКСПЕРТНАЯ ПРОВЕРКА",
            IntegrationStatus.REJECTED: "ОТКЛОНЁН",
        }
        lines = [f"  НЕЗАВИСИМАЯ ПРОВЕРКА ЯДРОМ 2.1: {labels[verification.status]}"]
        engine_result = verification.engine_result
        checked = engine_result.accepted_solution if engine_result and engine_result.accepted_solution else (
            engine_result.protocol.solution if engine_result and engine_result.protocol else None
        )
        if checked and checked.stages and checked.stages[0].placements:
            lines.append(f"    Конфигурация: {checked.stages[0].placements[0].configuration_id}")
        checks = engine_result.verification.checks if engine_result and engine_result.verification else ()
        capacity_checks = [check for check in checks if check.code == "CAPACITY_INSUFFICIENT"]
        if capacity_checks:
            critical = min(capacity_checks, key=lambda check: float(check.limit) - float(check.measured_value))
            margin = float(critical.limit) - float(critical.measured_value)
            lines.append(
                f"    Критическая операция: {critical.operation_id or '—'}; "
                f"масса {float(critical.measured_value):g} кг; доступно {float(critical.limit):g} кг; запас {margin:g} кг"
            )
        reach_checks = [check for check in checks if check.code == "REACH"]
        if reach_checks:
            maximum = max(float(check.measured_value) for check in reach_checks)
            lines.append(f"    Максимальный вылет: {maximum:g} м")
        height_checks = [check for check in checks if check.code == "HEIGHT"]
        if height_checks:
            critical_height = min(height_checks, key=lambda check: float(check.limit) - float(check.measured_value))
            margin = float(critical_height.limit) - float(critical_height.measured_value)
            lines.append(
                f"    Высота крюка: требуется {float(critical_height.measured_value):g} м; "
                f"доступно {float(critical_height.limit):g} м; запас {margin:g} м"
            )
        for message in verification.messages:
            lines.append(f"    • {message}")
        if verification.protocol:
            lines.extend(
                (
                    f"    Протокол: {verification.protocol.run_id}",
                    f"    SHA-256 входа: {verification.protocol.input_sha256}",
                    f"    SHA-256 результата: {verification.protocol.result_sha256}",
                )
            )
        return "\n".join(lines) + "\n"

    def _add_work_point_dialog(self, world, canvas_point):
        loads=self._collect_loads()
        if not loads:
            messagebox.showwarning("Нет грузов","Сначала добавьте хотя бы один груз.")
            return
        dialog=tk.Toplevel(self); dialog.title("Точка подачи груза"); dialog.configure(bg=UI["panel"]); dialog.transient(self); dialog.grab_set()
        ttk.Label(dialog,text="Груз").grid(row=0,column=0,sticky="w",padx=8,pady=6)
        load_var=tk.StringVar(value=loads[0].name)
        combo=ttk.Combobox(dialog,textvariable=load_var,values=[x.name for x in loads],state="readonly",width=42)
        combo.current(0)
        combo.grid(row=0,column=1,padx=8,pady=6)
        ttk.Label(dialog,text="Высота точки подачи от низа котлована, м").grid(row=1,column=0,sticky="w",padx=8,pady=6)
        try:
            default_level=float(self.parapet.get().replace(",","."))-float(self.pit_bottom.get().replace(",","."))
            default_level_text=f"{default_level:g}"
        except (TypeError,ValueError):
            default_level_text=""
        level_var=tk.StringVar(value=default_level_text)
        level_entry=ttk.Entry(dialog,textvariable=level_var,width=18)
        level_entry.grid(row=1,column=1,sticky="ew",padx=8,pady=6)
        special_var=tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog,text="Специальный подъём выше парапета (оборудование кровли)",variable=special_var).grid(row=2,column=0,columnspan=2,padx=8,pady=5,sticky="w")
        def apply():
            try:
                level=float(level_var.get().replace(",","."))
                if level<0: raise ValueError("Отметка не может быть отрицательной")
                try:
                    load_index=[load.name for load in loads].index(load_var.get())
                except ValueError as exc:
                    raise ValueError("Выберите груз") from exc
                self.work_points.append(WorkPoint(world[0],world[1],level,load_index,f"Точка подачи {len(self.work_points)+1}",special_var.get()))
                self._mark_calculation_changed()
                x,y=canvas_point; self.canvas.create_oval(x-4,y-4,x+4,y+4,fill=DRAW_COLORS["workpoint"],tags="markup")
                self.canvas.create_text(x+7,y-7,text=str(len(self.work_points)),anchor="w",fill=DRAW_COLORS["workpoint"],tags="markup")
                dialog.destroy(); self.status.set(f"Добавлена точка подачи для груза «{loads[load_index].name}».")
            except Exception as exc: messagebox.showerror("Ошибка точки подачи",str(exc),parent=dialog)
        ttk.Button(dialog,text="Добавить",command=apply).grid(row=3,column=0,columnspan=2,pady=8)

    def _collect_loads(self):
        result=[]
        for item in self.load_tree.get_children():
            v=self.load_tree.item(item,"values")
            extra = tuple(v[8:14]) if len(v) >= 14 else ("", "", "", "", "", "нет")
            result.append(Load(v[0],float(v[1]),float(v[2]),float(v[3]),float(v[4]),float(v[5]),int(float(v[6])),str(v[7]).lower() in ("да","true","1"),
                rigging_type=extra[0], rigging_branch_count=int(extra[1]) if str(extra[1]).strip() else None,
                sling_identification=extra[2], rigging_capacity_kg=float(extra[3]) if str(extra[3]).strip() else None,
                rigging_evidence=extra[4], rigging_verified=str(extra[5]).lower() in ("да", "true", "1")))
        return result

    def _input_issues(self):
        blockers=[]; reminders=[]
        if not self.plan_pdf: blockers.append("Загрузите векторный PDF-план.")
        if self.m_per_pixel is None or self.origin_px is None: blockers.append("Задайте масштаб плана по двум точкам и известному расстоянию.")
        if len(self.site_points)<3 or "site" not in self.closed_contours: blockers.append("Нарисуйте и замкните границу строительной площадки.")
        if len(self.building_points)<3 or "building" not in self.closed_contours: blockers.append("Нарисуйте и замкните контур строящегося здания.")
        if self.current_zone_points: blockers.append("Завершите или отмените незамкнутую запретную зону.")
        if self.current_storage_points: blockers.append("Завершите или отмените незамкнутую зону складирования.")
        if not self.work_points: blockers.append("Укажите минимум одну точку подачи груза — место на здании, куда кран должен доставлять материалы.")
        blockers += validate_polygon(self.site_points,"Граница площадки") if self.site_points else []
        blockers += validate_polygon(self.building_points,"Контур здания") if self.building_points else []
        for zone in self.restricted_zones: blockers += validate_zone(zone)
        for i,zone in enumerate(self.storage_zones,1): blockers += validate_polygon(zone,f"Зона складирования {i}")
        if self.unloading_points: blockers += validate_polygon(self.unloading_points,"Зона разгрузки")
        if self.site_points and self.building_points and not polygon_inside_polygon(self.building_points,self.site_points): blockers.append("Контур здания должен полностью находиться внутри границы площадки.")
        if self.building_points:
            for wp in self.work_points:
                if not point_in_polygon(wp.point,self.building_points): blockers.append(f"{wp.name}: точка подачи должна находиться внутри или на контуре здания.")
        try:
            loads=self._collect_loads()
            if not loads: blockers.append("Добавьте минимум один груз.")
            elif not any(load.active for load in loads): blockers.append("Отметьте минимум один груз как используемый в проекте.")
            for load in loads:
                if not load.name.strip() or load.load_kg<=0 or load.rigging_kg<0 or min(load.length_m,load.width_m,load.height_m)<=0 or load.lifts<=0:
                    blockers.append(f"Исправьте параметры груза «{load.name or 'без названия'}»: масса, габариты и количество подъёмов должны быть положительными.")
            for wp in self.work_points:
                if type(wp.load_index) is not int or not 0 <= wp.load_index < len(loads): blockers.append(f"{wp.name}: назначенный груз удалён; создайте точку подачи заново.")
                elif not loads[wp.load_index].active: blockers.append(f"{wp.name}: назначен груз, исключённый из проекта. Выберите активный груз или удалите точку подачи.")
            unassigned=[load.name for index,load in enumerate(loads) if load.active and not any(wp.load_index==index for wp in self.work_points)]
            if unassigned: reminders.append("Для грузов без отдельной точки подачи ("+", ".join(unassigned)+") программа выполнит консервативную проверку на всех нанесённых точках.")
        except Exception:
            blockers.append("Исправьте числовые значения в таблице грузов.")
        try:
            pit=float(self.pit_bottom.get()); parapet=float(self.parapet.get())
            if parapet<=pit: blockers.append("Отметка верха парапета должна быть выше отметки низа котлована.")
            height=parapet-pit
            for wp in self.work_points:
                if wp.level_m>height+.5 and not wp.special_roof_load: blockers.append(f"{wp.name}: отметка {wp.level_m:g} м выше парапета {height:g} м. Исправьте её или отметьте специальный подъём.")
            if self.section_building_points:
                section_height=section_contour_height(self.section_building_points)
                if abs(section_height-height)>.5: blockers.append(f"Высота по контуру разреза {section_height:.2f} м не совпадает с ручной высотой {height:.2f} м (допуск 0,5 м).")
        except ValueError: blockers.append("Заполните отметки низа котлована и верха парапета числами.")
        try:
            year=int(self.year.get())
            if year<2000 or year>2100: blockers.append("Укажите год проекта в диапазоне 2000-2100.")
        except ValueError: blockers.append("Укажите год проекта целым числом.")
        try:
            hours=float(self.hours.get()); utilization=float(self.utilization.get()); minimum=float(self.min_distance.get()); maximum=float(self.max_distance.get())
            if hours<=0 or hours>24: blockers.append("Рабочее время должно быть больше 0 и не более 24 часов в сутки.")
            if utilization<=0 or utilization>1: blockers.append("Коэффициент использования должен быть больше 0 и не более 1.")
            if minimum<0 or maximum<minimum: blockers.append("Максимальное расстояние от здания должно быть не меньше минимального; минимум не может быть отрицательным.")
            daily=float(self.daily_cost.get())
            if self.commercial_offer.get() and daily<=0: blockers.append("При наличии коммерческого предложения укажите положительную стоимость одного крана в сутки.")
        except ValueError: blockers.append("Исправьте числовые настройки расчёта: часы, коэффициент и расстояния от здания.")
        if not self.project_name.get().strip(): reminders.append("Заполните название объекта для титульного листа ППРк.")
        if not self.city.get().strip(): reminders.append("Заполните город для титульного листа ППРк.")
        if not self.unloading_points: reminders.append("Нанесите зону разгрузки для комплектного стройгенплана.")
        if not self.storage_zones: reminders.append("Нанесите минимум одну зону складирования.")
        if not self.restricted_zones and not self.no_restricted_confirmed.get(): reminders.append("Нанесите запретные зоны либо подтвердите, что их нет.")
        if not self.section_pdf: reminders.append("Загрузите PDF-разрез для высотной схемы.")
        elif self.section_m_per_pixel is None: reminders.append("Откалибруйте разрез по нижней и верхней точкам.")
        try:
            floors=int(self.floors.get()); tie_length=float(self.tie_length.get()); tie_angle=float(self.tie_angle.get())
            if floors<=0: blockers.append("Количество этажей должно быть положительным целым числом.")
            if tie_length<=0: blockers.append("Длина тяги должна быть положительной.")
            if not 0<tie_angle<180: blockers.append("Угол между тягами должен быть больше 0 и меньше 180°.")
        except ValueError: blockers.append("Исправьте количество этажей, длину и угол тяг.")
        if self.tie_ins_possible.get() and not self.section_building_points:
            reminders.append("Обведите контур здания на разрезе для проверки доступности конструкций на уровнях пристёжек.")
        if not self.author.get().strip(): reminders.append("Поле разработчика ППРк не заполнено; в отчёте останется строка для ручного заполнения.")
        if not self.organization.get().strip(): reminders.append("Заполните организацию для проектного штампа.")
        if not self.project_code.get().strip(): reminders.append("Заполните шифр проекта для проектного штампа.")
        if not self.checked_by.get().strip(): reminders.append("Заполните поле «Проверил» для проектного штампа.")
        if not self.approved_by.get().strip(): reminders.append("Заполните поле «Утвердил» для проектного штампа.")
        return list(dict.fromkeys(blockers)), reminders

    def _show_input_check(self, blockers, reminders):
        self.results.delete("1.0","end")
        self.results.insert("end","ПРОВЕРКА ИСХОДНЫХ ДАННЫХ\n\n")
        if blockers:
            self.results.insert("end","Расчёт не запущен. Необходимо заполнить или исправить:\n")
            for item in blockers: self.results.insert("end",f"  • {item}\n")
        if reminders:
            self.results.insert("end","\nДля полного комплекта ППРк рекомендуется дополнить:\n")
            for item in reminders: self.results.insert("end",f"  • {item}\n")

    def _project(self, *, require_geometry=True):
        if require_geometry and (len(self.site_points)<3 or len(self.building_points)<3): raise ValueError("Нужно нанести границу площадки и контур здания минимум по трём точкам")
        if require_geometry and not self.work_points: raise ValueError("Нужно нанести точки подачи грузов на здание")
        loads=self._collect_loads()
        for number, wp in enumerate(self.work_points, 1):
            if type(wp.load_index) is not int or not 0 <= wp.load_index < len(loads):
                raise ValueError(f"Точка подачи {number}: назначенный груз отсутствует. Проверьте ведомость и назначение груза.")
        project = ProjectInput(
            name=self.project_name.get().strip(),city=self.city.get().strip(),year=int(self.year.get()),author=self.author.get().strip(),email=self.email.get().strip(),
            pit_bottom_m=float(self.pit_bottom.get()),parapet_m=float(self.parapet.get()),
            site=SiteInput(self.site_points,self.building_points,self.restricted_zones,self.unloading_points,self.storage_zones,min_crane_to_building_m=float(self.min_distance.get()),max_crane_to_building_m=float(self.max_distance.get())),
            loads=loads,work_points=[replace(wp) for wp in self.work_points],priority=self.priority.get(),hours_per_day=float(self.hours.get()),utilization=float(self.utilization.get()),protective_screen_possible=self.screen_possible.get(),
            commercial_offer_present=self.commercial_offer.get(),commercial_offer_daily_cost=float(self.daily_cost.get()),source_plan_pdf=self.plan_pdf,source_section_pdf=self.section_pdf,
            plan_crop_box=self.plan_crop_box,section_crop_box=self.section_crop_box,
            plan_background_intensity=self._background_value(self.plan_background_intensity),section_background_intensity=self._background_value(self.section_background_intensity),
            floors=int(self.floors.get()),tie_ins_possible=self.tie_ins_possible.get(),tie_length_m=float(self.tie_length.get()),tie_angle_deg=float(self.tie_angle.get()),
            section_building_contour=self.section_building_points,
            restricted_zones_confirmed=self.no_restricted_confirmed.get() or bool(self.restricted_zones),
            loads_verified=self.loads_verified.get(),
            warning_acceptances=list(self.warning_acceptances),
        )
        if self.origin_px and self.m_per_pixel:
            project.plan_origin_x_px = self.origin_px[0]
            project.plan_origin_y_px = self.origin_px[1]
            project.plan_m_per_pixel = self.m_per_pixel
        if self.section_origin_px and self.section_m_per_pixel:
            project.section_origin_x_px=self.section_origin_px[0]; project.section_origin_y_px=self.section_origin_px[1]
            project.section_axis_dx=self.section_axis[0]; project.section_axis_dy=self.section_axis[1]
            project.section_m_per_pixel=self.section_m_per_pixel
        project.organization=self.organization.get().strip(); project.project_code=self.project_code.get().strip()
        project.project_stage=self.project_stage.get().strip() or "ППРк"; project.checked_by=self.checked_by.get().strip(); project.approved_by=self.approved_by.get().strip()
        if self.warning_acceptances:
            input_hash=hashlib.sha256(self._project_snapshot(project).encode("utf-8")).hexdigest()
            project.warning_acceptances=current_warning_acceptances(self.warning_acceptances,input_hash)
        return project

    def run_calculation(self):
        if "recalculation" in self.__dict__:
            self._show_tab(4)
            return self.recalculation.recalculate_now()
        try:
            blockers,reminders=self._input_issues()
            if blockers:
                self._reset_calculation_results(); self._show_input_check(blockers,reminders)
                self.status.set("Расчёт не запущен: исправьте пункты проверки исходных данных.")
                messagebox.showwarning("Нужно дополнить исходные данные",f"Обнаружено обязательных пунктов: {len(blockers)}. Подробности показаны на вкладке расчёта.")
                return
            self._reset_calculation_results()
            project=self._project(); catalog=load_catalog(self.catalog_path,self.user_catalog_path); self.scenarios=optimize(project,catalog,3,2.0)
            self.report_page_order=None; self.report_excluded_pages.clear(); self.report_selection_var.set("Состав листов: полный комплект по умолчанию")
            self.results.delete("1.0","end")
            if self.scenarios and self.scenarios[0].status=="BLOCKED":
                self.results.insert("end","ПОДХОДЯЩИЙ ВАРИАНТ НЕ НАЙДЕН\n\nПочему расчёт не прошёл:\n")
                for text in self.scenarios[0].reasons: self.results.insert("end",f"  • {text}\n")
                if reminders:
                    self.results.insert("end","\nТакже дополните данные для полного ППРк:\n")
                    for text in reminders: self.results.insert("end",f"  • {text}\n")
                self.status.set("Подходящий вариант не найден. Причины и рекомендации показаны в расчёте.")
                messagebox.showwarning("Вариант не найден","Программа определила причины отказа. Они показаны на вкладке расчёта.")
                return
            run_id=f"GUI-{datetime.now().astimezone():%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"
            created_at=datetime.now().astimezone().isoformat(timespec="seconds")
            try:
                catalog_v3=load_catalog_v3(self.catalog_v3_path)
                self.scenario_verifications=list(
                    verify_scenarios_v21(
                        project,
                        self.scenarios,
                        catalog_v3,
                        run_id=run_id,
                        created_at=created_at,
                    )
                )
            except Exception as exc:
                self.scenario_verifications=[
                    ScenarioVerificationV21(
                        index,
                        IntegrationStatus.EXPERT_REVIEW_REQUIRED,
                        False,
                        (f"V3_CATALOG_UNAVAILABLE: каталог V3 не загружен: {exc}",),
                        None,
                        None,
                    )
                    for index,_scenario in enumerate(self.scenarios)
                ]
            self.calculation_input_snapshot=self._project_snapshot(project)
            self._refresh_release_variant_choices()
            for i,s in enumerate(self.scenarios,1):
                self.results.insert("end",f"ВАРИАНТ {i}: {s.status}\n")
                for j,p in enumerate(s.placements,1):
                    sector=(f"; разрешённый сектор {_sector_text(p.allowed_sector_start_deg,p.allowed_sector_end_deg)}" if p.allowed_sector_start_deg is not None else "")
                    self.results.insert("end",f"  К{j} {p.model}: X={p.x:.1f}, Y={p.y:.1f}; рабочий вылет до {p.max_radius_m:.1f} м; монтажная стрела L={p.jib_length_m:.1f} м; высота крюка {p.required_hook_height_m:.1f} м; уровень стрелы {(p.jib_level_m or p.required_hook_height_m):.1f} м{sector}\n")
                    if p.tie_in_levels_m:
                        levels=", ".join(f"{value:.1f}" for value in p.tie_in_levels_m)
                        self.results.insert("end",f"    ПРИСТЁЖКИ: уровни {levels} м; дополнительных секций 5 м — {p.total_additional_sections}; принятая высота {p.accepted_crane_height_m:.1f} м; требуемая длина тяги {p.required_tie_length_m:.1f} м.\n")
                if s.joint_plan:
                    jp=s.joint_plan
                    self.results.insert("end",f"  СОВМЕСТНАЯ РАБОТА: оси {jp.axis_distance_m:.1f} м; общая зона {jp.overlap_area_m2:.1f} м²; горизонтальный разрыв ≥{jp.working_horizontal_clearance_m:.1f} м; оси стрел разнесены на {jp.vertical_separation_m:.1f} м ({jp.jib_structural_height_m:.1f} м стрела + 1.0 м зазор); защитный габарит башен {jp.tower_protection_radius_m:.1f}+{jp.tower_protection_radius_m:.1f}={jp.combined_tower_envelope_m:.1f} м; приоритет К{jp.priority_crane_index}.\n")
                    self.results.insert("end","  В общей зоне допускается один груз; второй кран ожидает вне зоны. Параметры перед настройкой координатной защиты сверить с паспортами.\n")
                if s.calendar_days is not None: self.results.insert("end",f"  Оценка: {s.calendar_days:.1f} календарных дней\n")
                self.results.insert("end",f"  Баланс подъёмов: {s.accounted_lifts} из {s.total_active_lifts}\n")
                if s.crane_work_hours:
                    self.results.insert("end","  Загрузка: "+", ".join(f"К{n+1} — {hours:.1f} ч" for n,hours in enumerate(s.crane_work_hours))+"\n")
                for text in s.warnings+s.reasons: self.results.insert("end",f"  • {text}\n")
                if i-1 < len(self.scenario_verifications):
                    self.results.insert("end",self._render_scenario_verification(self.scenario_verifications[i-1]))
                self.results.insert("end","\n")
            if reminders:
                self.results.insert("end","ДОПОЛНИТЬ ДЛЯ ПОЛНОГО ППРк:\n")
                for text in reminders: self.results.insert("end",f"  • {text}\n")
            self.status.set("Расчёт завершён. Проверьте условия каждого варианта.")
        except Exception as exc: messagebox.showerror("Расчёт не выполнен",str(exc))

    def preview_report_pages(self):
        temp = None
        try:
            if not self.scenarios:
                self.run_calculation()
            inputs = self._current_release_inputs()
            fingerprint = release_fingerprint(*inputs)
            view = prepare_release(*inputs[:3])
            if view.bundle.requested_status != view.bundle.effective_status:
                project, scenario, verification, _ = inputs
                draft = replace(project, pprk_release=replace(project.pprk_release, status=ReleaseStatus.PRELIMINARY))
                view = prepare_release(draft, scenario, verification)
            temp = TemporaryDirectory(dir=writable_temp_root(), prefix="craneplan_preview_")
            preview_path = Path(temp.name) / "preview.pdf"
            self.status.set("Формируется предпросмотр полного ППРк…")
            self.update_idletasks()
            publish_release(preview_path, view, fingerprint, self._current_release_fingerprint, render=generate_report)
            from pypdf import PdfReader
            with preview_path.open("rb") as stream:
                titles = []
                for number, page in enumerate(PdfReader(stream).pages, 1):
                    lines = (page.extract_text() or "").strip().splitlines()
                    titles.append(lines[0][:100] if lines else f"Лист {number}")
            dialog = tk.Toplevel(self)
            dialog.title(f"Предпросмотр ППРк — {view.bundle.effective_status.value}")
            dialog.geometry(f"{min(1080,self.winfo_screenwidth()-40)}x{min(720,self.winfo_screenheight()-80)}")
            dialog.transient(self)
            dialog.grab_set()
            left = ttk.Frame(dialog)
            left.pack(side="left", fill="y", padx=6, pady=6)
            tree = self._release_table(left, ("Стр.", "Физический лист"), 18, (45, 280))
            for i, title in enumerate(titles):
                tree.insert("", "end", iid=str(i), values=(i + 1, title))
            preview = ttk.Label(dialog, anchor="center")
            preview.pack(side="right", fill="both", expand=True)
            def show_selected(_event=None):
                selected = tree.selection()
                if selected:
                    image = render_page(preview_path, int(selected[0]), .7)
                    image.thumbnail((560, 620))
                    preview.photo = ImageTk.PhotoImage(image)
                    preview.configure(image=preview.photo)
            def close():
                dialog.destroy()
                temp.cleanup()
            ttk.Label(left, text="Порядок соответствует физическим ссылкам.\nСостав меняется на вкладках «Разделы» и «Приложения».",
                      wraplength=325).pack(anchor="w", pady=4)
            ttk.Label(left, textvariable=self.report_selection_var, wraplength=325).pack(anchor="w")
            ttk.Button(left, text="Закрыть", command=close).pack()
            tree.bind("<<TreeviewSelect>>", show_selected)
            dialog.protocol("WM_DELETE_WINDOW", close)
            tree.selection_set("0")
            self.preview_fingerprint = fingerprint
            self.report_selection_var.set(f"Предпросмотр актуален • {view.bundle.effective_status.value} • {len(titles)} стр.")
            self._watch_preview_sources(fingerprint)
            self.status.set("Предпросмотр готов.")
        except Exception as exc:
            if temp is not None:
                temp.cleanup()
            messagebox.showerror("Предпросмотр не выполнен", str(exc))

    def save_and_report(self):
        try:
            if not self.scenarios:
                self.run_calculation()
            inputs = self._current_release_inputs()
            project, scenario, verification, index = inputs
            fingerprint = release_fingerprint(*inputs)
            view = prepare_release(project, scenario, verification)
            require_saveable_release(view, verification)
            folder = create_project_folder(self.project_root, project)
            names = {ReleaseStatus.PRELIMINARY: "предварительный", ReleaseStatus.REVIEW: "на_проверку",
                     ReleaseStatus.COORDINATION: "на_согласование", ReleaseStatus.APPROVED: "утверждённый",
                     ReleaseStatus.PRODUCTION: "в_производство"}
            report = folder / "reports" / f"ППРк_{names[view.bundle.effective_status]}.pdf"
            sources = [project.source_plan_pdf, project.source_section_pdf,
                       *(doc.attachment_path for doc in project.pprk_release.external_documents)]
            if any(source and (Path(source).resolve() == report.resolve()
                               or (report.exists() and Path(source).exists() and report.samefile(source)))
                   for source in sources):
                raise ValueError("Исходный PDF совпадает с выходным файлом. Выберите отдельный исходный документ.")
            def stage_project(directory):
                saved = replace(project)
                (directory / "sources").mkdir()
                (directory / "reports").mkdir()
                for key, role in (("source_plan_pdf", "план"), ("source_section_pdf", "разрез")):
                    source = getattr(project, key)
                    if source:
                        copied = copy_source_pdf(source, directory, role)
                        setattr(saved, key, str(folder / copied.relative_to(directory)))
                save_protocol_atomic(directory / "reports" / "calculation_protocol_v21.json", verification.protocol)
                save_project(directory, saved, [s.to_dict() for s in self.scenarios], selected_scenario_index=index,
                             scenario_verifications=[v.to_dict() for v in self.scenario_verifications])
                return [(p, folder / p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()]

            publish_release(report, view, fingerprint, self._current_release_fingerprint,
                            render=generate_report, stage_files=stage_project)
            self.report_path_var.set(f"Готово: {report}")
            self.status.set("Проект и PDF сохранены.")
            messagebox.showinfo("Готово", f"Проект сохранён:\n{folder}")
        except (ValueError, OSError) as exc:
            messagebox.showwarning("Выпуск ППРк заблокирован", str(exc))
        except Exception as exc:
            messagebox.showerror("Ошибка сохранения", str(exc))


    def destroy(self):
        if "recalculation" in self.__dict__:
            self.recalculation.shutdown()
        if "_calculation_executor" in self.__dict__:
            self._calculation_executor.shutdown(wait=False,cancel_futures=True)
        super().destroy()


def run():
    CranePlanApp().mainloop()
