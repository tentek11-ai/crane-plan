# СОЗР и высотно-зависимые опасные зоны — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Цель:** заменить плоский запрет пересечения опасных зон на проверяемую высотно-зависимую модель движения башенного крана, строить безопасные маршруты и выпускать согласованную схему СОЗР с подробной диагностикой.

**Архитектура:** расчёт остаётся локальным и воспроизводимым. Новая типизированная модель зон используется старым оптимизатором, независимым ядром `engine`, протоколом и отчётом. Маршрут ищется графом в полярной сетке, но каждый найденный переход подтверждается точной векторной проверкой. Интерфейс только собирает данные, запускает расчёт по неизменяемому снимку и показывает структурированный результат.

**Технологии:** Python 3, `dataclasses`, `Enum`, `heapq`, Tkinter, ReportLab, `unittest`; без новых сетевых и геометрических зависимостей, чтобы сохранить переносимую офлайн-сборку.

**Спецификация:** `docs/superpowers/specs/2026-10-22-sozr-and-height-aware-restricted-zones-design.md`

## Глобальные ограничения

- Не менять физический смысл высот: сравниваются нижняя отметка груза и нижняя отметка стрелы, а не отметка крюка или вершины стрелы.
- Установка башни запрещена в любом типе зоны, включая её границу и дополнительный горизонтальный запас.
- Ровно `3,0 м` вертикального запаса считается допустимым; меньше `3,0 м` — недопустимым.
- Дискретная сетка служит только для поиска. Принятый маршрут обязан пройти точную проверку отрезков и дуг.
- Не добавлять `shapely` и другие тяжёлые зависимости: разрешённую область представлять техническим диском и набором вычитаемых контуров.
- Не читать Tk-переменные из рабочего потока. Снимок `ProjectInput` формируется в UI-потоке до отправки расчёта.
- Старый файл проекта не перезаписывать при миграции; сохранение выполняется только явной командой пользователя.
- Не ослаблять существующие проверки границы площадки, грузовой характеристики, габарита башни и совместной работы кранов.
- Каждый пункт плана завершается целевыми тестами и отдельным коммитом. Перед завершением задачи запускать также ближайший существующий регрессионный набор.
- Полная проверка Windows-переносимой сборки выполняется из путей без кириллицы либо через временное сопоставление дисков, так как встроенный Tcl/Tk может не загрузиться из кириллического пути.

## Review Focus

При ревью обязательно проверить пять наиболее рискованных классов входных данных; тест на каждый класс добавляется в указанной задаче:

1. Касание границы зоны башней, грузом, радиальным участком или дугой и точное равенство запасу `3,0 м` — задачи 2 и 3.
2. Вогнутый, вырожденный или самопересекающийся контур, а также разрушение контура после буферизации — задачи 1 и 2.
3. Центр разгрузки/склада или точка подачи внутри либо на границе активной зоны — задача 4.
4. Гонка автоперерасчёта, при которой старый расчёт завершается после нового — задача 8.
5. Несколько складов, отсутствие безопасной полной цепочки и необходимость показать причины по каждому складу — задача 4.

---

## Задача 1. Типизированная модель зон и миграция проекта

**Файлы:**

- Изменить: `05_src/crane_plan/models.py`
- Изменить: `05_src/crane_plan/project_io.py`
- Изменить: `06_tests/test_io_pdf_report.py`
- Создать: `06_tests/test_restricted_zone_model.py`

**Интерфейсы:**

- `RestrictedZoneKind(str, Enum)`: `LOAD_PROHIBITED`, `HEIGHT_OBSTACLE`, `FULL_EXCLUSION`.
- `RestrictedZone`: `id`, `name`, `kind`, `polygon`, `height_m`, `horizontal_clearance_m=0.0`, `note=""`, `verified=True`, `source_refs=[]`.
- `WarningAcceptance`: `warning_id`, `input_sha256`, `comment=""`.
- `SiteInput.restricted_zones: list[RestrictedZone]`.
- `ProjectInput.schema_version = 3`, поля `route_angle_step_deg=1.0`, `route_radius_step_m=0.5`, `vertical_clearance_m=3.0`, `warning_acceptances=[]`.
- `load_project(path) -> ProjectInput` мигрирует версии 1–2, но не записывает файл.

