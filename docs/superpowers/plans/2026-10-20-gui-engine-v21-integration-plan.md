# GUI Integration with Calculation Engine 2.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подключить независимую проверку ядром 2.1 к существующему поиску вариантов GUI и разрешать выпуск предварительного ППРк только для выбранного проверенного однокранового варианта Liebherr 130 EC-B 6.

**Architecture:** Существующий `optimize()` остаётся генератором до трёх `ScenarioResult`; новый чистый адаптер преобразует каждый сценарий в модели V3, а отдельный интеграционный сервис запускает `run_engine_v21()` и применяет политику выпуска. GUI хранит проверки параллельно сценариям, показывает все результаты, но передаёт в итоговый PDF и JSON-протокол только выбранный вариант.

**Tech Stack:** Python 3.11+, Tkinter, dataclasses, ReportLab, pypdf, стандартный `unittest`, существующие модули `crane_plan.engine`.

**Spec:** `docs/superpowers/specs/2026-10-20-gui-engine-v21-integration-design.md`

## Global Constraints

- Не заменять текущий алгоритм поиска координат и не изменять `ScenarioResult` динамическими полями.
- На первом этапе ядром 2.1 проверяется только один кран; двухкрановые варианты остаются доступными для просмотра, но требуют экспертной проверки.
- Единственная базовая конфигурация V3: `LIEBHERR-130-ECB-6-60-V3`; сопоставление старого ID: `LIEBHERR-130-ECB-6-60`.
- Не делать скрытых предположений о ближайшей складской зоне и не создавать фиктивных нормативных или паспортных ссылок.
- Неподдерживаемая конфигурация, неоднозначная логистика, пристёжки и исключение ядра никогда не дают статус `VERIFIED`.
- Старые `project.json` схемы 1 и 2 должны загружаться без миграции файла; новое поле подтверждения по умолчанию равно `False`.
- Предпросмотр доступен для всех статусов; выпуск разрешён только для `VERIFIED` и `VERIFIED_WITH_CONDITIONS`.
- Итоговый ППРк содержит один выбранный сценарий; сравнительный вывод GUI сохраняет все найденные сценарии.
- `reports/calculation_protocol_v21.json` записывается атомарно.
- Все пользовательские причины показываются по-русски, а технические коды сохраняются в сериализованных результатах.

## Review Focus

- Несколько складских зон без явного назначения должны давать `LOGISTICS_SOURCE_AMBIGUOUS`, а не неявно выбирать ближайшую зону — тест в Task 2.
- Укороченная стрела должна ограничивать геометрический вылет, использовать консервативную 60-метровую кривую и всегда печатать условие применения — тесты в Tasks 2 и 3.
- Наличие защитного экрана должно сохранять условный статус и условия в итоговом PDF, а не повышать вариант до безусловно проверенного — тесты в Tasks 3 и 5.
- Пристёжки или высота выше свободностоящей должны оставаться экспертным случаем даже при положительных проверках грузоподъёмности — тест в Task 3.
- После редактирования груза или повторного расчёта нельзя выпустить ранее выбранный устаревший вариант — тесты в Tasks 1 и 5.

---

### Task 1: Подтверждение грузов и инвалидирование результатов

**Files:**
- Modify: `05_src/crane_plan/models.py`
- Modify: `05_src/crane_plan/app.py`
- Modify: `06_tests/test_io_pdf_report.py`
- Create: `06_tests/test_app_engine_integration.py`

**Interfaces:**
- Consumes: существующие `ProjectInput.to_dict()`, `CranePlanApp.edit_load()` и `CranePlanApp.delete_load()`.
- Produces: `ProjectInput.loads_verified: bool = False`; `CranePlanApp._invalidate_load_confirmation(self) -> None`; GUI-переменная `self.loads_verified`; параллельное состояние `self.scenario_verifications: list[ScenarioVerificationV21]` и `self.selected_release_index: int | None`.

