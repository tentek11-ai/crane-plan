"""Русский настольный интерфейс первой версии Crane Plan."""

from __future__ import annotations

import json
import math
import tkinter as tk
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from .catalog import load_catalog
from .geometry import point_in_polygon, polygon_inside_polygon, validate_polygon
from .library import load_library, open_local_path, resolve_local_file
from .models import Load, ProjectInput, SiteInput, WorkPoint
from .optimizer import optimize
from .pdf_workspace import calibration_m_per_pixel, crop_pixel_box, inspect_pdf, normalize_crop_box, pixel_to_world, render_page, suggest_vector_bounds
from .project_io import copy_source_pdf, create_project_folder, load_project, save_project
from .report import generate_report


APP_TITLE = "КранПлан 2.0.3 — BIM-среда предварительной расстановки башенных кранов"


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
        self.loads_path = self.resource_root / "02_processed_data/loads/standard_monolithic_loads.json"
        self.project_root = Path.home() / "Documents" / "КранПлан проекты"
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
        self.restricted_zones: list[list[tuple[float, float]]] = []
        self.unloading_points: list[tuple[float, float]] = []
        self.current_storage_points: list[tuple[float, float]] = []
        self.storage_zones: list[list[tuple[float, float]]] = []
        self.contour_pixels: dict[str, list[tuple[float, float]]] = {"site": [], "building": [], "restricted": [], "unloading": [], "storage": []}
        self.closed_contours: set[str] = set()
        self.work_points: list[WorkPoint] = []
        self.scenarios = []
        self.report_page_order: list[int] | None = None
        self.report_excluded_pages: set[int] = set()
        self.loads = self._default_loads()
        self._configure_revit_theme()
        self._build_ui()
        self._configure_text_editing()

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
        tk.Label(title_bar, text="КранПлан 2.0.3", bg="#171b1f", fg=UI["text"], font=("Segoe UI Semibold", 10), padx=10).pack(side="left")
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
        ttk.Button(actions, text="Открыть весь список", command=lambda: open_local_path(resolve_local_file(library_root, data.get("index_file", "index.html")))).pack(side="left")
        ttk.Button(actions, text="Открыть папку", command=lambda: open_local_path(library_root)).pack(side="right")

        tree.bind("<<TreeviewSelect>>", show_selected)
        tree.bind("<Double-1>", lambda _event: open_selected())
        if entries:
            tree.selection_set("doc_0")
            show_selected()
        self.status.set(f"Открыта локальная библиотека: {data.get('title', '')}.")

    def _on_tab_changed(self, _event=None):
        index = self.notebook.index(self.notebook.select())
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
            self.load_tree.insert("", "end", values=(load.name, load.load_kg, load.rigging_kg, load.length_m, load.width_m, load.height_m, load.lifts, "да" if load.active else "нет"))
        buttons = ttk.Frame(frame); buttons.pack(fill="x", padx=10, pady=5)
        ttk.Button(buttons, text="Редактировать выбранный", command=self.edit_load).pack(side="left")
        ttk.Button(buttons, text="Добавить нестандартный груз", command=lambda: self.edit_load(new=True)).pack(side="left", padx=6)
        ttk.Button(buttons, text="Удалить выбранный груз", command=self.delete_load).pack(side="left", padx=6)

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
        ttk.Button(frame, text="РАССЧИТАТЬ ДО 3 ВАРИАНТОВ", command=self.run_calculation, style="Accent.TButton").pack(pady=8)
        self.results = tk.Text(frame, height=24, wrap="word", bg=UI["field"], fg=UI["text"], insertbackground=UI["text"], selectbackground=UI["selection"], relief="flat", padx=10, pady=8)
        self.results.pack(fill="both", expand=True, padx=10, pady=8)

    def _build_report_tab(self):
        frame = self.tabs["6. Отчёт"]
        ttk.Label(frame, text="После расчёта сохраните проект. Будет создана отдельная папка с исходными PDF, версиями project.json и печатным отчётом.", wraplength=900).pack(anchor="w", padx=12, pady=12)
        buttons=ttk.Frame(frame); buttons.pack(fill="x",padx=12,pady=8)
        ttk.Button(buttons, text="Предпросмотр и состав листов", command=self.preview_report_pages).pack(side="left")
        ttk.Button(buttons, text="Сохранить проект и сформировать PDF ППРк", command=self.save_and_report).pack(side="left",padx=8)
        self.report_selection_var=tk.StringVar(value="Состав листов: полный комплект по умолчанию")
        ttk.Label(frame,textvariable=self.report_selection_var).pack(anchor="w",padx=12,pady=4)
        self.report_path_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.report_path_var, wraplength=1000).pack(anchor="w", padx=12, pady=8)

    def open_project(self):
        path=filedialog.askopenfilename(title="Открыть проект КранПлан",filetypes=[("Проект КранПлан","project.json"),("JSON","*.json")])
        if not path: return
        try:
            project=load_project(path)
            for var,value in (
                (self.project_name,project.name),(self.city,project.city),(self.year,project.year),(self.author,project.author),(self.email,project.email),
                (self.pit_bottom,project.pit_bottom_m),(self.parapet,project.parapet_m),(self.organization,project.organization),(self.project_code,project.project_code),
                (self.project_stage,project.project_stage),(self.checked_by,project.checked_by),(self.approved_by,project.approved_by),(self.hours,project.hours_per_day),
                (self.utilization,project.utilization),(self.min_distance,project.site.min_crane_to_building_m),(self.max_distance,project.site.max_crane_to_building_m),
                (self.daily_cost,project.commercial_offer_daily_cost),
                (self.floors,project.floors),(self.tie_length,project.tie_length_m),(self.tie_angle,project.tie_angle_deg),
            ): var.set(str(value))
            self.priority.set(project.priority); self.screen_possible.set(project.protective_screen_possible); self.commercial_offer.set(project.commercial_offer_present); self.tie_ins_possible.set(project.tie_ins_possible)
            self.site_points=list(project.site.boundary); self.building_points=list(project.site.building); self.restricted_zones=[list(z) for z in project.site.restricted_zones]
            self.unloading_points=list(project.site.unloading_zone); self.storage_zones=[list(z) for z in project.site.storage_zones]; self.work_points=list(project.work_points)
            self.current_zone_points=[]; self.current_storage_points=[]; self.closed_contours={"site","building"}
            if self.unloading_points: self.closed_contours.add("unloading")
            self.m_per_pixel=project.plan_m_per_pixel or None; self.origin_px=(project.plan_origin_x_px,project.plan_origin_y_px) if self.m_per_pixel else None
            self.section_m_per_pixel=project.section_m_per_pixel or None
            self.section_origin_px=(project.section_origin_x_px,project.section_origin_y_px) if self.section_m_per_pixel else None
            self.section_axis=(project.section_axis_dx,project.section_axis_dy)
            self.section_building_points=list(project.section_building_contour); self.section_contour_closed=bool(self.section_building_points)
            self.plan_crop_box=normalize_crop_box(project.plan_crop_box); self.section_crop_box=normalize_crop_box(project.section_crop_box)
            self.plan_background_intensity.set(str(round(project.plan_background_intensity*100)))
            self.section_background_intensity.set(str(round(project.section_background_intensity*100)))
            self.plan_pdf=project.source_plan_pdf if project.source_plan_pdf and Path(project.source_plan_pdf).is_file() else ""
            self.section_pdf=project.source_section_pdf if project.source_section_pdf and Path(project.source_section_pdf).is_file() else ""
            self.load_tree.delete(*self.load_tree.get_children())
            for load in project.loads: self.load_tree.insert("","end",values=(load.name,load.load_kg,load.rigging_kg,load.length_m,load.width_m,load.height_m,load.lifts,"да" if load.active else "нет"))
            self.no_restricted_confirmed.set(project.restricted_zones_confirmed)
            if self.plan_pdf:
                self.plan_label.config(text=Path(self.plan_pdf).name); self._show_plan(); self._redraw_loaded_markup()
            else: self.plan_label.config(text="Исходный план не найден; выберите PDF повторно")
            if self.section_pdf:
                self.section_label.config(text=Path(self.section_pdf).name); self._show_section(); self._redraw_section_calibration()
            else: self.section_label.config(text="Исходный разрез не найден; выберите PDF повторно")
            self.scenarios=[]; self.report_page_order=None; self.report_excluded_pages.clear()
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
        for i,zone in enumerate(self.restricted_zones): draw_polygon(zone,DRAW_COLORS["restricted"],f"draw_restricted_{i}")
        for i,zone in enumerate(self.storage_zones): draw_polygon(zone,DRAW_COLORS["storage"],f"draw_storage_{i}")
        for i,wp in enumerate(self.work_points,1):
            x,y=self._world_to_canvas(wp.point); self.canvas.create_oval(x-4,y-4,x+4,y+4,fill=DRAW_COLORS["workpoint"],tags="markup"); self.canvas.create_text(x+7,y-7,text=str(i),anchor="w",fill=DRAW_COLORS["workpoint"],tags="markup")

    def _redraw_section_calibration(self):
        if not self.section_origin_px or not self.section_m_per_pixel: return
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
        path = filedialog.askopenfilename(title="Выберите векторный PDF-план", filetypes=[("PDF", "*.pdf")])
        if not path: return
        try:
            inspection = inspect_pdf(path)
            if not inspection.likely_vector:
                messagebox.showerror("Не векторный PDF", "В документе недостаточно векторных элементов. Растровые сканы в первой версии не поддерживаются.")
                return
            self.plan_pdf = path
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
        if factor < 1:
            image = image.resize((int(image.width * factor), int(image.height * factor)))
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
        if factor < 1:
            image = image.resize((int(image.width * factor), int(image.height * factor)))
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
        else: self.on_canvas_click(event)

    def _on_plan_drag(self,event):
        if self.plan_crop_active: self._crop_drag(self.canvas,event)

    def _on_plan_release(self,event):
        if self.plan_crop_active: self._finish_crop(event)

    def _on_section_press(self,event):
        if self.section_crop_active: self._crop_press(self.section_canvas,event)
        else: self.on_section_click(event)

    def _on_section_drag(self,event):
        if self.section_crop_active: self._crop_drag(self.section_canvas,event)

    def _on_section_release(self,event):
        if self.section_crop_active: self._finish_crop(event,section=True)

    def reset_plan_crop(self):
        if not self.plan_pdf or not self._confirm_crop_reset(): return
        self._rebase_crop(False,(0.0,0.0,1.0,1.0)); self._show_plan(); self._redraw_loaded_markup(); self.status.set("План возвращён к полной странице без потери разметки.")

    def reset_section_crop(self):
        if not self.section_pdf or not self._confirm_crop_reset(section=True): return
        self._rebase_crop(True,(0.0,0.0,1.0,1.0)); self._show_section(); self._redraw_section_calibration(); self.status.set("Разрез возвращён к полной странице без потери калибровки.")

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
        self.section_canvas.create_oval(event.x-4,event.y-4,event.x+4,event.y+4,fill=DRAW_COLORS["section"],tags="section_markup")
        if len(self.section_calibration_points)==2:
            try:
                p1,p2=self.section_calibration_points; distance=float(self.section_distance_var.get())
                self.section_m_per_pixel=calibration_m_per_pixel(p1,p2,distance); self.section_origin_px=p1
                length=math.hypot(p2[0]-p1[0],p2[1]-p1[1]); self.section_axis=((p2[0]-p1[0])/length,(p2[1]-p1[1])/length)
                self.section_canvas.create_line(p1[0]*self.section_image_scale,p1[1]*self.section_image_scale,p2[0]*self.section_image_scale,p2[1]*self.section_image_scale,fill=DRAW_COLORS["section"],width=2,tags="section_markup")
                self.status.set(f"Масштаб разреза принят: {self.section_m_per_pixel:.5f} м/пиксель. Высотная схема попадёт в ППРк.")
            except Exception as exc:
                messagebox.showerror("Ошибка масштаба разреза",str(exc)); self.section_calibration_points.clear()

    def start_section_building_contour(self):
        if not self.section_m_per_pixel:
            messagebox.showwarning("Сначала масштаб","Сначала откалибруйте разрез по двум точкам."); return
        self.section_mode="building"; self.status.set("Режим: контур здания на разрезе. Нанесите вершины по порядку.")

    def finish_section_building_contour(self):
        if self.section_mode!="building" or len(self.section_building_points)<3:
            messagebox.showwarning("Недостаточно точек","Для контура здания требуется минимум три точки."); return
        self.section_contour_closed=True; self._redraw_section_building_contour(); self.scenarios=[]; self.status.set("Контур здания на разрезе замкнут.")

    def undo_section_contour_point(self):
        if self.section_contour_closed or not self.section_building_points: return
        self.section_building_points.pop(); self._redraw_section_building_contour(); self.scenarios=[]

    def clear_section_building_contour(self):
        self.section_building_points.clear(); self.section_contour_pixels.clear(); self.section_contour_closed=False; self.section_canvas.delete("section_building"); self.scenarios=[]; self.status.set("Контур здания на разрезе очищен.")

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
            self.restricted_zones.append(self.current_zone_points[:])
            self.current_zone_points.clear()
            self.contour_pixels["restricted"] = []
            self.status.set(f"Запретная зона замкнута. Всего зон: {len(self.restricted_zones)}. Можно рисовать следующую.")
        elif self.mode == "storage":
            self.storage_zones.append(self.current_storage_points[:]); self.current_storage_points.clear(); self.contour_pixels["storage"]=[]
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

    def clear_markup(self):
        self._clear_plan_geometry()
        self._show_plan(); self.status.set("Разметка очищена. Выберите две точки масштаба.")

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
        def apply():
            try:
                row=(vars_[0].get().strip(),)+tuple(float(v.get()) for v in vars_[1:6])+(int(float(vars_[6].get())),)+("да" if active_var.get() else "нет",)
                if not row[0] or row[1]<=0 or row[2]<0 or min(row[3:6])<=0 or row[6]<=0: raise ValueError("Проверьте название, массы, габариты и количество подъёмов")
                if new or not selected: self.load_tree.insert("","end",values=row)
                else: self.load_tree.item(selected[0],values=row)
                dialog.destroy(); self.scenarios=[]
            except Exception as exc: messagebox.showerror("Груз не сохранён",str(exc),parent=dialog)
        ttk.Button(dialog,text="Сохранить",command=apply).grid(row=8,column=0,columnspan=2,pady=8)

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
        self.scenarios=[]
        self.status.set("Груз удалён. Точки, относившиеся к нему, переназначены на первый груз; проверьте их.")

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
                x,y=canvas_point; self.canvas.create_oval(x-4,y-4,x+4,y+4,fill=DRAW_COLORS["workpoint"],tags="markup")
                self.canvas.create_text(x+7,y-7,text=str(len(self.work_points)),anchor="w",fill=DRAW_COLORS["workpoint"],tags="markup")
                dialog.destroy(); self.status.set(f"Добавлена точка подачи для груза «{loads[load_index].name}».")
            except Exception as exc: messagebox.showerror("Ошибка точки подачи",str(exc),parent=dialog)
        ttk.Button(dialog,text="Добавить",command=apply).grid(row=3,column=0,columnspan=2,pady=8)

    def _collect_loads(self):
        result=[]
        for item in self.load_tree.get_children():
            v=self.load_tree.item(item,"values")
            result.append(Load(v[0],float(v[1]),float(v[2]),float(v[3]),float(v[4]),float(v[5]),int(float(v[6])),str(v[7]).lower() in ("да","true","1")))
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
        for i,zone in enumerate(self.restricted_zones,1): blockers += validate_polygon(zone,f"Запретная зона {i}")
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
                if wp.load_index<0 or wp.load_index>=len(loads): blockers.append(f"{wp.name}: назначенный груз удалён; создайте точку подачи заново.")
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
                section_top=max(y for _,y in self.section_building_points)
                if abs(section_top-height)>.5: blockers.append(f"Высота по контуру разреза {section_top:.2f} м не совпадает с ручной высотой {height:.2f} м (допуск 0,5 м).")
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

    def _project(self):
        if len(self.site_points)<3 or len(self.building_points)<3: raise ValueError("Нужно нанести границу площадки и контур здания минимум по трём точкам")
        if not self.work_points: raise ValueError("Нужно нанести точки подачи грузов на здание")
        loads=self._collect_loads()
        for wp in self.work_points: wp.load_index=min(wp.load_index,len(loads)-1)
        project = ProjectInput(
            name=self.project_name.get().strip(),city=self.city.get().strip(),year=int(self.year.get()),author=self.author.get().strip(),email=self.email.get().strip(),
            pit_bottom_m=float(self.pit_bottom.get()),parapet_m=float(self.parapet.get()),
            site=SiteInput(self.site_points,self.building_points,self.restricted_zones,self.unloading_points,self.storage_zones,min_crane_to_building_m=float(self.min_distance.get()),max_crane_to_building_m=float(self.max_distance.get())),
            loads=loads,work_points=self.work_points,priority=self.priority.get(),hours_per_day=float(self.hours.get()),utilization=float(self.utilization.get()),protective_screen_possible=self.screen_possible.get(),
            commercial_offer_present=self.commercial_offer.get(),commercial_offer_daily_cost=float(self.daily_cost.get()),source_plan_pdf=self.plan_pdf,source_section_pdf=self.section_pdf,
            plan_crop_box=self.plan_crop_box,section_crop_box=self.section_crop_box,
            plan_background_intensity=self._background_value(self.plan_background_intensity),section_background_intensity=self._background_value(self.section_background_intensity),
            floors=int(self.floors.get()),tie_ins_possible=self.tie_ins_possible.get(),tie_length_m=float(self.tie_length.get()),tie_angle_deg=float(self.tie_angle.get()),
            section_building_contour=self.section_building_points,
            restricted_zones_confirmed=self.no_restricted_confirmed.get() or bool(self.restricted_zones),
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
        return project

    def run_calculation(self):
        try:
            blockers,reminders=self._input_issues()
            if blockers:
                self.scenarios=[]; self._show_input_check(blockers,reminders)
                self.status.set("Расчёт не запущен: исправьте пункты проверки исходных данных.")
                messagebox.showwarning("Нужно дополнить исходные данные",f"Обнаружено обязательных пунктов: {len(blockers)}. Подробности показаны на вкладке расчёта.")
                return
            project=self._project(); catalog=load_catalog(self.catalog_path); self.scenarios=optimize(project,catalog,3,2.0)
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
                self.results.insert("end","\n")
            if reminders:
                self.results.insert("end","ДОПОЛНИТЬ ДЛЯ ПОЛНОГО ППРк:\n")
                for text in reminders: self.results.insert("end",f"  • {text}\n")
            self.status.set("Расчёт завершён. Проверьте условия каждого варианта.")
        except Exception as exc: messagebox.showerror("Расчёт не выполнен",str(exc))

    def preview_report_pages(self):
        temp=None
        try:
            if not self.scenarios: self.run_calculation()
            if not self.scenarios: return
            project=self._project(); temp=TemporaryDirectory(prefix="craneplan_preview_")
            preview_path=Path(temp.name)/"preview.pdf"
            self.status.set("Формируется предпросмотр листов..."); self.update_idletasks()
            generate_report(preview_path,project,self.scenarios)
            from pypdf import PdfReader
            reader=PdfReader(str(preview_path)); page_count=len(reader.pages); titles=[]
            for number,page in enumerate(reader.pages,1):
                lines=[line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
                title=lines[0] if lines else f"Лист {number}"
                titles.append(title[:100])
            if getattr(reader,"stream",None): reader.stream.close()
            if self.report_page_order is None or set(self.report_page_order)!=set(range(page_count)):
                order=list(range(page_count)); excluded=set()
            else:
                order=list(self.report_page_order); excluded=set(self.report_excluded_pages)&set(order)
            dialog=tk.Toplevel(self); dialog.title("Предпросмотр и состав листов ППРк"); dialog.geometry("1180x760"); dialog.configure(bg=UI["panel"]); dialog.transient(self); dialog.grab_set()
            left=ttk.Frame(dialog); left.pack(side="left",fill="y",padx=8,pady=8)
            tree=ttk.Treeview(left,columns=("included","number","title"),show="headings",height=27)
            tree.heading("included",text="Включён"); tree.heading("number",text="Исх. №"); tree.heading("title",text="Наименование листа")
            tree.column("included",width=70,anchor="center"); tree.column("number",width=55,anchor="center"); tree.column("title",width=420)
            tree.pack(fill="y",expand=True)
            preview=ttk.Label(dialog,anchor="center"); preview.pack(side="right",fill="both",expand=True,padx=8,pady=8)
            controls=ttk.Frame(left); controls.pack(fill="x",pady=6)
            preview_photo=[None]

            def rebuild(select_index=None):
                tree.delete(*tree.get_children())
                for position,page_index in enumerate(order):
                    tree.insert("","end",iid=str(page_index),values=("нет" if page_index in excluded else "да",page_index+1,titles[page_index]))
                if select_index is not None:
                    tree.selection_set(str(select_index)); tree.focus(str(select_index)); tree.see(str(select_index))

            def show_selected(_event=None):
                selected=tree.selection()
                if not selected: return
                page_index=int(selected[0]); image=render_page(preview_path,page_index,.7)
                image.thumbnail((520,650)); preview_photo[0]=ImageTk.PhotoImage(image)
                preview.configure(image=preview_photo[0],text="")

            def toggle():
                selected=tree.selection()
                if not selected: return
                page_index=int(selected[0])
                if page_index in excluded: excluded.remove(page_index)
                else: excluded.add(page_index)
                rebuild(page_index); show_selected()

            def move(delta):
                selected=tree.selection()
                if not selected: return
                page_index=int(selected[0]); position=order.index(page_index); target=position+delta
                if target<0 or target>=len(order): return
                order[position],order[target]=order[target],order[position]; rebuild(page_index); show_selected()

            def close(save=False):
                if save:
                    included=[page for page in order if page not in excluded]
                    if not included:
                        messagebox.showwarning("Пустой комплект","Оставьте включённым хотя бы один лист.",parent=dialog); return
                    self.report_page_order=list(order); self.report_excluded_pages=set(excluded)
                    self.report_selection_var.set(f"Состав листов: включено {len(included)} из {len(order)}; порядок сохранён")
                    self.status.set("Состав и порядок листов сохранены для итогового PDF.")
                dialog.destroy(); temp.cleanup()

            ttk.Button(controls,text="Включить / исключить",command=toggle).pack(side="left")
            ttk.Button(controls,text="Вверх",command=lambda:move(-1)).pack(side="left",padx=3)
            ttk.Button(controls,text="Вниз",command=lambda:move(1)).pack(side="left",padx=3)
            ttk.Button(left,text="Применить состав и порядок",command=lambda:close(True)).pack(fill="x",pady=3)
            ttk.Button(left,text="Закрыть без изменений",command=lambda:close(False)).pack(fill="x",pady=3)
            tree.bind("<<TreeviewSelect>>",show_selected); dialog.protocol("WM_DELETE_WINDOW",lambda:close(False))
            rebuild(order[0]); show_selected(); self.status.set("Предпросмотр готов. Настройте состав и порядок листов.")
        except Exception as exc:
            if temp is not None: temp.cleanup()
            messagebox.showerror("Предпросмотр не выполнен",str(exc))

    def save_and_report(self):
        try:
            if not self.scenarios: self.run_calculation()
            if not self.scenarios: return
            release_issues=[]
            if not self.project_name.get().strip(): release_issues.append("Не заполнено название объекта.")
            if not self.city.get().strip(): release_issues.append("Не заполнен город.")
            if not self.unloading_points: release_issues.append("Не нанесена зона разгрузки.")
            if not self.storage_zones: release_issues.append("Не нанесена зона складирования.")
            if not self.restricted_zones and not self.no_restricted_confirmed.get(): release_issues.append("Не подтверждено наличие или отсутствие запретных зон.")
            if any(s.accounted_lifts!=s.total_active_lifts for s in self.scenarios): release_issues.append("Не все активные подъёмы учтены в расчёте.")
            if release_issues:
                messagebox.showwarning("Выпуск ППРк заблокирован","Дополните исходные данные:\n\n"+"\n".join("• "+item for item in release_issues)); return
            project=self._project(); self.project_root.mkdir(parents=True,exist_ok=True)
            folder=create_project_folder(self.project_root,project)
            if self.plan_pdf: project.source_plan_pdf=str(copy_source_pdf(self.plan_pdf,folder,"план"))
            if self.section_pdf: project.source_section_pdf=str(copy_source_pdf(self.section_pdf,folder,"разрез"))
            save_project(folder,project,[s.to_dict() for s in self.scenarios])
            selected_pages=None if self.report_page_order is None else [page for page in self.report_page_order if page not in self.report_excluded_pages]
            report=generate_report(folder/"reports"/"ППРк_предварительный.pdf",project,self.scenarios,selected_pages=selected_pages)
            self.report_path_var.set(f"Готово: {report}")
            self.status.set("Проект и PDF сохранены.")
            messagebox.showinfo("Готово",f"Проект сохранён:\n{folder}")
        except Exception as exc: messagebox.showerror("Ошибка сохранения",str(exc))


def run():
    CranePlanApp().mainloop()
