# IVDon Article Rewrite and Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Выпустить полностью переработанную статью для «Инженерного вестника Дона», проверочную PDF-копию и ответ редакции о разработанной и верифицированной на трех реальных объектах математической модели CranePlan Portable 2.2.2.

**Architecture:** Исследовательские доказательства хранятся отдельно от публичного текста статьи и нормализуются в машиночитаемые реестры. Рукопись собирается из проверенного Markdown-текста, таблиц результатов, матрицы литературы и локальных рисунков детерминированным Python-скриптом; DOCX затем компилируется в PDF и проходит автоматическую и визуальную проверку. Неподтвержденные сведения остаются качественными утверждениями и не превращаются в численные показатели.

**Tech Stack:** Python 3.11+, `python-docx`, `pypdf`, `pdfplumber`, Poppler, встроенный рендерер документов Codex, `unittest`, Markdown, CSV, JSON.

**Spec:** `docs/superpowers/specs/2026-10-22-ivdon-article-rewrite-validation-design.md`

## Global Constraints

- В тексте статьи, таблицах и рисунках не использовать обозначения `PPRK-005`, `PPRK-006`, `PPRK-007`; использовать полные названия объектов из спецификации.
- `PASS_WITH_CONDITIONS` переводить как «решение допустимо при выполнении установленных условий безопасности».
- Малый Знаменский переулок и Люберцы описывать как ретроспективные объекты, воспроизведенные сторонним проектировщиком в независимой пользовательской среде.
- Объект на ул. Новаторов описывать как независимый расчет с последующей экспертной оценкой, а не как фактическую реализацию программной схемы.
- Наличие файлов независимых пользовательских запусков, итоговых ППРк, датированной характеристики проектировщика и письменного заключения Гриценко В. Н. подтверждено автором; документы хранятся у автора и могут быть предоставлены редакции по запросу.
- Продолжительность `1,774` дня относится только к заданному набору из 160 подъемов при 24 ч/сут и коэффициенте использования 0,7.
- Численные значения публиковать только при наличии файла проекта, итогового ППРк, паспорта крана или явного локатора источника.
- Исходную отклоненную рукопись и исходные материалы редакции не перезаписывать.
- Персональные контакты и частные доказательства хранить вне публичного дерева статьи; публичный текст не должен содержать телефон или e-mail.
- Третья статья и пять новых независимых объектов остаются за пределами этого плана.

## Review Focus

- **Доказательные документы хранятся у автора, но не переданы в текущую рабочую среду:** публичный реестр должен фиксировать статус `AUTHOR_CONFIRMED_HELD_BY_AUTHOR`, не утверждая, что оригиналы инспектированы исполнителем; проверяется в Task 2.
- **Внутренние идентификаторы просочились в рукопись:** сборка должна завершаться ошибкой при `PPRK-005` - `PPRK-007`; проверяется в Task 4.
- **Однокрановая схема на ул. Новаторов представлена как безусловная или реализованная:** проверка утверждений должна требовать русскую условную формулировку и запрещать заявление о внедрении; проверяется в Task 3.
- **Расчетные 1,774 дня ошибочно названы сроком строительства:** проверка должна допускать число только рядом с описанием 160 подъемов; проверяется в Task 3.
- **DOCX формально создан, но таблицы, формулы или подписи обрезаны:** финальная задача должна отрендерить все страницы и потребовать визуальную проверку каждой страницы; проверяется в Task 6.

---

## Planned File Structure

### Sources and evidence

- Create: `01_sources/04_article_editorial/README.md` - происхождение отклоненной рукописи и письма редакции без изменения оригиналов.
- Create: `01_sources/04_article_editorial/source_manifest.csv` - SHA-256, тип и приватный локатор исходной рукописи и редакционного PDF.
- Preserve privately: `11_backups/article_1_evidence_private/editorial/migin_elsheikh.docx` - неизмененная отклоненная рукопись из `F:\загрузки хром\migin_elsheikh.docx`.
- Preserve privately: `11_backups/article_1_evidence_private/editorial/Инженерный вестник Дона.pdf` - неизмененный редакционный материал из `F:\загрузки хром\Инженерный вестник Дона.pdf`.
- Create: `08_dissertation/04_article_1_crane_placement/results/external_validation_attestation.json` - публичная обезличенная фиксация стороннего запуска.
- Create: `08_dissertation/04_article_1_crane_placement/results/novatorov_v222_result.json` - нормализованный результат версии 2.2.2 по ул. Новаторов.
- Modify: `08_dissertation/04_article_1_crane_placement/cases/*/case_manifest.json` - корректные статусы проверки.
- Modify: `08_dissertation/04_article_1_crane_placement/cases/*/source_register.csv` - локаторы и статус доказательств.
- Modify: `08_dissertation/04_article_1_crane_placement/results/run_registry.csv` - реестр запусков и доступности артефактов.
- Modify: `08_dissertation/04_article_1_crane_placement/results/results_summary.csv` - только подтвержденные показатели.