- [ ] Написать тесты сериализации всех типов зон, значений по умолчанию и миграции старого `list[list[Point]]` в `FULL_EXCLUSION` с `verified=False`.
- [ ] Добавить тесты отклонения полигона с менее чем тремя уникальными вершинами, отрицательной высоты и отрицательного горизонтального запаса.
- [ ] Запустить `python -m unittest 06_tests.test_restricted_zone_model 06_tests.test_io_pdf_report` и подтвердить ожидаемое падение.
- [ ] Реализовать модель и явную миграцию схемы 1/2 → 3; высоту старой зоны принимать `0.0`, но сохранять `verified=False`, чтобы новый расчёт СОЗР блокировался до проверки пользователем.
- [ ] Повторить тесты и выполнить `git commit -m "feat: add typed restricted zones and project migration"`.

## Задача 2. Правила высоты, буферизация и точная геометрия

**Файлы:**

- Создать: `05_src/crane_plan/restricted_zones.py`
- Изменить: `05_src/crane_plan/geometry.py`
- Создать: `06_tests/test_restricted_zone_geometry.py`

**Интерфейсы:**

- `validate_zone(zone: RestrictedZone) -> list[str]`.
- `buffered_zone_polygon(zone: RestrictedZone) -> list[Point]`.
- `tower_is_allowed(zone, tower_center, tower_protection_radius_m) -> bool`.
- `load_may_overfly(zone, load_bottom_m, clearance_m) -> bool`.
- `jib_may_overfly(zone, jib_bottom_m, clearance_m) -> bool`.
- `segment_circle_intersections(a, b, center, radius) -> list[Point]`.
- `segment_intersects_polygon_exact(a, b, polygon, boundary_is_collision=True) -> bool`.
- `arc_intersects_polygon_exact(center, radius, start_deg, end_deg, clockwise, polygon, boundary_is_collision=True) -> bool`.

- [ ] Написать таблицу тестов для трёх типов зон при запасе `2.999`, `3.000` и `3.001 м`, отдельно для груза и стрелы.
- [ ] Добавить тесты касания границы, вогнутого контура, самопересечения, вырожденного контура и недопустимого результата буферизации.
- [ ] Запустить `python -m unittest 06_tests.test_restricted_zone_geometry` и подтвердить ожидаемое падение.
- [ ] Реализовать правила зон и аналитические пересечения отрезок–окружность/дуга–ребро; использовать единый именованный допуск только для ошибок вычисления, не превращая его в дополнительный запас безопасности.
- [ ] Запустить новые тесты и `06_tests.test_geometry_catalog_optimizer`, затем выполнить `git commit -m "feat: add exact height-aware zone geometry"`.

## Задача 3. Полярный планировщик маршрута и точная перепроверка

**Файлы:**

- Создать: `05_src/crane_plan/route_planner.py`
- Изменить: `05_src/crane_plan/models.py`
- Создать: `06_tests/test_route_planner.py`

**Интерфейсы:**

- `RoutePlannerSettings(angle_step_deg=1.0, radius_step_m=0.5, vertical_clearance_m=3.0)`.
- `RouteFailureCode(str, Enum)` со стабильными кодами: `SOURCE_BLOCKED`, `DESTINATION_BLOCKED`, `HEIGHT_EXCEEDED`, `CAPACITY_EXCEEDED`, `INNER_BYPASS_BLOCKED`, `OUTER_BYPASS_BLOCKED`, `SITE_BOUNDARY`, `SECOND_CRANE_CONFLICT`, `NO_PATH`, `EXACT_RECHECK_FAILED`.
- `RouteWaypoint(x, y, hook_height_m, movement)`.
- `RouteAlternative(kind, accepted, min_clearance_m, path_length_m, failures)`.
- `LiftRoute(operation_id, waypoints, transport_hook_height_m, alternatives, input_sha256)`.
- `RoutePlanResult(route: LiftRoute | None, failures: list[RouteFailure])`.
- `plan_lift_route(crane_point, jib_length_m, jib_bottom_m, max_hook_height_m, load, source, destination, project, capacity_at_radius, settings) -> RoutePlanResult`.