- [ ] **Step 1: Написать падающие тесты модели и обратной совместимости**

  В `06_tests/test_io_pdf_report.py` добавить проверки:

  - новый `ProjectInput` имеет `loads_verified is False`;
  - `to_dict()` сохраняет `loads_verified=True`;
  - старый JSON без поля загружается с `loads_verified is False`;
  - новый JSON с полем загружается с `loads_verified is True`.

- [ ] **Step 2: Запустить тесты модели и подтвердить RED**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_io_pdf_report -v`

  Expected: FAIL из-за отсутствующего поля `loads_verified`.

- [ ] **Step 3: Добавить поле в `ProjectInput`**

  Добавить в `05_src/crane_plan/models.py` поле `loads_verified: bool = False`, не повышая `schema_version` и не меняя существующие обязательные аргументы. Убедиться, что фильтрация `ProjectInput.__dataclass_fields__` в `load_project()` сохраняет обратную совместимость.

- [ ] **Step 4: Запустить тесты модели и подтвердить GREEN**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_io_pdf_report -v`

  Expected: PASS.

- [ ] **Step 5: Написать падающие тесты инвалидирования GUI-состояния**

  В `06_tests/test_app_engine_integration.py` вызвать метод как чистую операцию над объектом-заглушкой с `loads_verified.set`, `scenarios`, `scenario_verifications` и `selected_release_index`. Проверить, что `_invalidate_load_confirmation()`:

  - устанавливает подтверждение в `False`;
  - очищает оба списка;
  - устанавливает выбранный индекс в `None`.

  Добавить регрессионные проверки, что успешные ветки `edit_load()` и `delete_load()` вызывают этот метод; отмена диалога ничего не инвалидирует.

- [ ] **Step 6: Запустить GUI-тест и подтвердить RED**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_app_engine_integration -v`

  Expected: FAIL с отсутствующим `_invalidate_load_confirmation`.

- [ ] **Step 7: Реализовать состояние и единый сброс**

  В `CranePlanApp`:

  - создать `self.loads_verified = tk.BooleanVar(value=False)` и флажок «Массы грузов и оснастки сверены с проектными документами» на вкладке грузов;
  - инициализировать `self.scenario_verifications = []` и `self.selected_release_index = None`;
  - реализовать `_invalidate_load_confirmation(self) -> None`;
  - вызывать его только после фактического изменения/удаления груза;
  - переносить значение между `_project()` и `open_project()`.

- [ ] **Step 8: Запустить целевые тесты и подтвердить GREEN**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_io_pdf_report 06_tests.test_app_engine_integration -v`

  Expected: PASS.

- [ ] **Step 9: Зафиксировать изменение**

  ```powershell
  git add 05_src/crane_plan/models.py 05_src/crane_plan/app.py 06_tests/test_io_pdf_report.py 06_tests/test_app_engine_integration.py
  git commit -m "feat: track verified project loads"
  ```

### Task 2: Чистый адаптер GUI-моделей к V3

**Files:**
- Create: `05_src/crane_plan/engine/gui_adapter.py`
- Modify: `05_src/crane_plan/engine/__init__.py`
- Create: `06_tests/test_engine_gui_adapter.py`

**Interfaces:**
- Consumes: `ProjectInput`, `ScenarioResult`, `CraneConfigurationV3`, модели из `engine.domain`, `geometry.polygon_centroid()`.
- Produces:
  - `AdapterIssue(code: str, message: str)`;
  - `AdaptedScenarioV21(project: ProjectV3 | None, catalog: tuple[CraneConfigurationV3, ...], solution: ProjectSolutionV3 | None, issues: tuple[AdapterIssue, ...], conditional_messages: tuple[str, ...] = ())`;
  - `adapt_scenario_v21(project: ProjectInput, scenario: ScenarioResult, catalog: tuple[CraneConfigurationV3, ...], *, scenario_index: int) -> AdaptedScenarioV21`.

