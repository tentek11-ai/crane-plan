# Full PPRk Master Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Выпускать из CranePlan полный комплект ППРк по структуре эталонного проекта с расчетными объектными листами, полной условной пояснительной запиской, точными копиями типовых схем и контролем готовности к выпуску.

**Architecture:** Вводится отдельный слой формирования ППРк между расчетным ядром и PDF-рендерером. Он строит неизменяемую модель комплекта из проекта, выбранного сценария, каталога шаблонов и реестра приложений; PDF-слой только отображает эту модель. Типовые изображения хранятся как проверенные клипы исходного PDF без перерисовки, а объектные планы и разрезы продолжают строиться расчетными модулями CranePlan.

**Tech Stack:** Python 3, dataclasses, tkinter/ttk, ReportLab, pypdf, pdfplumber/Pillow, pytest/unittest.

**Spec:** `docs/superpowers/specs/2026-11-04-full-pprk-master-template-design.md`

## Global Constraints

- Не перерисовывать и не восстанавливать типовые инженерные схемы средствами ИИ.
- Исключать из публикуемых клипов старые рамки, штампы, шифр, реквизиты объекта и водяные надписи, не изменяя содержание схемы.
- Не публиковать подписи об авторстве, происхождении или «проекте-аналоге».
- Не переносить в новый проект адрес, организации, фамилии, координаты и этапные значения эталонного объекта.
- Пояснительная записка — A4; расчетные графические листы — A3/A2/A1 по читаемости.
- Программа не присваивает автоматически статусы «утвержден» и «в производство» и не имитирует подписи.
- Отсутствующий внешний конструктивный проект не мешает предварительному выпуску, но блокирует статус «в производство».
- Старые проекты загружаются без потери данных и не перезаписываются до явного сохранения.

## Review Focus

- Клипы содержат мелкий текст или водяную надпись: выпуск должен блокироваться, а не улучшать изображение автоматически — Task 1.
- Повторный расчет меняет шаблонный текст, но не должен стирать пользовательские правки — Task 3.
- Условный раздел становится обязательным после изменения груза/операции: состав и ссылки должны перестроиться без «висячих» номеров — Task 5.
- Внешний PDF имеет смешанный формат или поворот страниц: объединение должно сохранить размер и ориентацию — Task 9.
- Предпросмотр устарел после изменения расчетных данных: финальный PDF не должен использовать старую модель комплекта — Task 10.

---

### Task 1: Реестр и извлечение типовых графических фрагментов

**Files:**
- Create: `05_src/crane_plan/pprk_assets.py`
- Create: `05_src/crane_plan/assets/pprk/manifest.json`
- Create: `tools/extract_pprk_reference_assets.py`
- Create: `06_tests/test_pprk_assets.py`
- Modify: `tools/build_portable_release.py`

**Interfaces:**
- Produces: `PPRKAssetRecord`, `load_asset_manifest() -> tuple[PPRKAssetRecord, ...]`, `validate_asset_library(root: Path) -> list[AssetIssue]`.
- Consumes: эталонный PDF только во время контролируемого извлечения; готовая программа использует упакованные клипы.

- [ ] **Step 1: Write failing manifest validation tests**

Проверить уникальные `asset_id`, существование файла, SHA-256, минимальное разрешение, отсутствие запрещенных строк OCR (`ППР ЦЕНТР`, `27.06-23`, `AUTODESK EDUCATIONAL PRODUCT`) и отказ для нечитаемого/загрязненного клипа.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `pytest 06_tests/test_pprk_assets.py -v`  
Expected: FAIL because `pprk_assets` does not exist.

- [ ] **Step 3: Implement asset records and validator**

Определить точные поля: `asset_id`, `title`, `category`, `file_name`, `source_page`, `crop_box`, `sha256`, `pixel_width`, `pixel_height`, `source_kind`, `quality_status`. Валидатор не изменяет изображение.

- [ ] **Step 4: Implement deterministic extraction script**

Сценарий принимает `--source-pdf`, `--manifest`, `--output-dir`; извлекает только заданные прямоугольники, сохраняет исходное качество и обновляет контрольные суммы. Включить отдельные клипы схем строповки, ограждений, знаков, сигналов, складирования и защитных экранов.

- [ ] **Step 5: Package the asset directory in portable releases**

Проверить, что сборщик копирует manifest и все перечисленные файлы, но не копирует исходный 71-страничный PDF.