### Manuscript sources

- Create: `08_dissertation/04_article_1_crane_placement/manuscript/ARTICLE_RU.md` - полный научный текст без верстки Word.
- Create: `08_dissertation/04_article_1_crane_placement/manuscript/ARTICLE_METADATA.json` - название, авторы, организации, ключевые слова, подписи рисунков и таблиц.
- Create: `08_dissertation/04_article_1_crane_placement/manuscript/EDITOR_RESPONSE_RU.md` - ответ редакции по каждому замечанию.
- Modify: `08_dissertation/04_article_1_crane_placement/EDITORIAL_RESPONSE_MATRIX.md` - связь замечаний с разделами новой статьи.

### Build and tests

- Create: `04_experiments/import_ivdon_validation_evidence.py` - нормализация доказательств трех объектов.
- Create: `04_experiments/build_ivdon_article_revision.py` - сборка DOCX статьи и ответа редакции.
- Create: `06_tests/test_ivdon_validation_evidence.py` - статусы, локаторы, численные значения и fallback для отсутствующих файлов.
- Create: `06_tests/test_ivdon_article_claims.py` - научные утверждения, названия объектов и запрет внутренних кодов.
- Create: `06_tests/test_ivdon_article_build.py` - структура и содержимое DOCX.
- Modify: `06_tests/test_article_evidence_hygiene.py` - новые статусы кейсов и запрет устаревшей формулировки «принят для реализации».

### Final outputs

- Create: `output/docx/Статья_Математическая_модель_выбора_башенных_кранов_ИВД_2026.docx`.
- Create: `output/pdf/Статья_Математическая_модель_выбора_башенных_кранов_ИВД_2026.pdf`.
- Create: `output/docx/Ответ_редакции_Инженерный_вестник_Дона_2026.docx`.

---

### Task 1: Correct the Case Status Model

**Files:**
- Modify: `06_tests/test_article_evidence_hygiene.py`
- Modify: `08_dissertation/04_article_1_crane_placement/cases/PPRK-005/case_manifest.json`
- Modify: `08_dissertation/04_article_1_crane_placement/cases/PPRK-006/case_manifest.json`
- Modify: `08_dissertation/04_article_1_crane_placement/cases/PPRK-007/case_manifest.json`
- Modify: `08_dissertation/04_article_1_crane_placement/cases/PPRK-005/source_register.csv`
- Modify: `08_dissertation/04_article_1_crane_placement/cases/PPRK-006/source_register.csv`
- Modify: `08_dissertation/04_article_1_crane_placement/cases/PPRK-007/source_register.csv`

**Interfaces:**
- Consumes: утвержденные статусы из спецификации.
- Produces: `validation_status` со значениями `retrospective_external_reproduction_positive` для первых двух объектов и `independent_pilot_expert_confirmed_with_conditions` для ул. Новаторов.

- [ ] **Step 1: Update the evidence hygiene test with the new statuses**

```python
expected_statuses = {
    "PPRK-005": "retrospective_external_reproduction_positive",
    "PPRK-006": "retrospective_external_reproduction_positive",
    "PPRK-007": "independent_pilot_expert_confirmed_with_conditions",
}
```