- [ ] **Step 1: Написать падающий тест полного преобразования**

  В `06_tests/test_engine_gui_adapter.py` собрать минимальный проект с одной складской зоной, одной точкой подачи, подтверждённым грузом и сценарием `LIEBHERR-130-ECB-6-60`. Проверить:

  - этап имеет ID `MAIN_STAGE`;
  - монтажный горизонт этапа равен максимальной `WorkPoint.level_m`;
  - граница площадки, контур здания, запретные зоны и минимальное/максимальное расстояния установки перенесены без потерь;
  - решение содержит размещение `SCENARIO-1-CRANE-1` и конфигурацию `LIEBHERR-130-ECB-6-60-V3`;
  - операция имеет стабильный ID `OP-W1-L1`, источник — центроид склада, назначение — координаты/высота рабочей точки;
  - операция сохраняет `Load.lifts`, массу с оснасткой и габариты отредактированного груза;
  - масса имеет `SourceKind.PROJECT`, а высота строповки 1,5 м остаётся явно помеченным `ASSUMPTION`;
  - `issues == ()`.

- [ ] **Step 2: Запустить один тест и подтвердить RED**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_engine_gui_adapter.GuiAdapterTests.test_adapts_verified_single_crane_scenario -v`

  Expected: ERROR с отсутствующим модулем `engine.gui_adapter`.

- [ ] **Step 3: Реализовать каркас адаптера и базовый однокрановый путь**

  Создать неизменяемые dataclass-модели и `adapt_scenario_v21(...)`. Переносить всю геометрию площадки и ограничения расстояния, формировать один `ConstructionStage(id="MAIN_STAGE")` с максимальным монтажным горизонтом, операции из активных грузов/точек и один `ProjectSolutionV3`. Возвращать структурированную проблему вместо исключения, если обязательная часть преобразования отсутствует.

- [ ] **Step 4: Запустить базовый тест и подтвердить GREEN**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_engine_gui_adapter.GuiAdapterTests.test_adapts_verified_single_crane_scenario -v`

  Expected: PASS.

- [ ] **Step 5: Добавить падающие тесты логистики и назначения грузов**

  Добавить отдельные тесты:

  - ровно один склад использует его центроид;
  - без склада используется центроид зоны разгрузки;
  - несколько складов дают только `LOGISTICS_SOURCE_AMBIGUOUS` и не выбирают источник;
  - отсутствие обеих зон даёт `LOGISTICS_SOURCE_REQUIRED`;
  - активный груз без собственной точки создаёт операции на всех существующих точках;
  - неактивный груз не создаёт операций.

- [ ] **Step 6: Добавить падающие тесты конфигураций и границ этапа**

  Проверить:

  - разрешённая укороченная стрела получает стабильный ID `LIEBHERR-130-ECB-6-60-V3@JIB-<длина>M`, фактический `jib_length_m`, неизменённую консервативную кривую и условное сообщение;
  - неизвестный кран даёт `CONFIGURATION_NOT_IN_V3_CATALOG`;
  - два размещения дают `MULTI_CRANE_NOT_SUPPORTED`;
  - пристёжки или высота выше свободностоящей дают `TIE_INS_NOT_VERIFIED`;
  - защитный экран переносится как условие `PROTECTIVE_SCREEN`.

- [ ] **Step 7: Реализовать правила логистики, грузов и конфигураций**

  Источник выбирать только по правилам спецификации. Для укороченной стрелы использовать `dataclasses.replace()` базовой записи, менять только ID и `jib_length_m`, не интерполировать новую паспортную кривую. Для неподтверждённых масс использовать `SourceKind.ASSUMPTION`; для подтверждённых — `SourceKind.PROJECT` с сообщением о происхождении библиотечного значения.