- [ ] **Step 6: Run tests**

Run: `pytest 06_tests/test_pprk_assets.py 06_tests/test_release_builder.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add 05_src/crane_plan/pprk_assets.py 05_src/crane_plan/assets/pprk tools/extract_pprk_reference_assets.py tools/build_portable_release.py 06_tests/test_pprk_assets.py
git commit -m "feat: add verified PPRk reference asset library"
```

### Task 2: Модель выпуска ППРк и миграция проекта

**Files:**
- Create: `05_src/crane_plan/pprk_models.py`
- Modify: `05_src/crane_plan/models.py`
- Modify: `05_src/crane_plan/project_io.py`
- Create: `06_tests/test_pprk_models.py`
- Modify: `06_tests/test_io_pdf_report.py`

**Interfaces:**
- Produces: `PPRKReleaseConfig`, `ApprovalSlot`, `ExternalDocument`, `TemplateOverride`, `ReleaseStatus`, `CompletenessIssue`.
- Consumes: existing `ProjectInput.to_dict()` and `load_project()` migration path.

- [ ] **Step 1: Write failing serialization and migration tests**

Зафиксировать восемь согласований по умолчанию, отдельные данные титула, список внешних документов, пользовательские правки, status `PRELIMINARY`, загрузку schema v3 с безопасными значениями и сохранение schema v4.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest 06_tests/test_pprk_models.py 06_tests/test_io_pdf_report.py -v`  
Expected: FAIL on missing model types.

- [ ] **Step 3: Implement `pprk_models.py`**

Использовать dataclasses и строковые Enum. `PPRKReleaseConfig` содержит реквизиты выпуска, согласования, включения/исключения, overrides, внешние документы и выбранный статус.

- [ ] **Step 4: Add `pprk_release` to `ProjectInput` and migrate schema**

Старый JSON должен загружаться с конфигурацией по умолчанию; неизвестные новые поля не должны ломать загрузку.

- [ ] **Step 5: Run tests**

Run: `pytest 06_tests/test_pprk_models.py 06_tests/test_io_pdf_report.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add 05_src/crane_plan/pprk_models.py 05_src/crane_plan/models.py 05_src/crane_plan/project_io.py 06_tests/test_pprk_models.py 06_tests/test_io_pdf_report.py
git commit -m "feat: persist full PPRk release configuration"
```

### Task 3: Каталог полного текста и безопасные пользовательские правки

**Files:**
- Create: `05_src/crane_plan/pprk_templates.py`
- Create: `05_src/crane_plan/assets/pprk/sections.json`
- Create: `06_tests/test_pprk_templates.py`

**Interfaces:**
- Produces: `TemplateSection`, `TemplateParagraph`, `load_template_catalog()`, `render_template_text(section_id, context, overrides) -> RenderedSection`.
- Consumes: `TemplateOverride` from Task 2.

- [ ] **Step 1: Write failing catalog tests**

Проверить наличие всех 22 разделов спецификации, уникальные идентификаторы, обязательные переменные, нормативные ключи, условия включения и запрет необъявленных placeholder-полей.

- [ ] **Step 2: Write failing override preservation tests**

Ручная замена абзаца должна сохраняться после изменения расчетного контекста; изменение версии базового абзаца должно создавать конфликт, а не молча стирать правку.

- [ ] **Step 3: Run tests and confirm failure**

Run: `pytest 06_tests/test_pprk_templates.py -v`  
Expected: FAIL because catalog loader is missing.

- [ ] **Step 4: Implement catalog and strict renderer**

Не хранить полный текст в `report.py`. Рендерер принимает только объявленные переменные, возвращает список незаполненных обязательных полей и не подставляет значения эталонного объекта.

- [ ] **Step 5: Populate the full standard section catalog**

Перенести максимально полный применимый текст эталона с исправлением реквизитов, явных ошибок и устаревших нормативных ссылок; каждый абзац получает стабильный ID.

- [ ] **Step 6: Run tests**

Run: `pytest 06_tests/test_pprk_templates.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add 05_src/crane_plan/pprk_templates.py 05_src/crane_plan/assets/pprk/sections.json 06_tests/test_pprk_templates.py
git commit -m "feat: add conditional full PPRk text catalog"
```

### Task 4: Объектный контекст и трассировка расчетных значений

**Files:**
- Create: `05_src/crane_plan/pprk_context.py`
- Create: `06_tests/test_pprk_context.py`
- Modify: `05_src/crane_plan/engine/integration.py`

**Interfaces:**
- Produces: `PPRKContext`, `PPRKValueTrace`, `build_pprk_context(project, scenario, verification) -> PPRKContext`.
- Consumes: `ProjectInput`, `ScenarioResult`, engine verification protocol.

- [ ] **Step 1: Write failing context tests**

Проверить объект/адрес, кран, грузовые проверки, высоты, длины стрел, пристежки, опасные зоны, маршруты и номера операций. Каждое числовое значение должно иметь `source`, `rule`, `algorithm_version`.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest 06_tests/test_pprk_context.py -v`  
Expected: FAIL on missing builder.

