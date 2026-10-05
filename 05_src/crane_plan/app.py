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
from .models import Load, ProjectInput, SiteInput, WorkPoint
from .optimizer import optimize
from .pdf_workspace import calibration_m_per_pixel, inspect_pdf, pixel_to_world, render_page, suggest_vector_bounds
from .project_io import copy_source_pdf, create_project_folder, load_project, save_project
from .report import generate_report


APP_TITLE = "КранПлан 1.5.1 - предварительная расстановка башенных кранов"


class CranePlanApp(tk.Tk):
    def __init__(self, resource_root: Path | None = None):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x820")
        self.minsize(1020, 700)
        self.resource_root = resource_root or Path(__file__).parents[2]
        self.catalog_path = self.resource_root / "02_processed_data/cranes/crane_configurations.json"
        self.loads_path = self.resource_root / "02_processed_data/loads/standard_monolithic_loads.json"
        self.project_root = Path.home() / "Documents" / "КранПлан проекты"
        self.plan_pdf = ""
        self.section_pdf = ""
        self.plan_image = None
        self.plan_photo = None
        self.section_image = None
        self.section_photo = None
        self.section_image_scale = 1.0
        self.section_calibration_points: list[tuple[float, float]] = []
        self.section_m_per_pixel: float | None = None
        self.section_origin_px: tuple[float, float] | None = None
        self.section_axis: tuple[float, float] = (0.0, -1.0)
        self.image_scale = 1.0
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
        self._build_ui()

    def _default_loads(self) -> list[Load]:
        data = json.loads(self.loads_path.read_text(encoding="utf-8"))
        return [Load(name=x["name"], load_kg=x["load_kg"], rigging_kg=x["rigging_kg"], length_m=x["length_m"], width_m=x["width_m"], height_m=x["height_m"], lifts=10) for x in data["loads"]]

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs = {name: ttk.Frame(notebook) for name in ("1. Проект", "2. План", "3. Разрез", "4. Грузы", "5. Расчёт", "6. Отчёт")}
        for name, frame in self.tabs.items():
            notebook.add(frame, text=name)
        self._build_project_tab()
        self._build_plan_tab()
        self._build_section_tab()
        self._build_loads_tab()
        self._build_calculation_tab()
        self._build_report_tab()
        self.status = tk.StringVar(value="Создайте проект и загрузите векторный PDF-план.")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def _field(self, parent, row, label, default="", width=45):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        var = tk.StringVar(value=str(default))
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        return var

    def _build_project_tab(self):
        frame = self.tabs["1. Проект"]
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
        ttk.Label(zones, text="Точка подачи — место на здании, куда кран должен доставить груз. Для зон укажите вершины и замкните контур.").pack(side="left", padx=10)
        self.canvas = tk.Canvas(frame, bg="#ececec", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=6, pady=5)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

    def _build_section_tab(self):
        frame = self.tabs["3. Разрез"]
        toolbar = ttk.Frame(frame); toolbar.pack(fill="x", padx=6, pady=5)
        self.section_distance_var = tk.StringVar(value="50")
        ttk.Label(toolbar, text="Высота между двумя точками, м:").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.section_distance_var, width=8).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Выбрать низ и верх на разрезе", command=self.start_section_calibration).pack(side="left", padx=3)
        ttk.Label(toolbar, text="Сначала щёлкните нижнюю, затем верхнюю отметку.").pack(side="left", padx=10)
        self.section_canvas = tk.Canvas(frame, bg="#ececec", cursor="crosshair")
        self.section_canvas.pack(fill="both", expand=True, padx=6, pady=5)
        self.section_canvas.bind("<Button-1>", self.on_section_click)

    def _build_loads_tab(self):
        frame = self.tabs["4. Грузы"]
        ttk.Label(frame, text="Стандартные стартовые массы необходимо подтвердить или отредактировать. Укажите нестандартное оборудование для кровли отдельной строкой.", wraplength=1000).pack(anchor="w", padx=10, pady=8)
        columns = ("name", "load", "rigging", "length", "width", "height", "lifts")
        self.load_tree = ttk.Treeview(frame, columns=columns, show="headings", height=16)
        labels = ("Груз", "Масса, кг", "Оснастка, кг", "Длина, м", "Ширина, м", "Высота, м", "Подъёмов")
        for col, label in zip(columns, labels):
            self.load_tree.heading(col, text=label)
            self.load_tree.column(col, width=125 if col == "name" else 90)
        self.load_tree.pack(fill="both", expand=True, padx=10, pady=5)
        for load in self.loads:
            self.load_tree.insert("", "end", values=(load.name, load.load_kg, load.rigging_kg, load.length_m, load.width_m, load.height_m, load.lifts))
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
        ttk.Button(frame, text="РАССЧИТАТЬ ДО 3 ВАРИАНТОВ", command=self.run_calculation).pack(pady=8)
        self.results = tk.Text(frame, height=24, wrap="word")
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
            ): var.set(str(value))
            self.priority.set(project.priority); self.screen_possible.set(project.protective_screen_possible); self.commercial_offer.set(project.commercial_offer_present)
            self.site_points=list(project.site.boundary); self.building_points=list(project.site.building); self.restricted_zones=[list(z) for z in project.site.restricted_zones]
            self.unloading_points=list(project.site.unloading_zone); self.storage_zones=[list(z) for z in project.site.storage_zones]; self.work_points=list(project.work_points)
            self.current_zone_points=[]; self.current_storage_points=[]; self.closed_contours={"site","building"}
            if self.unloading_points: self.closed_contours.add("unloading")
            self.m_per_pixel=project.plan_m_per_pixel or None; self.origin_px=(project.plan_origin_x_px,project.plan_origin_y_px) if self.m_per_pixel else None
            self.section_m_per_pixel=project.section_m_per_pixel or None
            self.section_origin_px=(project.section_origin_x_px,project.section_origin_y_px) if self.section_m_per_pixel else None
            self.section_axis=(project.section_axis_dx,project.section_axis_dy)
            self.plan_pdf=project.source_plan_pdf if project.source_plan_pdf and Path(project.source_plan_pdf).is_file() else ""
            self.section_pdf=project.source_section_pdf if project.source_section_pdf and Path(project.source_section_pdf).is_file() else ""
            self.load_tree.delete(*self.load_tree.get_children())
            for load in project.loads: self.load_tree.insert("","end",values=(load.name,load.load_kg,load.rigging_kg,load.length_m,load.width_m,load.height_m,load.lifts))
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
        self.contour_pixels["site"]=draw_polygon(self.site_points,"#111111","draw_site") or []
        self.contour_pixels["building"]=draw_polygon(self.building_points,"#0066cc","draw_building") or []
        self.contour_pixels["unloading"]=draw_polygon(self.unloading_points,"#e67e00","draw_unloading") or []
        for i,zone in enumerate(self.restricted_zones): draw_polygon(zone,"#cc0000",f"draw_restricted_{i}")
        for i,zone in enumerate(self.storage_zones): draw_polygon(zone,"#7a1fa2",f"draw_storage_{i}")
        for i,wp in enumerate(self.work_points,1):
            x,y=self._world_to_canvas(wp.point); self.canvas.create_oval(x-4,y-4,x+4,y+4,fill="#008800",tags="markup"); self.canvas.create_text(x+7,y-7,text=str(i),anchor="w",fill="#006600",tags="markup")

    def _redraw_section_calibration(self):
        if not self.section_origin_px or not self.section_m_per_pixel: return
        p1=self.section_origin_px; distance=float(self.parapet.get())-float(self.pit_bottom.get())
        p2=(p1[0]+self.section_axis[0]*distance/self.section_m_per_pixel,p1[1]+self.section_axis[1]*distance/self.section_m_per_pixel)
        for p in (p1,p2):
            x,y=p[0]*self.section_image_scale,p[1]*self.section_image_scale; self.section_canvas.create_oval(x-4,y-4,x+4,y+4,fill="#7A1FA2",tags="section_markup")
        self.section_canvas.create_line(p1[0]*self.section_image_scale,p1[1]*self.section_image_scale,p2[0]*self.section_image_scale,p2[1]*self.section_image_scale,fill="#7A1FA2",width=2,tags="section_markup")

    def choose_plan(self):
        path = filedialog.askopenfilename(title="Выберите векторный PDF-план", filetypes=[("PDF", "*.pdf")])
        if not path: return
        try:
            inspection = inspect_pdf(path)
            if not inspection.likely_vector:
                messagebox.showerror("Не векторный PDF", "В документе недостаточно векторных элементов. Растровые сканы в первой версии не поддерживаются.")
                return
            self.plan_pdf = path
            self.plan_label.config(text=f"{Path(path).name}; страниц: {inspection.pages}; векторных элементов: {inspection.vector_lines + inspection.vector_rects}")
            self._show_plan()
            self.status.set("План загружен. Выберите две точки с известным расстоянием.")
        except Exception as exc:
            messagebox.showerror("Ошибка PDF", str(exc))

    def choose_section(self):
        path = filedialog.askopenfilename(title="Выберите PDF-разрез", filetypes=[("PDF", "*.pdf")])
        if path:
            self.section_pdf = path
            self.section_label.config(text=Path(path).name)
            self._show_section()
            self.status.set("Разрез загружен. На вкладке «3. Разрез» задайте нижнюю и верхнюю отметки.")

    def _show_plan(self):
        if not self.plan_pdf: return
        image = render_page(self.plan_pdf, 0, 1.5)
        max_w, max_h = 1120, 650
        factor = min(max_w / image.width, max_h / image.height, 1.0)
        self.image_scale = factor
        if factor < 1:
            image = image.resize((int(image.width * factor), int(image.height * factor)))
        self.plan_image = image
        self.plan_photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.plan_photo, anchor="nw", tags="pdf")

    def _show_section(self):
        if not self.section_pdf: return
        image = render_page(self.section_pdf, 0, 1.5)
        factor = min(1120 / image.width, 650 / image.height, 1.0)
        self.section_image_scale = factor
        if factor < 1:
            image = image.resize((int(image.width * factor), int(image.height * factor)))
        self.section_image = image; self.section_photo = ImageTk.PhotoImage(image)
        self.section_canvas.delete("all")
        self.section_canvas.create_image(0, 0, image=self.section_photo, anchor="nw", tags="pdf")

    def start_section_calibration(self):
        if not self.section_pdf:
            messagebox.showwarning("Нет разреза", "Сначала выберите PDF-разрез на вкладке проекта.")
            return
        self.section_calibration_points.clear(); self.section_canvas.delete("section_markup")
        self.status.set("На разрезе укажите нижнюю, затем верхнюю точку с известной разностью отметок.")

    def on_section_click(self, event):
        if not self.section_pdf: return
        point=(event.x/self.section_image_scale,event.y/self.section_image_scale)
        if len(self.section_calibration_points)>=2: self.start_section_calibration()
        self.section_calibration_points.append(point)
        self.section_canvas.create_oval(event.x-4,event.y-4,event.x+4,event.y+4,fill="#7A1FA2",tags="section_markup")
        if len(self.section_calibration_points)==2:
            try:
                p1,p2=self.section_calibration_points; distance=float(self.section_distance_var.get())
                self.section_m_per_pixel=calibration_m_per_pixel(p1,p2,distance); self.section_origin_px=p1
                length=math.hypot(p2[0]-p1[0],p2[1]-p1[1]); self.section_axis=((p2[0]-p1[0])/length,(p2[1]-p1[1])/length)
                self.section_canvas.create_line(p1[0]*self.section_image_scale,p1[1]*self.section_image_scale,p2[0]*self.section_image_scale,p2[1]*self.section_image_scale,fill="#7A1FA2",width=2,tags="section_markup")
                self.status.set(f"Масштаб разреза принят: {self.section_m_per_pixel:.5f} м/пиксель. Высотная схема попадёт в ППРк.")
            except Exception as exc:
                messagebox.showerror("Ошибка масштаба разреза",str(exc)); self.section_calibration_points.clear()

    def set_mode(self, mode):
        if mode != "calibration" and self.m_per_pixel is None:
            messagebox.showwarning("Сначала масштаб", "Сначала выберите две точки масштаба.")
            return
        self.mode = mode
        names = {"calibration":"масштаб", "site":"граница площадки", "building":"контур здания", "restricted":"запретная зона", "workpoint":"точки подачи грузов на здание", "unloading":"зона разгрузки", "storage":"зона складирования"}
        instruction = " Щёлкайте вершины по порядку: линии строятся автоматически, затем нажмите «Замкнуть контур»." if mode in self.contour_pixels else " Щёлкните требуемые точки."
        self.status.set(f"Режим: {names[mode]}.{instruction}")

    def on_canvas_click(self, event):
        if not self.plan_pdf: return
        point_px = (event.x / self.image_scale, event.y / self.image_scale)
        if self.mode == "calibration":
            self.calibration_points.append(point_px)
            self.canvas.create_oval(event.x-4,event.y-4,event.x+4,event.y+4,fill="#ff8800",tags="markup")
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
        if self.mode == "site": self.site_points.append(world); color="#111111"
        elif self.mode == "building": self.building_points.append(world); color="#0066cc"
        elif self.mode == "restricted": self.current_zone_points.append(world); color="#cc0000"
        elif self.mode == "unloading": self.unloading_points.append(world); color="#e67e00"
        elif self.mode == "storage": self.current_storage_points.append(world); color="#7a1fa2"
        else:
            self._add_work_point_dialog(world, (event.x, event.y))
            return
        pixels = self.contour_pixels[self.mode]
        draw_tag = self._current_contour_tag()
        if pixels:
            x0, y0 = pixels[-1]
            self.canvas.create_line(x0, y0, event.x, event.y, fill=color, width=2, tags=("markup", draw_tag))
        pixels.append((event.x, event.y))
        self.canvas.create_oval(event.x-3,event.y-3,event.x+3,event.y+3,fill=color,outline=color,tags=("markup", draw_tag))

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
        colors = {"site":"#111111", "building":"#0066cc", "restricted":"#cc0000", "unloading":"#e67e00", "storage":"#7a1fa2"}
        self.canvas.create_line(*pixels[-1], *pixels[0], fill=colors[self.mode], width=2, tags=("markup", self._current_contour_tag()))
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
        colors = {"site":"#111111", "building":"#0066cc", "restricted":"#cc0000", "unloading":"#e67e00", "storage":"#7a1fa2"}
        color = colors[self.mode]
        for index, (x, y) in enumerate(pixels):
            if index:
                self.canvas.create_line(*pixels[index-1], x, y, fill=color, width=2, tags=("markup", draw_tag))
            self.canvas.create_oval(x-3,y-3,x+3,y+3,fill=color,outline=color,tags=("markup", draw_tag))
        self.status.set(f"Последняя вершина отменена. Осталось: {len(pixels)}.")

    def clear_markup(self):
        self.calibration_points.clear(); self.m_per_pixel=None; self.origin_px=None
        self.site_points.clear(); self.building_points.clear(); self.current_zone_points.clear(); self.restricted_zones.clear(); self.work_points.clear()
        self.unloading_points.clear(); self.current_storage_points.clear(); self.storage_zones.clear()
        self.contour_pixels = {"site": [], "building": [], "restricted": [], "unloading": [], "storage": []}; self.closed_contours.clear()
        self._show_plan(); self.status.set("Разметка очищена. Выберите две точки масштаба.")

    def auto_suggest_boundary(self):
        if not self.plan_pdf or self.m_per_pixel is None:
            messagebox.showwarning("Недостаточно данных", "Загрузите план и задайте масштаб по двум точкам.")
            return
        try:
            x0, y0, x1, y1 = suggest_vector_bounds(self.plan_pdf)
            # PDFium рендерится с scale=1.5; переводим PDF-точки в пиксели исходного рендера.
            points_px = [(x0*1.5,y0*1.5),(x1*1.5,y0*1.5),(x1*1.5,y1*1.5),(x0*1.5,y1*1.5)]
            proposed = [pixel_to_world(point,self.origin_px,self.m_per_pixel) for point in points_px]
            if messagebox.askyesno("Автоматическое предложение", "Предложена рамка по векторным элементам. Использовать её как черновую границу площадки? После этого обязательно проверьте все точки."):
                self.site_points = proposed
                self.contour_pixels["site"] = [(px*self.image_scale,py*self.image_scale) for px,py in points_px]
                self.closed_contours.add("site")
                coords=[]
                for px,py in points_px: coords += [px*self.image_scale,py*self.image_scale]
                self.canvas.create_polygon(*coords,outline="#111111",fill="",width=2,tags="markup")
                self.status.set("Автоматическая граница добавлена как черновик. Проверьте её; при ошибке очистите и нанесите вручную.")
        except Exception as exc:
            messagebox.showerror("Автоматическое предложение не выполнено",str(exc))

    def edit_load(self, new=False):
        selected = self.load_tree.selection()
        values = ("Новый груз",1000,100,1,1,1,10) if new or not selected else self.load_tree.item(selected[0], "values")
        dialog = tk.Toplevel(self); dialog.title("Параметры груза"); dialog.transient(self); dialog.grab_set()
        vars_=[]
        for row,(label,value) in enumerate(zip(("Название","Масса, кг","Оснастка, кг","Длина, м","Ширина, м","Высота, м","Подъёмов"),values)):
            ttk.Label(dialog,text=label).grid(row=row,column=0,padx=5,pady=3,sticky="w"); var=tk.StringVar(value=value); vars_.append(var); ttk.Entry(dialog,textvariable=var).grid(row=row,column=1,padx=5,pady=3)
        def apply():
            try:
                row=(vars_[0].get().strip(),)+tuple(float(v.get()) for v in vars_[1:6])+(int(float(vars_[6].get())),)
                if not row[0] or row[1]<=0 or row[2]<0 or min(row[3:6])<=0 or row[6]<=0: raise ValueError("Проверьте название, массы, габариты и количество подъёмов")
                if new or not selected: self.load_tree.insert("","end",values=row)
                else: self.load_tree.item(selected[0],values=row)
                dialog.destroy(); self.scenarios=[]
            except Exception as exc: messagebox.showerror("Груз не сохранён",str(exc),parent=dialog)
        ttk.Button(dialog,text="Сохранить",command=apply).grid(row=7,column=0,columnspan=2,pady=8)

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
        dialog=tk.Toplevel(self); dialog.title("Точка подачи груза"); dialog.transient(self); dialog.grab_set()
        ttk.Label(dialog,text="Груз").grid(row=0,column=0,sticky="w",padx=8,pady=6)
        load_var=tk.StringVar(value=loads[0].name)
        combo=ttk.Combobox(dialog,textvariable=load_var,values=[x.name for x in loads],state="readonly",width=42)
        combo.grid(row=0,column=1,padx=8,pady=6)
        ttk.Label(dialog,text="Отметка точки подачи, м").grid(row=1,column=0,sticky="w",padx=8,pady=6)
        level_var=tk.StringVar(value=str(float(self.parapet.get())-float(self.pit_bottom.get())))
        ttk.Entry(dialog,textvariable=level_var,width=15).grid(row=1,column=1,sticky="w",padx=8,pady=6)
        def apply():
            try:
                level=float(level_var.get())
                if level<0: raise ValueError("Отметка не может быть отрицательной")
                load_index=combo.current()
                if load_index<0: raise ValueError("Выберите груз")
                self.work_points.append(WorkPoint(world[0],world[1],level,load_index,f"Точка подачи {len(self.work_points)+1}"))
                x,y=canvas_point; self.canvas.create_oval(x-4,y-4,x+4,y+4,fill="#008800",tags="markup")
                self.canvas.create_text(x+7,y-7,text=str(len(self.work_points)),anchor="w",fill="#006600",tags="markup")
                dialog.destroy(); self.status.set(f"Добавлена точка подачи для груза «{loads[load_index].name}».")
            except Exception as exc: messagebox.showerror("Ошибка точки подачи",str(exc),parent=dialog)
        ttk.Button(dialog,text="Добавить",command=apply).grid(row=2,column=0,columnspan=2,pady=8)

    def _collect_loads(self):
        result=[]
        for item in self.load_tree.get_children():
            v=self.load_tree.item(item,"values")
            result.append(Load(v[0],float(v[1]),float(v[2]),float(v[3]),float(v[4]),float(v[5]),int(float(v[6]))))
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
            for load in loads:
                if not load.name.strip() or load.load_kg<=0 or load.rigging_kg<0 or min(load.length_m,load.width_m,load.height_m)<=0 or load.lifts<=0:
                    blockers.append(f"Исправьте параметры груза «{load.name or 'без названия'}»: масса, габариты и количество подъёмов должны быть положительными.")
            for wp in self.work_points:
                if wp.load_index<0 or wp.load_index>=len(loads): blockers.append(f"{wp.name}: назначенный груз удалён; создайте точку подачи заново.")
        except Exception:
            blockers.append("Исправьте числовые значения в таблице грузов.")
        try:
            pit=float(self.pit_bottom.get()); parapet=float(self.parapet.get())
            if parapet<=pit: blockers.append("Отметка верха парапета должна быть выше отметки низа котлована.")
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
        if not self.section_pdf: reminders.append("Загрузите PDF-разрез для высотной схемы.")
        elif self.section_m_per_pixel is None: reminders.append("Откалибруйте разрез по нижней и верхней точкам.")
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
                    sector=(f"; разрешённый сектор {p.allowed_sector_start_deg:.1f}°…{p.allowed_sector_end_deg:.1f}°" if p.allowed_sector_start_deg is not None else "")
                    self.results.insert("end",f"  К{j} {p.model}: X={p.x:.1f}, Y={p.y:.1f}; рабочий вылет до {p.max_radius_m:.1f} м; монтажная стрела L={p.jib_length_m:.1f} м; высота крюка {p.required_hook_height_m:.1f} м; уровень стрелы {(p.jib_level_m or p.required_hook_height_m):.1f} м{sector}\n")
                if s.joint_plan:
                    jp=s.joint_plan
                    self.results.insert("end",f"  СОВМЕСТНАЯ РАБОТА: оси {jp.axis_distance_m:.1f} м; общая зона {jp.overlap_area_m2:.1f} м²; горизонтальный разрыв ≥{jp.working_horizontal_clearance_m:.1f} м; оси стрел разнесены на {jp.vertical_separation_m:.1f} м ({jp.jib_structural_height_m:.1f} м стрела + 1.0 м зазор); защитный габарит башен {jp.tower_protection_radius_m:.1f}+{jp.tower_protection_radius_m:.1f}={jp.combined_tower_envelope_m:.1f} м; приоритет К{jp.priority_crane_index}.\n")
                    self.results.insert("end","  В общей зоне допускается один груз; второй кран ожидает вне зоны. Параметры перед настройкой координатной защиты сверить с паспортами.\n")
                if s.calendar_days is not None: self.results.insert("end",f"  Оценка: {s.calendar_days:.1f} календарных дней\n")
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
            dialog=tk.Toplevel(self); dialog.title("Предпросмотр и состав листов ППРк"); dialog.geometry("1080x720"); dialog.transient(self); dialog.grab_set()
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