- [ ] **Step 8: Запустить весь тест адаптера**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_engine_gui_adapter -v`

  Expected: PASS; не менее 12 тестов.

- [ ] **Step 9: Экспортировать публичные интерфейсы и зафиксировать изменение**

  Добавить `AdapterIssue`, `AdaptedScenarioV21` и `adapt_scenario_v21` в `engine.__init__.__all__`.

  ```powershell
  git add 05_src/crane_plan/engine/gui_adapter.py 05_src/crane_plan/engine/__init__.py 06_tests/test_engine_gui_adapter.py
  git commit -m "feat: adapt GUI scenarios to engine v3"
  ```

### Task 3: Интеграционный сервис, статусы и политика выпуска

**Files:**
- Create: `05_src/crane_plan/engine/integration.py`
- Modify: `05_src/crane_plan/engine/__init__.py`
- Create: `06_tests/test_engine_integration.py`

**Interfaces:**
- Consumes: `adapt_scenario_v21(...)`, `EngineRequestV21`, `run_engine_v21()`, `VerificationStatus`, `CalculationProtocolV3`.
- Produces:
  - `IntegrationStatus(StrEnum)` со значениями `VERIFIED`, `VERIFIED_WITH_CONDITIONS`, `EXPERT_REVIEW_REQUIRED`, `REJECTED`;
  - `ScenarioVerificationV21(scenario_index: int, status: IntegrationStatus, release_allowed: bool, messages: tuple[str, ...], engine_result: EngineResultV21 | None, protocol: CalculationProtocolV3 | None)` и `to_dict(self) -> dict[str, object]`;
  - `verify_scenario_v21(project: ProjectInput, scenario: ScenarioResult, catalog: tuple[CraneConfigurationV3, ...], *, scenario_index: int, run_id: str, created_at: str) -> ScenarioVerificationV21`;
  - `verify_scenarios_v21(project: ProjectInput, scenarios: list[ScenarioResult], catalog: tuple[CraneConfigurationV3, ...], *, run_id: str, created_at: str) -> tuple[ScenarioVerificationV21, ...]`;
  - `default_release_index(results: Sequence[ScenarioVerificationV21]) -> int | None`;
  - `release_blockers(results: Sequence[ScenarioVerificationV21], selected_index: int | None) -> tuple[str, ...]`;
  - `scenario_for_report(scenario: ScenarioResult, verification: ScenarioVerificationV21) -> ScenarioResult`.

- [ ] **Step 1: Написать падающие тесты таблицы статусов**

  Реальными моделями из каталога проверить:

  - полный допустимый вариант с подтверждёнными массами → `VERIFIED`, `release_allowed=True`;
  - те же данные без подтверждения → `EXPERT_REVIEW_REQUIRED`;
  - укороченная стрела → `VERIFIED_WITH_CONDITIONS` с текстом метода;
  - недостаточная грузоподъёмность → `REJECTED` с фактической массой/доступной грузоподъёмностью;
  - недостаточная свободностоящая высота → `REJECTED` с требуемой/доступной высотой;
  - пристёжка или превышение свободностоящей высоты → `EXPERT_REVIEW_REQUIRED` независимо от остальных успешных проверок;
  - защитный экран → `VERIFIED_WITH_CONDITIONS`, условие сохранено.

- [ ] **Step 2: Запустить тесты статусов и подтвердить RED**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_engine_integration -v`

  Expected: ERROR с отсутствующим модулем `engine.integration`.

- [ ] **Step 3: Реализовать одиночную проверку и русский перевод причин**

  `verify_scenario_v21()` сначала применяет адаптер, затем ядро. Правила приоритета:

  1. `VerificationStatus.INVALID` → `REJECTED`.
  2. Любая проблема полноты адаптации, неподтверждённые массы, пристёжки или исключение ядра → `EXPERT_REVIEW_REQUIRED`.
  3. `VALID_WITH_CONDITIONS` либо производная укороченная конфигурация → `VERIFIED_WITH_CONDITIONS`.
  4. Иначе `VALID` → `VERIFIED`.

  В `messages` хранить русский текст вместе с кодом (`"КОД: пояснение"`). Для измерений грузоподъёмности и высоты использовать значения из `VerificationReport`, не пересчитывать их в GUI.

- [ ] **Step 4: Реализовать пакетную изоляцию ошибок**

  `verify_scenarios_v21()` оборачивает каждый сценарий отдельно: исключение одного возвращает для него `EXPERT_REVIEW_REQUIRED` с диагностическим сообщением и не прерывает остальные проверки.