Добавить проверку, что ни один публичный реестр не содержит значения `independent_pilot_accepted_for_implementation`.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m unittest 06_tests/test_article_evidence_hygiene.py -v`

Expected: FAIL на старых значениях статуса.

- [ ] **Step 3: Update the three manifests and source registers**

Зафиксировать полные названия объектов, новый статус, вид проверки, источник подтверждения и границу утверждений. В публичных файлах не указывать контакты проектировщика или эксперта.

- [ ] **Step 4: Run the evidence hygiene test**

Run: `python -m unittest 06_tests/test_article_evidence_hygiene.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 06_tests/test_article_evidence_hygiene.py 08_dissertation/04_article_1_crane_placement/cases
git commit -m "test: correct article validation statuses"
```

### Task 2: Normalize Validation Evidence for Three Named Objects

**Files:**
- Create: `04_experiments/import_ivdon_validation_evidence.py`
- Create: `06_tests/test_ivdon_validation_evidence.py`
- Create: `08_dissertation/04_article_1_crane_placement/results/external_validation_attestation.json`
- Create: `08_dissertation/04_article_1_crane_placement/results/novatorov_v222_result.json`
- Modify: `08_dissertation/04_article_1_crane_placement/results/run_registry.csv`
- Modify: `08_dissertation/04_article_1_crane_placement/results/results_summary.csv`
- Create: `01_sources/04_article_editorial/README.md`
- Create: `01_sources/04_article_editorial/source_manifest.csv`
- Preserve privately: `11_backups/article_1_evidence_private/editorial/migin_elsheikh.docx`
- Preserve privately: `11_backups/article_1_evidence_private/editorial/Инженерный вестник Дона.pdf`

**Interfaces:**
- Consumes: `project.json` и итоговый PDF из сохраненной папки ул. Новаторов; обезличенное свидетельство автора о стороннем запуске двух ретроспективных объектов.
- Produces: `load_validation_evidence(article_root: Path, novatorov_project: Path) -> dict[str, object]` и два стабильных JSON-файла для текста и таблиц статьи.

- [ ] **Step 1: Write failing tests for confirmed and missing evidence**

Tests must assert:

```python
self.assertEqual(novatorov["software_version"], "2.2.2")
self.assertEqual(novatorov["recommended_model"], "130 EC-B 6")
self.assertEqual(novatorov["covered_points"], 16)
self.assertEqual(novatorov["accounted_lifts"], 160)
self.assertEqual(novatorov["status_ru"], "решение допустимо при выполнении установленных условий безопасности")
self.assertEqual(novatorov["expert_evidence_status"], "AUTHOR_CONFIRMED_WRITTEN_SIGNED_STAMPED")
self.assertEqual(retrospective["evidence_status"], "AUTHOR_CONFIRMED_HELD_BY_AUTHOR")
```

Добавить fixture без локальных копий файлов стороннего запуска и проверить, что importer фиксирует подтвержденное автором наличие архива, но не придумывает не переданные в рабочую среду численные значения.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m unittest 06_tests/test_ivdon_validation_evidence.py -v`

Expected: FAIL because importer and normalized files do not exist.

- [ ] **Step 3: Implement `load_validation_evidence` and CLI export**

`import_ivdon_validation_evidence.py` должен:

- читать сохраненный `project.json` объекта на ул. Новаторов;
- выбирать основной вариант по порядку сохраненного ранжирования;
- извлекать 16/16 точек, 160/160 подъемов, модель, координаты, стрелу, вылет, высоту, продолжительность и предупреждения;
- записывать SHA-256 исходного `project.json` и итогового PDF без публикации абсолютного пользовательского пути;
- формировать обезличенную запись о подтвержденных двух ретроспективных проектах, датированной положительной характеристике и хранении доказательного комплекта у автора;
- различать `AUTHOR_CONFIRMED_HELD_BY_AUTHOR` и `INSPECTED_IN_WORKSPACE`, чтобы не заявлять личную проверку недоступных оригиналов.

- [ ] **Step 4: Preserve the original editorial sources without publishing them**

Скопировать исходный DOCX и PDF в игнорируемый Git приватный каталог, вычислить SHA-256 и записать только хеши, тип документа и приватный относительный локатор в `source_manifest.csv`. Проверить, что `git check-ignore` подтверждает игнорирование обоих приватных файлов.

- [ ] **Step 5: Run the importer against the preserved Novatorov project**

Run:

```powershell
python 04_experiments/import_ivdon_validation_evidence.py --novatorov-project "C:\Users\Владимир\Documents\КранПлан проекты\2026 — г. Москва — Родильный дом № 4" --article-root 08_dissertation/04_article_1_crane_placement
```

Expected: two JSON files updated; no absolute user path in public outputs.

- [ ] **Step 6: Run evidence tests**