- [ ] Написать тесты прямой подачи, внутреннего обхода, внешнего обхода, прохода сверху, комбинированного обхода и сохранения доступной области за локальным препятствием.
- [ ] Добавить тесты касания зоны дугой/отрезком, отказа точной перепроверки и равенства минимальному вертикальному запасу.
- [ ] Добавить тест выбора: сначала максимальный минимальный запас, затем минимальная длина пути.
- [ ] Запустить `python -m unittest 06_tests.test_route_planner` и подтвердить ожидаемое падение.
- [ ] Реализовать Dijkstra/A* по узлам `(angle_index, radius_index, height_index)` с рёбрами только «тележка», «поворот», «подъём/опускание»; каждое принятое ребро повторно проверить точной геометрией.
- [ ] Запустить тесты и выполнить `git commit -m "feat: add exact-checked polar lift route planner"`.

## Задача 4. Логистические цепочки и интеграция с оптимизатором

**Файлы:**

- Изменить: `05_src/crane_plan/optimizer.py`
- Изменить: `05_src/crane_plan/models.py`
- Изменить: `05_src/crane_plan/engine/gui_adapter.py`
- Создать: `06_tests/test_optimizer_routes.py`
- Изменить: `06_tests/test_engine_gui_adapter.py`

**Интерфейсы:**

- `LogisticsLeg(operation_id, source_kind, source_id, destination_kind, destination_id)`.
- `build_logistics_chains(site: SiteInput, work_point: WorkPoint) -> list[list[LogisticsLeg]]`.
- `ScenarioResult.routes: list[LiftRoute]` и `ScenarioResult.route_failures: list[RouteFailure]`.
- `evaluate_logistics_chain(placement, chain, project, settings) -> ChainPlanResult`.
- `diagnose_no_solution(...)` использует стабильные коды и числовые параметры отказа, а не строку «не найден безопасный маршрут».

- [ ] Написать тесты цепочки разгрузка → склад → точка и прямой цепочки разгрузка → точка при отсутствии склада.
- [ ] Добавить риск-тесты: центр исходной/конечной зоны внутри или на границе запрета; несколько складов, из которых безопасен только один; ни один склад не даёт полной цепочки.
- [ ] Запустить `python -m unittest 06_tests.test_optimizer_routes 06_tests.test_engine_gui_adapter` и подтвердить ожидаемое падение.
- [ ] Заменить `_ray_is_clear`/`_route_is_safe` в принятии решения на новый планировщик; сохранить быстрые проверки только как безопасные предварительные фильтры.
- [ ] Убрать ошибку адаптера о неоднозначности нескольких складов: формировать кандидаты и сохранять выбранный склад с причинами отклонения остальных.
- [ ] Запустить тесты оптимизатора и выполнить `git commit -m "feat: integrate planned logistics routes into optimization"`.

## Задача 5. Геометрия СОЗР и стабильная нумерация точек

**Файлы:**

- Создать: `05_src/crane_plan/sozr.py`
- Изменить: `05_src/crane_plan/models.py`
- Создать: `06_tests/test_sozr.py`

**Интерфейсы:**

- `SOZRRestrictionClass(str, Enum)`: `PERMANENT`, `CONDITIONAL`.
- `SOZRPoint(label, x, y, bearing_deg, radius_m, restriction_class, zone_id, zone_height_m, condition)`.
- `SOZRPlan(crane_id, technical_radius_m, permanent_contours, conditional_contours, points, critical_routes, algorithm_version)`.
- `bearing_from_north_clockwise(origin, point) -> float`.
- `build_sozr_plan(crane_id, crane_point, technical_radius_m, zones, routes, project) -> SOZRPlan`.

- [ ] Написать тесты точек в вершинах, пересечениях зоны с окружностью и переходах постоянного ограничения в условное.
- [ ] Добавить тест стабильной сортировки по часовой стрелке от севера, детерминированного разрешения одинаковых углов и независимой нумерации `К1-*`, `К2-*`.
- [ ] Запустить `python -m unittest 06_tests.test_sozr` и подтвердить ожидаемое падение.
- [ ] Реализовать представление «технический диск + вычитаемые контуры», не выполняя небезопасное полигональное упрощение.
- [ ] Запустить тесты и выполнить `git commit -m "feat: build deterministic SOZR geometry and points"`.