- [ ] **Step 5: Добавить и пройти тесты отказоустойчивости и хешей**

  Добавить проверки:

  - исключение адаптера/ядра в первом сценарии не мешает второму;
  - неизвестный кран сохраняет код `CONFIGURATION_NOT_IN_V3_CATALOG`;
  - одинаковые входы при разных `run_id`/`created_at` дают одинаковые `input_sha256` и `result_sha256`;
  - `to_dict()` сериализует технический статус, сообщения и хеши без dataclass-объектов.

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_engine_integration -v`

  Expected: PASS.

- [ ] **Step 6: Написать и пройти тесты выбора и выпуска**

  Проверить:

  - `default_release_index()` выбирает первый `VERIFIED`/`VERIFIED_WITH_CONDITIONS`, иначе индекс первого результата только для просмотра, а для пустого списка — `None`;
  - `release_blockers()` блокирует `None`, индекс вне диапазона, `EXPERT_REVIEW_REQUIRED` и `REJECTED` конкретными русскими причинами;
  - `scenario_for_report()` возвращает новую копию сценария с условиями проверки в предупреждениях, не изменяя исходный `ScenarioResult`.

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_engine_integration -v`

  Expected: PASS; не менее 14 тестов.

- [ ] **Step 7: Экспортировать интерфейсы и зафиксировать изменение**

  Добавить публичные типы и функции интеграции в `engine.__init__.__all__`.

  ```powershell
  git add 05_src/crane_plan/engine/integration.py 05_src/crane_plan/engine/__init__.py 06_tests/test_engine_integration.py
  git commit -m "feat: verify legacy scenarios with engine 2.1"
  ```

### Task 4: Атомарный протокол и метаданные проекта

**Files:**
- Modify: `05_src/crane_plan/engine/protocol.py`
- Modify: `05_src/crane_plan/engine/__init__.py`
- Modify: `05_src/crane_plan/project_io.py`
- Modify: `06_tests/test_engine_protocol.py`
- Modify: `06_tests/test_io_pdf_report.py`

**Interfaces:**
- Consumes: `CalculationProtocolV3`, `ScenarioVerificationV21.to_dict()`.
- Produces:
  - `save_protocol_atomic(path: str | Path, protocol: CalculationProtocolV3) -> Path`;
  - расширенный `save_project(folder: str | Path, project: ProjectInput, scenarios: list[dict] | None = None, *, selected_scenario_index: int | None = None, scenario_verifications: list[dict] | None = None) -> Path`.

- [ ] **Step 1: Написать падающие тесты атомарной записи протокола**

  В `06_tests/test_engine_protocol.py` проверить, что `save_protocol_atomic()`:

  - создаёт родительскую папку и канонический JSON с завершающим переводом строки;
  - после успеха не оставляет временного файла;
  - при подменённой ошибке `os.replace` не повреждает заранее существующий целевой файл и удаляет временный файл.

- [ ] **Step 2: Запустить тест и подтвердить RED**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_engine_protocol -v`

  Expected: FAIL с отсутствующим `save_protocol_atomic`.

- [ ] **Step 3: Реализовать атомарную запись**

  Писать UTF-8 во временный файл рядом с целевым, затем применять `os.replace`; удалять временный файл в `finally`, если замена не завершилась. Оставить существующий `save_protocol()` для обратной совместимости и экспортировать новую функцию.

- [ ] **Step 4: Запустить тесты протокола и подтвердить GREEN**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_engine_protocol -v`

  Expected: PASS.

- [ ] **Step 5: Написать падающий тест метаданных `project.json`**

  В `06_tests/test_io_pdf_report.py` вызвать расширенный `save_project()` и проверить точные ключи:

  - `selected_scenario_index`;
  - `scenario_verifications` со статусом, сообщениями и хешами всех вариантов;
  - прежний `scenarios` остаётся без изменений;
  - `load_project()` по-прежнему восстанавливает `ProjectInput` и игнорирует служебные ключи.