Run: `python -m unittest 06_tests/test_ivdon_validation_evidence.py 06_tests/test_article_evidence_hygiene.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add 01_sources/04_article_editorial/README.md 01_sources/04_article_editorial/source_manifest.csv 04_experiments/import_ivdon_validation_evidence.py 06_tests/test_ivdon_validation_evidence.py 08_dissertation/04_article_1_crane_placement/results
git commit -m "feat: normalize ivdon validation evidence"
```

### Task 3: Build the Claim and Editorial Compliance Gate

**Files:**
- Create: `06_tests/test_ivdon_article_claims.py`
- Modify: `08_dissertation/04_article_1_crane_placement/EDITORIAL_RESPONSE_MATRIX.md`
- Modify: `08_dissertation/04_article_1_crane_placement/TERMINOLOGY.md`
- Modify: `08_dissertation/04_article_1_crane_placement/ARTICLE_PASSPORT.md`

**Interfaces:**
- Consumes: normalized evidence JSON and literature matrix.
- Produces: `validate_article_claims(text: str, evidence: dict[str, object]) -> list[str]` in the test helper or build module; empty list means the manuscript may be built.

- [ ] **Step 1: Write failing claim tests**

Tests must reject:

- `PPRK-005`, `PPRK-006`, `PPRK-007` in public manuscript text;
- `PASS_WITH_CONDITIONS` in final Russian prose;
- claims that the one-crane solution was implemented or accepted for implementation;
- `1,774` or `1.774` unless the same paragraph contains `160` and `подъем`/`подъём`;
- a blanket literature reference containing more than three sources.