- [ ] **Step 3: Implement the context builder**

Не пересчитывать инженерные величины внутри отчетного слоя; только переносить проверенные результаты и явно помечать отсутствующие значения.

- [ ] **Step 4: Run tests**

Run: `pytest 06_tests/test_pprk_context.py 06_tests/test_engine_integration.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 05_src/crane_plan/pprk_context.py 05_src/crane_plan/engine/integration.py 06_tests/test_pprk_context.py 06_tests/test_engine_integration.py
git commit -m "feat: build traceable PPRk calculation context"
```

### Task 5: Конструктор состава, нумерации и комплектности

**Files:**
- Create: `05_src/crane_plan/pprk_composer.py`
- Create: `06_tests/test_pprk_composer.py`

**Interfaces:**
- Produces: `PPRKBundle`, `PPRKDocumentPart`, `PPRKSheet`, `compose_pprk(context, templates, assets, config) -> PPRKBundle`, `check_completeness(bundle) -> tuple[CompletenessIssue, ...]`.
- Consumes: Tasks 1–4.

- [ ] **Step 1: Write failing first-four-pages test**

Assert exact order: титул, лист согласований, лист ознакомления, состав проекта. Verify eight approval cells by default.

- [ ] **Step 2: Write failing conditional composition tests**

Бадья включает соответствующий раздел и карту; длинномерный груз включает оттяжки; два крана включают совместную работу; изменение входа перестраивает состав и ссылки без разрывов.

- [ ] **Step 3: Write failing completeness/status tests**

Незаполненный адрес дает placeholder и блокирует `IN_PRODUCTION`; отсутствующий проект пристежек блокирует только конечный статус; предварительный комплект остается доступен.

- [ ] **Step 4: Run tests and confirm failure**

Run: `pytest 06_tests/test_pprk_composer.py -v`  
Expected: FAIL on missing composer.

- [ ] **Step 5: Implement immutable bundle composition**

Сквозные страницы записки и номера графических листов формируются раздельно. Состав проекта создается после построения всех частей, а ссылки разрешаются по стабильным ID.

- [ ] **Step 6: Run tests**

Run: `pytest 06_tests/test_pprk_composer.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add 05_src/crane_plan/pprk_composer.py 06_tests/test_pprk_composer.py
git commit -m "feat: compose and validate full PPRk bundles"
```

### Task 6: Служебные листы и полная пояснительная записка PDF

**Files:**
- Create: `05_src/crane_plan/pprk_text_report.py`
- Create: `06_tests/test_pprk_text_report.py`
- Modify: `05_src/crane_plan/report.py`

**Interfaces:**
- Produces: `draw_title_page`, `draw_approval_page`, `draw_familiarization_page`, `build_explanatory_note_story`.
- Consumes: `PPRKBundle` from Task 5.

- [ ] **Step 1: Write failing PDF text/order tests**