- [ ] **Step 6: Реализовать расширение `save_project()` и пройти тест**

  Добавить только keyword-only параметры с безопасными значениями по умолчанию, чтобы существующие вызовы не изменились.

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_io_pdf_report -v`

  Expected: PASS.

- [ ] **Step 7: Зафиксировать изменение**

  ```powershell
  git add 05_src/crane_plan/engine/protocol.py 05_src/crane_plan/engine/__init__.py 05_src/crane_plan/project_io.py 06_tests/test_engine_protocol.py 06_tests/test_io_pdf_report.py
  git commit -m "feat: persist engine verification protocols"
  ```

### Task 5: Подключение GUI, выбранный вариант и безопасный PDF

**Files:**
- Modify: `05_src/crane_plan/app.py`
- Modify: `05_src/crane_plan/report.py`
- Modify: `06_tests/test_app_engine_integration.py`
- Modify: `06_tests/test_io_pdf_report.py`
- Modify: `README.md`
- Create: `CHANGELOG.md`

**Interfaces:**
- Consumes: все интерфейсы Tasks 1–4, `load_catalog_v3()`, существующие `optimize()` и `generate_report()`.
- Produces:
  - `CranePlanApp._reset_calculation_results(self) -> None`;
  - `CranePlanApp._selected_release_index(self) -> int | None`;
  - `CranePlanApp._refresh_release_variant_choices(self) -> None`;
  - `CranePlanApp._render_scenario_verification(self, verification: ScenarioVerificationV21) -> str`;
  - расширенный `generate_report(path: str | Path, project: ProjectInput, scenarios: list[ScenarioResult], selected_pages: list[int] | None = None, *, document_status: str | None = None) -> Path`.

- [ ] **Step 1: Написать падающие тесты GUI-оркестрации без запуска Tk mainloop**

  В `06_tests/test_app_engine_integration.py` с подменёнными зависимостями проверить:

  - `run_calculation()` сначала получает все сценарии через старый `optimize()`, затем проверяет каждый через `verify_scenarios_v21()`;
  - отсутствующий/повреждённый каталог V3 оставляет сценарии для просмотра и создаёт экспертные результаты, не закрывая приложение;
  - повторный расчёт очищает старый выбранный индекс до назначения нового;
  - поле выбора содержит все варианты, а по умолчанию выбирается первый допускаемый к выпуску;
  - текст каждого варианта содержит русский статус, конфигурацию, критическую операцию, максимальный вылет, грузоподъёмность/запас, требуемую высоту/запас, `input_sha256`, `result_sha256` и `run_id` протокола;
  - устаревший индекс после повторного расчёта блокируется.

- [ ] **Step 2: Запустить GUI-тесты и подтвердить RED**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_app_engine_integration -v`

  Expected: FAIL из-за отсутствующей оркестрации и методов выбора.

- [ ] **Step 3: Подключить расчёт и сравнительный вывод**

  В `run_calculation()` сохранить текущую валидацию и `optimize()`, загрузить каталог V3, создать один `run_id` и `created_at` на запуск, вызвать пакетную проверку и синхронно заполнить два списка. Добавить поле «Вариант для выпуска» (не более трёх значений) и блок «Независимая проверка ядром 2.1» для каждого сценария. Все технические значения брать из `ScenarioVerificationV21.engine_result`, не дублировать расчёт в `app.py`.