Tests must require all three full object names and the Russian conditional status.
Также тест должен требовать центральную формулировку «разработана и верифицирована на трех реальных объектах математическая модель» и письменный статус экспертной оценки.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m unittest 06_tests/test_ivdon_article_claims.py -v`

Expected: FAIL because compliance metadata and manuscript source are not yet aligned.

- [ ] **Step 3: Update the passport, terminology, and editorial matrix**

Matrix rows must cover `LITERATURE_REVIEW`, `ABBREVIATION`, `OBJECT_DESCRIPTION`, and `UNSUPPORTED_CLAIMS`, and name the exact new section that resolves each criticism. Replace the obsolete status «принят для реализации» with «технически допустимо и организационно предпочтительно при выполнении защитных мероприятий».

- [ ] **Step 4: Run the claim and citation gates**

Run: `python -m unittest 06_tests/test_ivdon_article_claims.py 06_tests/test_article_citations.py 06_tests/test_article_evidence_hygiene.py -v`

Expected: PASS for metadata and fixtures; manuscript-specific assertions may remain skipped until Task 4 with an explicit skip reason.

- [ ] **Step 5: Commit**

```bash
git add 06_tests/test_ivdon_article_claims.py 08_dissertation/04_article_1_crane_placement/ARTICLE_PASSPORT.md 08_dissertation/04_article_1_crane_placement/EDITORIAL_RESPONSE_MATRIX.md 08_dissertation/04_article_1_crane_placement/TERMINOLOGY.md
git commit -m "test: define ivdon article claim gate"
```

### Task 4: Write the Structured Scientific Manuscript

**Files:**
- Create: `08_dissertation/04_article_1_crane_placement/manuscript/ARTICLE_RU.md`
- Create: `08_dissertation/04_article_1_crane_placement/manuscript/ARTICLE_METADATA.json`
- Create: `08_dissertation/04_article_1_crane_placement/manuscript/EDITOR_RESPONSE_RU.md`
- Modify: `06_tests/test_ivdon_article_claims.py`

**Interfaces:**
- Consumes: `novatorov_v222_result.json`, `external_validation_attestation.json`, `LITERATURE_MATRIX.csv`, `CITATION_PLAN.md`, case manifests, source registers, and the approved spec.
- Produces: final structured Russian text, metadata, table captions, figure captions, and point-by-point editor response.

- [ ] **Step 1: Enable manuscript-specific assertions before writing text**

Remove the Task 3 skip. Assert the manuscript contains these sections in order: introduction, state of the art, materials and methods, mathematical model, algorithm, objects and protocol, results, discussion, novelty and practical significance, limitations, conclusion, literature, References.

- [ ] **Step 2: Run the claim tests and verify they fail**

Run: `python -m unittest 06_tests/test_ivdon_article_claims.py -v`

Expected: FAIL because `ARTICLE_RU.md` does not exist.

- [ ] **Step 3: Write `ARTICLE_RU.md`**

Requirements:

- expand «проект производства работ кранами (ППРк)» in the abstract and first main-text use;
- explain each cited source individually or in claim-specific groups of at most three;
- include the exact equations from the spec and define every symbol and unit;
- describe candidate generation at 2 m and contour sampling up to 5 m;
- state the implemented technical and organizational ranking components without discussing economic factors;
- provide a separate passport and result subsection for each named object;
- describe the independent user reproduction of both retrospective cases as completed and document-backed, while publishing only numerical fields that have explicit locators in the available source registers;
- provide the verified Novatorov numbers and all conditional safety caveats;
- state that the external designer files, final PPRk documents and dated positive characteristic are held by the author and available to the editors on request;
- state that the written, signed and stamped Gritsenko expert conclusion is held by the author and available to the editors on request, without claiming implementation;
- reserve the five new objects for the third article.

- [ ] **Step 4: Write metadata and editor response sources**

`ARTICLE_METADATA.json` must include the approved title, author fields, organization fields, 5-8 keywords, ordered table captions, ordered figure captions, and output filenames. `EDITOR_RESPONSE_RU.md` must quote each editorial criticism only briefly and identify the exact corrective section and evidence.

- [ ] **Step 5: Run manuscript, citation, and evidence gates**

Run:

```powershell
python -m unittest 06_tests/test_ivdon_article_claims.py 06_tests/test_article_citations.py 06_tests/test_article_evidence_hygiene.py 06_tests/test_ivdon_validation_evidence.py -v
```

Expected: PASS, with no skipped manuscript tests.

- [ ] **Step 6: Commit**

```bash
git add 06_tests/test_ivdon_article_claims.py 08_dissertation/04_article_1_crane_placement/manuscript
git commit -m "docs: rewrite ivdon scientific manuscript"
```

### Task 5: Build the DOCX Article and Editorial Response

**Files:**
- Create: `04_experiments/build_ivdon_article_revision.py`
- Create: `06_tests/test_ivdon_article_build.py`
- Create: `output/docx/Статья_Математическая_модель_выбора_башенных_кранов_ИВД_2026.docx`
- Create: `output/docx/Ответ_редакции_Инженерный_вестник_Дона_2026.docx`

**Interfaces:**
- Consumes: `ARTICLE_RU.md`, `ARTICLE_METADATA.json`, `EDITOR_RESPONSE_RU.md`, normalized evidence, verified literature, and approved local article figures.
- Produces: `build_article(article_root: Path, output_path: Path) -> Path` and `build_editor_response(article_root: Path, output_path: Path) -> Path`.

- [ ] **Step 1: Write failing DOCX structure tests**

Tests must open generated files with `python-docx` and assert:

- title and author block exist;
- required sections and all three named objects exist;
- internal identifiers and raw English status are absent;
- equations are present as numbered editable paragraphs or equation images with accessible captions;
- every table and figure caption is referenced in preceding prose;
- response document contains all four editorial issue codes and their corrections;
- core properties do not expose private e-mail.

- [ ] **Step 2: Run the build tests and verify they fail**

Run: `python -m unittest 06_tests/test_ivdon_article_build.py -v`

Expected: FAIL because builder and outputs do not exist.

- [ ] **Step 3: Implement the two builder functions**

Use `python-docx`; preserve the source article only as a read-only reference. Create a new document with consistent Times New Roman typography, editable tables, numbered headings, page numbers, captions, references, and no orphaned headings. Reuse only figures whose source and publication status are recorded; do not add the canceled candidate-grid visualization.

- [ ] **Step 4: Build both DOCX outputs**

Run: `python 04_experiments/build_ivdon_article_revision.py`

Expected: both DOCX paths printed and files reopen successfully.

- [ ] **Step 5: Run the DOCX and content tests**

Run:

```powershell
python -m unittest 06_tests/test_ivdon_article_build.py 06_tests/test_ivdon_article_claims.py 06_tests/test_article_citations.py 06_tests/test_article_evidence_hygiene.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add 04_experiments/build_ivdon_article_revision.py 06_tests/test_ivdon_article_build.py output/docx/Статья_Математическая_модель_выбора_башенных_кранов_ИВД_2026.docx output/docx/Ответ_редакции_Инженерный_вестник_Дона_2026.docx
git commit -m "feat: build revised ivdon article package"
```

### Task 6: Compile PDF and Perform Full Visual QA

**Files:**
- Create: `output/pdf/Статья_Математическая_модель_выбора_башенных_кранов_ИВД_2026.pdf`
- Create: `output/qa/ivdon_article/rendered/page-*.png`
- Create: `output/qa/ivdon_article/QA_REPORT.md`

**Interfaces:**
- Consumes: final article DOCX from Task 5.
- Produces: final PDF, rendered page images, and a zero-defect QA report.

- [ ] **Step 1: Add PDF assertions to `test_ivdon_article_build.py`**

Tests must assert PDF exists, has at least 7 pages, contains extractable title and object names where fonts permit, and is no larger than the journal limit recorded in the current rules. If the official limit has changed, update the rule source and test before rebuilding.

- [ ] **Step 2: Run the PDF assertions and verify they fail**

Run: `python -m unittest 06_tests/test_ivdon_article_build.py -v`

Expected: FAIL because PDF is absent.

- [ ] **Step 3: Compile DOCX to PDF using the bundled document workflow**

Use the documents skill's compiler/render script. Do not overwrite the DOCX. Write the PDF to the exact output path above.

- [ ] **Step 4: Render every PDF page to PNG**

Use Poppler at a resolution sufficient to inspect formulas, table text, figure captions, headers, footers, and references. Store pages under `output/qa/ivdon_article/rendered/`.

- [ ] **Step 5: Inspect every rendered page and write `QA_REPORT.md`**

The report must explicitly cover:

- no clipped or overlapping text;
- no split rows that lose meaning;
- readable formulas and units;
- consistent figure/table numbering;
- no blank unintended pages;
- no internal case IDs;
- complete references and References;
- page count and file size.

If any defect exists, fix the builder and repeat Steps 3-5 until the latest render has zero known defects.

- [ ] **Step 6: Run all article tests**

Run:

```powershell
python -m unittest 06_tests/test_ivdon_validation_evidence.py 06_tests/test_ivdon_article_claims.py 06_tests/test_ivdon_article_build.py 06_tests/test_article_citations.py 06_tests/test_article_evidence_hygiene.py -v
```

Expected: PASS with no skips.

- [ ] **Step 7: Commit**

```bash
git add 06_tests/test_ivdon_article_build.py output/pdf/Статья_Математическая_модель_выбора_башенных_кранов_ИВД_2026.pdf output/qa/ivdon_article
git commit -m "test: verify revised ivdon article output"
```

### Task 7: Final Scientific and Editorial Release Gate

**Files:**
- Modify: `08_dissertation/04_article_1_crane_placement/README.md`
- Modify: `08_dissertation/04_article_1_crane_placement/results/run_registry.csv`
- Modify: `08_dissertation/04_article_1_crane_placement/results/results_summary.csv`
- Verify: all outputs from Tasks 2-6.

**Interfaces:**
- Consumes: tested evidence, manuscript, DOCX, PDF, editor response, and QA report.
- Produces: release index with final hashes and a clear statement of which claims are documentary, author-reported, or expert-assessed.

- [ ] **Step 1: Record final output hashes and provenance**

Add SHA-256 for article DOCX, article PDF, editor response DOCX, normalized evidence files, and the Novatorov source snapshot. Do not hash private evidence into a publicly reversible path; store only the digest and evidence class.

- [ ] **Step 2: Update the article README**

Document how to rebuild, where the three final files are, which evidence was inspected in the workspace, which evidence is confirmed by the author and held outside it, and why the three-object mathematical-model verification is complete while the five-object external validation remains future work.

- [ ] **Step 3: Run the complete relevant test suite**

Run:

```powershell
python -m unittest discover -s 06_tests -p "test_*.py" -v
```

Expected: all tests PASS. Any unrelated pre-existing failure must be documented separately; article-specific tests must all pass.

- [ ] **Step 4: Reopen final artifacts**

Open the final DOCX and PDF after hashing. Confirm they are readable and that the hashes still match.

- [ ] **Step 5: Commit**

```bash
git add 08_dissertation/04_article_1_crane_placement/README.md 08_dissertation/04_article_1_crane_placement/results
git commit -m "docs: finalize ivdon article research package"
```

- [ ] **Step 6: Request final review**

Present the three output files and summarize evidence limits. Do not state that publication is guaranteed; state that the package addresses the recorded editorial objections and is ready for author and supervisor review.