## Задача 6. Независимое ядро v3, верификатор и протокол

**Файлы:**

- Изменить: `05_src/crane_plan/engine/domain.py`
- Изменить: `05_src/crane_plan/engine/verification.py`
- Изменить: `05_src/crane_plan/engine/protocol.py`
- Изменить: `06_tests/test_engine_domain.py`
- Изменить: `06_tests/test_engine_verification.py`
- Изменить: `06_tests/test_engine_protocol.py`

**Интерфейсы:**

- `RestrictedZoneV3` повторяет расчётно значимые поля `RestrictedZone`.
- `OperationRouteV3` хранит `operation_id`, `placement_id`, `transport_hook_height_m`, `waypoints`, `source_id`, `destination_id`.
- `ProjectSolutionV3.operation_routes: tuple[OperationRouteV3, ...]`.
- `verify_solution(project, solution) -> VerificationReport` независимо проверяет каждое ребро маршрута, грузоподъёмность, высоту и активность зоны.
- Протокол содержит исходные и буферизованные контуры, настройки сетки, версию алгоритма, маршруты, отклонённые альтернативы и SHA-256 входа.

- [ ] Написать тест, в котором дискретные узлы безопасны, но дуга между ними пересекает зону: независимый верификатор обязан отклонить решение.
- [ ] Добавить тесты полноты/детерминированности протокола и изменения хеша при изменении высоты зоны или шага сетки.
- [ ] Запустить три тестовых модуля ядра и подтвердить ожидаемое падение.
- [ ] Реализовать преобразование legacy-моделей в v3 и независимую точную проверку без вызова внутренней функции поиска маршрута.
- [ ] Запустить тесты и выполнить `git commit -m "feat: verify and protocol height-aware operation routes"`.

## Задача 7. Редактор опасных зон в интерфейсе

**Файлы:**

- Создать: `05_src/crane_plan/zone_editor.py`
- Изменить: `05_src/crane_plan/app.py`
- Создать: `06_tests/test_zone_editor.py`
- Изменить: `06_tests/test_app_engine_integration.py`

**Интерфейсы:**

- `ZoneEditorResult(zone: RestrictedZone | None, cancelled: bool)`.
- `edit_restricted_zone(parent, polygon, initial=None) -> ZoneEditorResult`.
- Карточка содержит имя, тип, высоту от `0`, горизонтальный запас и примечание.
- Таблица рядом с планом содержит имя, тип и высоту; выбор строки вызывает `select_restricted_zone(zone_id)` и подсвечивает контур.

- [ ] Написать unit-тесты преобразования значений формы и ошибок обязательных полей без запуска полного GUI.
- [ ] Добавить интеграционный тест: замыкание контура открывает карточку, отмена не добавляет зону, сохранение добавляет типизированную зону.
- [ ] Запустить тесты и подтвердить ожидаемое падение.
- [ ] Реализовать карточку и таблицу; рисовать полный запрет сплошным красным, запрет груза красной штриховкой, высотное препятствие оранжевой штриховкой с подписью высоты.
- [ ] Запустить UI-тесты и выполнить `git commit -m "feat: add typed restricted zone editor"`.

## Задача 8. Автоперерасчёт, явные состояния и принятие предупреждений

**Файлы:**

- Создать: `05_src/crane_plan/recalculation.py`
- Изменить: `05_src/crane_plan/app.py`
- Изменить: `05_src/crane_plan/models.py`
- Создать: `06_tests/test_recalculation.py`
- Создать: `06_tests/test_warning_acceptance.py`

**Интерфейсы:**

- `CalculationState(str, Enum)`: `MISSING_INPUT`, `STALE`, `RUNNING`, `CURRENT`, `NO_SOLUTION`, `EXPERT_REVIEW`.
- `CalculationTicket(revision, input_sha256)`.
- `RecalculationCoordinator(snapshot_factory, calculate, schedule, cancel_schedule, submit, on_state, on_result, delay_ms=600)`.
- `mark_changed()`, `recalculate_now()`, `accept_completed(ticket, result) -> bool`, `shutdown()`.
- `accept_warning(warning_id, input_sha256, comment="")`; принятие разрешено только для `severity="warning"`.