- [ ] **Step 4: Запустить GUI-тесты и подтвердить GREEN**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_app_engine_integration -v`

  Expected: PASS.

- [ ] **Step 5: Написать падающие тесты предпросмотра и выпуска**

  Проверить:

  - предварительный PDF для `EXPERT_REVIEW_REQUIRED` содержит текст `НЕ ДЛЯ ВЫПУСКА — ТРЕБУЕТСЯ ЭКСПЕРТНАЯ ПРОВЕРКА`;
  - предварительный PDF для `REJECTED` содержит `НЕ ДЛЯ ВЫПУСКА — ВАРИАНТ ОТКЛОНЁН`;
  - подтверждённый PDF не содержит водяного знака;
  - условно подтверждённый PDF содержит условия, включая защитный экран;
  - `preview_report_pages()` передаёт только выбранный сценарий и разрешает все четыре статуса;
  - `save_and_report()` до выбора или для запрещённого статуса не создаёт/не обновляет PDF и перечисляет причины;
  - для разрешённого статуса в `generate_report()` передаётся список из одного выбранного сценария, в `save_project()` — все проверки и выбранный индекс, а протокол сохраняется как `reports/calculation_protocol_v21.json`.

- [ ] **Step 6: Реализовать маркировку PDF**

  Добавить keyword-only `document_status`. Для двух запрещённых статусов наносить читаемую полупрозрачную отметку на каждый сформированный лист; для `None` ничего не менять. Условия разрешённого варианта добавлять через `scenario_for_report()`, чтобы они попали в существующий блок предупреждений.

- [ ] **Step 7: Реализовать проверку выпуска и выбранный сценарий**

  В `preview_report_pages()` использовать выбранный индекс либо первый доступный для просмотра. В `save_and_report()` сначала вызвать `release_blockers()`, и только при пустом результате создавать/обновлять итоговый PDF, сохранять проект и атомарный протокол. Не передавать остальные сценарии в итоговый отчёт.

- [ ] **Step 8: Запустить тесты GUI и отчёта**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest 06_tests.test_app_engine_integration 06_tests.test_io_pdf_report -v`

  Expected: PASS.

- [ ] **Step 9: Обновить документацию пользователя**

  В `README.md` кратко описать цепочку «поиск → независимая проверка → выбор → выпуск», четыре статуса, обязательное подтверждение масс, расположение протокола и ограничения первого этапа. В `CHANGELOG.md` добавить раздел интеграции ядра 2.1 без изменения публичного номера версии.

- [ ] **Step 10: Выполнить полную проверку проекта**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m compileall -q 05_src 06_tests`

  Expected: exit code 0, без вывода ошибок.

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m unittest discover -s 06_tests -v`

  Expected: PASS для всего набора, включая не менее 109 существующих тестов и все новые тесты.

- [ ] **Step 11: Провести ручную проверку критического пути**

  Запустить приложение, открыть существующий однокрановый проект и подтвердить:

  - все найденные варианты видны и имеют независимый статус;
  - изменение груза снимает подтверждение и старый выбор;
  - непроверенный вариант открывает предпросмотр с отметкой, но не выпускается;
  - проверенный вариант создаёт PDF только с выбранной схемой и JSON-протокол рядом с ним.

- [ ] **Step 12: Зафиксировать интеграцию**

  ```powershell
  git add 05_src/crane_plan/app.py 05_src/crane_plan/report.py 06_tests/test_app_engine_integration.py 06_tests/test_io_pdf_report.py README.md CHANGELOG.md
  git commit -m "feat: integrate engine 2.1 verification into GUI"
  ```

### Task 6: Финальная проверка ветки перед слиянием

**Files:**
- Review: все файлы Tasks 1–5
- Test: `06_tests/`

**Interfaces:**
- Consumes: завершённая интеграция Tasks 1–5.
- Produces: проверенная ветка без незакоммиченных изменений, готовая к отдельному code review и последующему слиянию.

- [ ] **Step 1: Проверить чистоту и состав изменений**

  Run: `git status --short; git diff --check; git log --oneline --decorate -6`

  Expected: рабочее дерево чистое; `git diff --check` не сообщает ошибок; видны отдельные коммиты Tasks 1–5.

- [ ] **Step 2: Повторить машинную проверку с нуля**

  Run: `$env:PYTHONPATH=(Resolve-Path '.\05_src').Path; python -m compileall -q 05_src 06_tests; python -m unittest discover -s 06_tests -v`

  Expected: exit code 0 и полный PASS.

- [ ] **Step 3: Сверить обязательные сценарии со спецификацией**

  Сопоставить 16 обязательных тестов раздела 10 спецификации с именами реально выполненных тестов; если пункт не покрыт, сначала добавить отдельный падающий тест и минимальную реализацию, затем повторить Step 2.

- [ ] **Step 4: Запросить итоговый code review**

  Проверяющий должен отдельно оценить пять пунктов `Review Focus`, отсутствие скрытых логистических допущений, атомарность протокола и то, что запрещённый статус невозможно обойти через предпросмотр/старый индекс.