Извлеченный текст первых страниц должен содержать требуемые заголовки в порядке; записка должна содержать все включенные разделы и не содержать реквизиты эталона.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest 06_tests/test_pprk_text_report.py -v`  
Expected: FAIL because pages are not bundle-driven.

- [ ] **Step 3: Implement A4 service pages and note renderer**

Использовать существующий ГОСТ-подобный шрифт и стили, но вынести длинные тексты из `report.py`. Видимые placeholders выделять и передавать в completeness issues.

- [ ] **Step 4: Preserve `generate_report()` compatibility**

Добавить необязательный `bundle: PPRKBundle | None`; при отсутствии строить bundle через новый слой. Существующие вызовы и тесты не должны ломаться.

- [ ] **Step 5: Run tests**

Run: `pytest 06_tests/test_pprk_text_report.py 06_tests/test_io_pdf_report.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add 05_src/crane_plan/pprk_text_report.py 05_src/crane_plan/report.py 06_tests/test_pprk_text_report.py 06_tests/test_io_pdf_report.py
git commit -m "feat: render full PPRk front matter and explanatory note"
```

### Task 7: Поэтапные расчетные листы и автоматический формат

**Files:**
- Create: `05_src/crane_plan/pprk_sheets.py`
- Create: `06_tests/test_pprk_sheets.py`
- Modify: `05_src/crane_plan/report.py`
- Modify: `05_src/crane_plan/sozr_report.py`

**Interfaces:**
- Produces: `choose_sheet_format(bounds, min_text_mm)`, `draw_calculated_sheet(canvas, sheet, context)`.
- Consumes: existing plan, section, SOZR and joint-work drawing functions.

- [ ] **Step 1: Write failing format and stage tests**

Проверить A3/A2/A1 выбор, отдельные листы ниже/выше 0,000 при различии решений, стабильные номера и наличие этапных конфигураций на разрезе.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest 06_tests/test_pprk_sheets.py -v`  
Expected: FAIL on missing sheet planner.

- [ ] **Step 3: Implement sheet planning and reuse existing drawing primitives**

Не дублировать геометрию. Лист получает данные из `PPRKContext`, выбирает формат и вызывает существующие отрисовщики плана, разреза и СОЗР.

- [ ] **Step 4: Run tests**

Run: `pytest 06_tests/test_pprk_sheets.py 06_tests/test_sozr_report.py 06_tests/test_io_pdf_report.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 05_src/crane_plan/pprk_sheets.py 05_src/crane_plan/report.py 05_src/crane_plan/sozr_report.py 06_tests/test_pprk_sheets.py
git commit -m "feat: generate staged PPRk calculation sheets"
```

### Task 8: Строповка и типовые приложения из неизмененных клипов

**Files:**
- Create: `05_src/crane_plan/pprk_appendices.py`
- Create: `06_tests/test_pprk_appendices.py`
- Modify: `05_src/crane_plan/report.py`

**Interfaces:**
- Produces: `build_slinging_cards(bundle)`, `draw_asset_appendix(canvas, appendix, assets)`, `AppendixRenderResult`.
- Consumes: asset manifest, active loads and composed appendix list.

- [ ] **Step 1: Write failing slinging selection tests**

Активный груз выбирает соответствующий clip; неактивный не публикуется; неизвестный груз создает обязательный placeholder без фантомного рисунка.

- [ ] **Step 2: Write failing image-integrity tests**

Вставленный clip должен иметь SHA-256 из manifest, сохранять пропорции и не подвергаться фильтрам/дорисовке; динамическая таблица массы должна совпадать с `Load.total_kg`.

- [ ] **Step 3: Run tests and confirm failure**

Run: `pytest 06_tests/test_pprk_appendices.py -v`  
Expected: FAIL on missing appendix renderer.

- [ ] **Step 4: Implement appendices and replace generated sling sketches**

Использовать исходные клипы для строповки, ограждений, знаков, сигналов, складирования и экранов. Объектные данные выводить отдельными таблицами без наложения на изображение.

- [ ] **Step 5: Run tests**

Run: `pytest 06_tests/test_pprk_appendices.py 06_tests/test_io_pdf_report.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add 05_src/crane_plan/pprk_appendices.py 05_src/crane_plan/report.py 06_tests/test_pprk_appendices.py
git commit -m "feat: render exact reference schemes in PPRk appendices"
```

### Task 9: Внешние PDF-приложения и финальная сборка

**Files:**
- Create: `05_src/crane_plan/pprk_merge.py`
- Create: `06_tests/test_pprk_merge.py`
- Modify: `05_src/crane_plan/report.py`

**Interfaces:**
- Produces: `merge_pprk_documents(main_pdf, external_documents, output_pdf) -> MergeResult`.
- Consumes: `ExternalDocument` from Task 2 and composed order from Task 5.

- [ ] **Step 1: Write failing mixed-page merge tests**

Создать тестовые A4 portrait, A3 landscape и повернутую страницу; после слияния mediabox, rotation and page order должны сохраниться.