- [ ] Написать тест debounce после изменения данных и немедленного запуска кнопкой «Пересчитать сейчас».
- [ ] Добавить риск-тест гонки: результат ревизии 1 завершается после ревизии 2 и не может изменить UI или сохранённый результат.
- [ ] Написать тесты запрета игнорирования блокера, отмены принятия после изменения хеша и отсутствия пустого комментария в публикуемых данных.
- [ ] Запустить новые тесты и подтвердить ожидаемое падение.
- [ ] Реализовать снимок проекта в UI-потоке, расчёт в одном рабочем исполнителе и применение результата только при совпадении ревизии и хеша.
- [ ] Добавить строку состояния, список недостающих полей, кнопку «Пересчитать сейчас» и действие «Игнорировать предупреждение» с необязательным комментарием.
- [ ] Запустить тесты и выполнить `git commit -m "feat: add safe automatic recalculation and warning acceptance"`.

## Задача 9. Отображение маршрутов и СОЗР на плане

**Файлы:**

- Изменить: `05_src/crane_plan/app.py`
- Создать: `05_src/crane_plan/sozr_canvas.py`
- Создать: `06_tests/test_sozr_canvas.py`

**Интерфейсы:**

- `SOZRCanvasStyle` задаёт цвета и толщины, но не геометрию.
- `build_sozr_canvas_primitives(plan: SOZRPlan, transform) -> list[CanvasPrimitive]`.
- Примитивы: полный технический круг, голубая допустимая область, красные постоянные вырезы, оранжевые условные вырезы, стрелки маршрутов, точки и подписи.

- [ ] Написать тест снимка списка примитивов для одного и двух кранов; проверять координаты, слои, цвета и подписи, а не пиксели Tk.
- [ ] Запустить тест и подтвердить ожидаемое падение.
- [ ] Реализовать чистое построение примитивов и тонкий адаптер к Canvas, чтобы масштабирование/панорамирование применяло один `transform` ко всей разметке.
- [ ] Проверить, что полная окружность остаётся пунктирной, а вырезы не уничтожают область за препятствием.
- [ ] Запустить тесты и выполнить `git commit -m "feat: render SOZR routes and restriction sectors on plan"`.

## Задача 10. Листы СОЗР и пояснительная записка ППРк

**Файлы:**

- Создать: `05_src/crane_plan/sozr_report.py`
- Изменить: `05_src/crane_plan/report.py`
- Изменить: `06_tests/test_io_pdf_report.py`
- Создать: `06_tests/test_sozr_report.py`

**Интерфейсы:**

- `draw_sozr_sheet(canvas, project, placement, sozr_plan, sheet_number) -> None`.
- `build_sozr_table_rows(plan) -> list[list[str]]` с колонками: точка, X, Y, угол, вылет, тип, высота зоны, условие.
- `build_route_explanation(result) -> list[str]` публикует выбранные цепочки, отказанные альтернативы и принятия предупреждений; пустые комментарии пропускает.

- [ ] Написать тест таблицы, обязательной оговорки об экспертном переносе настроек в прибор и публикации числовой причины отказа.
- [ ] Добавить тест, что пустой комментарий отсутствует в PDF-тексте, а непустой присутствует рядом с принятым предупреждением.
- [ ] Запустить тесты и подтвердить ожидаемое падение.
- [ ] Реализовать отдельный лист СОЗР на каждый кран и раздел пояснительной записки; не перегружать основной план всеми маршрутами.
- [ ] Извлечь текст созданного PDF через `pdfplumber` и проверить ключевые фразы.
- [ ] Выполнить `git commit -m "feat: publish SOZR sheets and route diagnostics in PPRk"`.

## Задача 11. Совместная работа двух кранов

**Файлы:**

- Изменить: `05_src/crane_plan/route_planner.py`
- Изменить: `05_src/crane_plan/optimizer.py`
- Изменить: `05_src/crane_plan/engine/verification.py`
- Изменить: `06_tests/test_route_planner.py`
- Изменить: `06_tests/test_engine_verification.py`

**Интерфейсы:**

- `OtherCraneConstraint(crane_id, tower_center, tower_radius_m, jib_level_m, jib_height_m, routes, permitted_sectors)`.
- `plan_lift_route(..., other_cranes: Sequence[OtherCraneConstraint] = ())`.
- Конфликт классифицируется как башня–стрела, стрела–стрела или груз–стрела и отражается кодом `SECOND_CRANE_CONFLICT` с идентификатором крана.

- [ ] Написать тесты разведённых по высоте стрел, укороченной нижней стрелы с шагом 5 м и запрета пересечения при недостаточном вертикальном разрыве.
- [ ] Добавить тест, где маршрут существует только после ограничения сектора одного из кранов.
- [ ] Запустить целевые тесты и подтвердить ожидаемое падение.
- [ ] Передавать ограничения совместной работы в проверку состояния/ребра и независимый верификатор; не заменять ими существующий график совместной работы.
- [ ] Запустить тесты и выполнить `git commit -m "feat: account for two-crane conflicts in route planning"`.

## Задача 12. Сквозная приёмка, документация и переносимая сборка

**Файлы:**

- Создать: `06_tests/test_sozr_end_to_end.py`
- Изменить: `README.md`
- Изменить: `CHANGELOG.md` (если файл существует; иначе создать)
- Изменить: файл версии/метаданных сборки, найденный по `rg "version|__version__" 05_src build* *.spec`.

**Интерфейсы и сценарий:**

- Сквозной fixture воспроизводит исходную ошибку «Точка подачи 1: не найден безопасный маршрут», содержит высотное препятствие, альтернативные склады и минимум один найденный обход.
- Результат обязан содержать маршрут, СОЗР, протокол, PDF и одинаковые идентификаторы операций во всех артефактах.

- [ ] Написать сквозной тест безопасного обхода и отдельный тест доказанного отсутствия маршрута с числовой диагностикой всех альтернатив.
- [ ] Добавить property-style цикл по набору маршрутов: ни один принятый радиальный участок или дуга не пересекает активный запрещённый объём после точной проверки.
- [ ] Запустить все тесты: `python -m unittest discover -s 06_tests -p "test_*.py"`.
- [ ] Собрать переносимую папку штатным скриптом проекта и запустить smoke-тест из пути без кириллицы; проверить создание/открытие проекта, расчёт и PDF без интернета.
- [ ] Визуально проверить минимум три PDF: одна высотная зона, полный запрет, два крана. Сверить точки на схеме с таблицей и текстом протокола.
- [ ] Обновить README/CHANGELOG: смысл типов зон, оговорка о графическом характере СОЗР, параметры сетки, миграция старых проектов и ограничения метода.
- [ ] Выполнить `git status --short`, убедиться, что в коммит не попали пользовательские ППРк, статьи и каталоги, затем `git commit -m "release: complete height-aware SOZR planning"`.

## Итоговая проверка перед выпуском

- [ ] Все 18 испытаний из утверждённой спецификации имеют автоматический тест или документированный ручной сценарий.
- [ ] В репозитории нет новых необязательных зависимостей и сетевых вызовов.
- [ ] Старые проекты открываются, но непроверенные зоны блокируют расчёт СОЗР до ввода высоты.
- [ ] Причина каждого отказа содержит операцию, конкретную зону/ограничение и числовые значения.
- [ ] Графика Canvas, таблица СОЗР, протокол и PDF построены из одного `SOZRPlan`, а не из четырёх независимых расчётов.
- [ ] Устаревший результат никогда не отмечается актуальным и не попадает в отчёт.
- [ ] Блокирующее нарушение нельзя игнорировать; принятое предупреждение остаётся в протоколе.
- [ ] Выполнен `superpowers:requesting-code-review`, затем замечания обработаны через `superpowers:receiving-code-review`.
- [ ] Перед утверждением завершения выполнен `superpowers:verification-before-completion` с сохранёнными командами и результатами проверки.