- [ ] **Step 2: Write failing missing-document/status tests**

Отсутствующий необязательный файл дает warning; обязательный блокирует конечный статус; исходные PDF не изменяются.

- [ ] **Step 3: Run tests and confirm failure**

Run: `pytest 06_tests/test_pprk_merge.py -v`  
Expected: FAIL on missing merge function.

- [ ] **Step 4: Implement atomic pypdf merge**

Собирать во временный файл, повторно открывать для проверки количества/форматов страниц, затем атомарно заменять результат.

- [ ] **Step 5: Run tests**

Run: `pytest 06_tests/test_pprk_merge.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add 05_src/crane_plan/pprk_merge.py 05_src/crane_plan/report.py 06_tests/test_pprk_merge.py
git commit -m "feat: merge external documents into final PPRk"
```

### Task 10: Интерфейс конструктора, предпросмотр и защита от устаревшего выпуска

**Files:**
- Modify: `05_src/crane_plan/app.py`
- Create: `06_tests/test_app_pprk_release.py`
- Modify: `06_tests/test_app_engine_integration.py`

**Interfaces:**
- Consumes: composer, completeness checker, template overrides and merge service.
- Produces: UI для реквизитов, согласований, состава, приложений, статуса и выпуска.

- [ ] **Step 1: Write failing UI-state tests**

Проверить восемь согласований по умолчанию, добавление/удаление, список условных разделов с причиной, внешние PDF, issues и невозможность выбрать конечный статус при блокерах.

- [ ] **Step 2: Write failing stale-preview test**

После изменения проекта hash preview должен стать устаревшим; `save_and_report()` обязан пересобрать context/bundle, а не использовать старый PDF.

- [ ] **Step 3: Run tests and confirm failure**

Run: `pytest 06_tests/test_app_pprk_release.py 06_tests/test_app_engine_integration.py -v`  
Expected: FAIL on missing UI state.

- [ ] **Step 4: Implement the PPRk release editor in the existing report tab**

Добавить панели «Реквизиты», «Согласования», «Разделы», «Приложения», «Комплектность». Сохранить существующий предпросмотр страниц и связать его с `PPRKBundle`.

- [ ] **Step 5: Implement release guards**

Кнопка формирования показывает блокеры и допускает предварительный PDF с соответствующим статусом; финальный выпуск требует актуального расчета и отсутствия блокеров.

- [ ] **Step 6: Run tests**

Run: `pytest 06_tests/test_app_pprk_release.py 06_tests/test_app_engine_integration.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add 05_src/crane_plan/app.py 06_tests/test_app_pprk_release.py 06_tests/test_app_engine_integration.py
git commit -m "feat: add full PPRk release workflow"
```

### Task 11: Сквозная проверка комплекта, визуальный контроль и документация

**Files:**
- Create: `06_tests/test_full_pprk_end_to_end.py`
- Modify: `07_docs/USER_GUIDE.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified full sample PPRk and documented workflow.

- [ ] **Step 1: Write end-to-end project fixture**

Включить бетонную бадью, длинномерный груз, складирование, опасную зону, пристежки and two-crane scenario; attach mixed-format external PDFs.

- [ ] **Step 2: Assert structural completeness**

Проверить первые четыре страницы, состав, все включенные разделы, расчетные листы, приложения, absence of forbidden reference identifiers and exact page/sheet counts.

- [ ] **Step 3: Render every final PDF page to PNG**

Проверить автоматическими heuristics отсутствие пустых страниц, обрезанного текста, недопустимо малых изображений и наложений; затем выполнить визуальную проверку контактных листов.

- [ ] **Step 4: Run full regression suite**

Run: `pytest 06_tests -q`  
Expected: all tests PASS.

- [ ] **Step 5: Build and smoke-test portable release**

Run: `python tools/build_portable_release.py` using the configured runtime.  
Expected: release contains the application, manifest, all verified PPRk assets and no source reference PDF.

- [ ] **Step 6: Update documentation and changelog**

Описать разницу между расчетной частью, типовыми блоками и внешними проектами; объяснить статусы выпуска и порядок замены нечитаемого клипа.

- [ ] **Step 7: Commit**

```bash
git add 06_tests/test_full_pprk_end_to_end.py 07_docs/USER_GUIDE.md README.md CHANGELOG.md
git commit -m "test: verify complete PPRk generation workflow"
```

