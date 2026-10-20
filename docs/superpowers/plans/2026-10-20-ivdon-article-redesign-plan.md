# IVD Article Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a submission-ready replacement manuscript for *Inzhenernyj vestnik Dona* that presents the mathematical transition from expert crane-placement decisions to an explainable admissible-area calculation, supported by PPRK-005, PPRK-006, and the independent pilot case PPRK-007.

**Architecture:** Keep raw and potentially sensitive evidence in the ignored private archive, keep traceable hashes and sanitized research records in the article workspace, and compute every reported number through a deterministic research API and runner. Build the manuscript from the verified evidence tables, then generate and visually inspect the journal-formatted DOCX and the response-to-editor package.

**Tech Stack:** Python 3, project dataclasses and geometry/optimizer modules, `unittest`, JSON/CSV/Markdown research records, `python-docx`, bundled LibreOffice/Poppler rendering when available.

**Spec:** `docs/superpowers/specs/2026-10-20-ivdon-article-redesign-design.md`

## Global Constraints

- PPRK-005 and PPRK-006 are retrospective cases and must never be reported as independent validation.
- PPRK-007 is one independent pilot case whose exact status is «принят для реализации»; do not claim actual site implementation without new evidence.
- The third article uses five new independent objects; PPRK-007 is not counted among those five.
- Preserve the first recorded result of every run; changed inputs or algorithms create a new Run ID and version.
- Unknown mandatory inputs produce `BLOCKED`, never an inferred pass.
- The preregistered sensitivity series is 4 m, 2 m, and 1 m; stability requires unchanged project-point status, recommended-coordinate shift no greater than 1 m between the 2 m and 1 m runs, and admissible-area change no greater than 5 percent between those runs.
- Do not claim reduced labor, economic effect, statistical superiority, industry-wide validation, or replacement of the responsible engineer.
- Raw correspondence, signatures, personal data, and confidential drawings stay under `11_backups/article_1_evidence_private/`, which is already ignored by Git.
- Publish addresses and source drawing fragments only after documenting permission; otherwise use a sanitized address and redrawn calculation scheme.
- Journal rules: at least 7 pages, at least 10 references including at least 2 English-language sources, self-citation at most 30%, at most 3 sources in one citation group, BGN transliteration, `Inzhenernyj vestnik Dona`, DOCX size at most 1.5 MB.
- Expand «проект производства работ кранами (ППРк)» independently in the abstract and at first use in the body; do not use the abbreviation in the title or keywords.

## Review Focus

- **Evidence leakage:** private expert correspondence or restricted drawings must not enter Git or the public manuscript; Task 1 adds a repository guard test and Task 10 audits the final package.
- **Validation-status drift:** PPRK-005/006 must remain retrospective and PPRK-007 must remain a single pilot accepted for implementation; Task 2 validates case manifests and Task 9 checks manuscript wording.
- **Metric provenance:** no manuscript number may lack Run ID, source file, unit, and calculation rule; Tasks 5-8 add schema and consistency tests.
- **Post-hoc tuning:** sensitivity thresholds and selection rules must be frozen before result inspection; Task 6 tests immutable protocol fields and Task 8 records all tested grid levels.
- **Journal non-compliance:** grouped citations, unexplained abbreviations, excessive self-citation, missing References, oversized output, or broken layouts must block delivery; Tasks 9-11 implement automated and visual checks.

---

## File Structure

### Research computation

- `05_src/crane_plan/admissible_area.py` - candidate evaluation, reason codes, grid refinement, and article metrics.
- `04_experiments/run_admissible_area_study.py` - deterministic CLI for PPRK-005/006/007 and sensitivity runs.
- `06_tests/test_admissible_area.py` - mathematical and boundary tests.
- `06_tests/test_admissible_area_study.py` - manifest, provenance, determinism, and export tests.

### Article workspace

- `08_dissertation/04_article_1_crane_placement/EDITORIAL_RESPONSE_MATRIX.md` - every editorial criticism and its resolution.
- `08_dissertation/04_article_1_crane_placement/TERMINOLOGY.md` - controlled terms and abbreviation rules.
- `08_dissertation/04_article_1_crane_placement/literature/LITERATURE_MATRIX.csv` - source-by-source comparison.
- `08_dissertation/04_article_1_crane_placement/literature/CITATION_PLAN.md` - claim-to-source mapping and final order.
- `08_dissertation/04_article_1_crane_placement/cases/PPRK-00X/case_manifest.json` - public/sanitized case metadata and status.
- `08_dissertation/04_article_1_crane_placement/cases/PPRK-00X/source_register.csv` - parameter-level provenance.
- `08_dissertation/04_article_1_crane_placement/cases/PPRK-007/INDEPENDENCE_PROTOCOL.md` - evidence chronology and expert status.
- `08_dissertation/04_article_1_crane_placement/protocol/EXPERIMENT_PROTOCOL.md` - frozen run and comparison rules.
- `08_dissertation/04_article_1_crane_placement/results/run_registry.csv` - immutable run index.
- `08_dissertation/04_article_1_crane_placement/results/results_summary.csv` - reported metrics by case.
- `08_dissertation/04_article_1_crane_placement/results/sensitivity.csv` - `h`, `h/2`, `h/4` comparison.
- `08_dissertation/04_article_1_crane_placement/manuscript/ARTICLE.md` - authoritative manuscript text.
- `08_dissertation/04_article_1_crane_placement/manuscript/FIGURE_REGISTER.md` - source, permission, caption, and placement for every figure.
- `08_dissertation/04_article_1_crane_placement/manuscript/CLAIM_EVIDENCE_MATRIX.md` - strong claims and supporting evidence.
- `08_dissertation/04_article_1_crane_placement/submission/RESPONSE_TO_EDITOR.md` - concise response letter.
- `08_dissertation/04_article_1_crane_placement/submission/SUBMISSION_CHECKLIST.md` - final journal checks.

### Generated deliverables

- `output/docx/admissible_area/migin_elsheikh_ivd_revised.docx` - final submission manuscript.
- `output/docx/admissible_area/response_to_editor.docx` - response letter and correction matrix.
- `output/pdf/admissible_area/migin_elsheikh_ivd_revised_review.pdf` - internal render for QA only.

---

### Task 1: Establish the evidence workspace and privacy guard

**Files:**
- Create: `08_dissertation/04_article_1_crane_placement/EDITORIAL_RESPONSE_MATRIX.md`
- Create: `08_dissertation/04_article_1_crane_placement/TERMINOLOGY.md`
- Create: `06_tests/test_article_evidence_hygiene.py`
- Use privately: `11_backups/article_1_evidence_private/`

**Interfaces:**
- Consumes: approved redesign spec.
- Produces: public evidence rules and `assert_public_article_tree_is_sanitized(root: Path) -> None` test helper.

- [ ] **Step 1: Write the failing hygiene tests**

Add tests named `test_private_evidence_directory_is_git_ignored`, `test_public_article_tree_contains_no_email_or_phone`, and `test_editorial_matrix_covers_all_rejection_reasons`. Assert the four rejection reasons are literature review, abbreviation, object description, and unsupported novelty/practical value.

- [ ] **Step 2: Run the tests and verify failure**

Run: `$env:PYTHONPATH=(Resolve-Path '05_src').Path; python -m unittest 06_tests.test_article_evidence_hygiene -v`

Expected: FAIL because the article evidence files and helper do not exist.

- [ ] **Step 3: Create the evidence controls**

Write the editorial matrix with columns `remark`, `old_problem`, `required_evidence`, `new_section`, `status`. Write terminology rules that expand ППРк separately in abstract and body. Create the private directory locally and confirm `git check-ignore` identifies it through the existing `11_backups/*` rule.

- [ ] **Step 4: Run the hygiene tests**

Expected: all Task 1 tests PASS and `git status --short 11_backups/article_1_evidence_private` returns no tracked files.

- [ ] **Step 5: Commit**

Commit only the two public Markdown files and the test with message `docs: establish article evidence controls`.

### Task 2: Build sanitized case manifests and source registers

**Files:**
- Create: `08_dissertation/04_article_1_crane_placement/cases/PPRK-005/case_manifest.json`
- Create: `08_dissertation/04_article_1_crane_placement/cases/PPRK-005/source_register.csv`
- Create: `08_dissertation/04_article_1_crane_placement/cases/PPRK-006/case_manifest.json`
- Create: `08_dissertation/04_article_1_crane_placement/cases/PPRK-006/source_register.csv`
- Create: `08_dissertation/04_article_1_crane_placement/cases/PPRK-007/case_manifest.json`
- Create: `08_dissertation/04_article_1_crane_placement/cases/PPRK-007/source_register.csv`
- Modify: `06_tests/test_article_evidence_hygiene.py`

**Interfaces:**
- Consumes: `02_processed_data/pprk/PPRK-005` through `PPRK-007` and private evidence hashes.
- Produces: manifests with keys `case_id`, `validation_status`, `address_publication_status`, `building`, `site`, `crane`, `critical_operations`, `source_files`; registers with columns `parameter`, `value`, `unit`, `status`, `source_hash`, `locator`, `public_note`.

- [ ] **Step 1: Add failing manifest tests**

Assert exact statuses: `PPRK-005=retrospective`, `PPRK-006=retrospective`, `PPRK-007=independent_pilot_accepted_for_implementation`. Assert every numeric value has a unit and a source locator, and `UNKNOWN` values are not represented as zero.

- [ ] **Step 2: Run tests and verify failure**

Expected: FAIL because manifests are absent.

- [ ] **Step 3: Inventory the three source sets**

Read each existing `project_summary.md`, `source_traceability.md`, `geometry.json`, `cranes.json`, `loads.json`, and `constraints.json`. Record missing evidence as `UNKNOWN`; do not infer coordinates, masses, or crane configurations from an unscaled image.

- [ ] **Step 4: Create the manifests and source registers**

Include address only when `address_publication_status` is `permitted`; otherwise store the sanitized publication form. Reference private evidence by SHA-256 and locator, not by personal correspondence content.

- [ ] **Step 5: Run manifest and hygiene tests**

Expected: PASS for all three cases, with no personal contact data in tracked files.

- [ ] **Step 6: Commit**

Commit manifests, registers, and tests with message `data: add article case evidence manifests`.

### Task 3: Document PPRK-007 independence and expert acceptance

**Files:**
- Create: `08_dissertation/04_article_1_crane_placement/cases/PPRK-007/INDEPENDENCE_PROTOCOL.md`
- Modify: `08_dissertation/04_article_1_crane_placement/cases/PPRK-007/case_manifest.json`
- Modify: `06_tests/test_article_evidence_hygiene.py`

**Interfaces:**
- Consumes: dated private correspondence, original program output, expert credentials, and acceptance evidence.
- Produces: a public chronology whose events are `input_received`, `input_frozen`, `calculation_run`, `scheme_exported`, `sent_to_expert`, `expert_response`, `accepted_for_implementation`.

- [ ] **Step 1: Add a failing chronology test**

Assert every required event has an ISO date, private evidence hash, and non-empty locator. Assert no event claims `implemented_on_site`.

- [ ] **Step 2: Run the chronology test and verify failure**

Expected: FAIL because the protocol is absent.

- [ ] **Step 3: Assemble private evidence without modifying originals**

Copy the authoritative messages, output files, and acceptance document into the ignored private archive. Calculate SHA-256 for each file and record only hashes, dates, roles, and sanitized descriptions publicly.

- [ ] **Step 4: Write the independence protocol**

State what the operator knew, what was hidden, who prepared input data, the exact first output, what was sent to the expert, whether corrections were requested, and that the final status is only «принят для реализации».

- [ ] **Step 5: Run chronology and hygiene tests**

Expected: PASS; tracked files contain no signatures, private addresses, phone numbers, or email text.

- [ ] **Step 6: Commit**

Commit public protocol, manifest update, and tests with message `docs: record PPRK-007 independent pilot evidence`.

### Task 4: Complete the source-by-source literature review matrix

**Files:**
- Create: `08_dissertation/04_article_1_crane_placement/literature/LITERATURE_MATRIX.csv`
- Create: `08_dissertation/04_article_1_crane_placement/literature/CITATION_PLAN.md`
- Create: `06_tests/test_article_citations.py`

**Interfaces:**
- Consumes: `02_processed_data/articles/core_articles_registry.csv` and primary article PDFs.
- Produces: matrix columns `source_id`, `problem`, `method`, `inputs`, `constraints`, `result`, `validation`, `limitation`, `article_claim`, `verified_locator`; citation plan in first-mention order.

- [ ] **Step 1: Add failing citation tests**

Assert at least 10 used sources, at least 2 English-language sources, self-citation ratio at most `0.30`, no citation group larger than 3, and a verified locator for every substantive literature claim.

- [ ] **Step 2: Run tests and verify failure**

Expected: FAIL because matrix and plan do not exist.

- [ ] **Step 3: Fill the matrix from primary texts**

Start with CORE-001, CORE-003, CORE-004 and the other direct crane-placement sources. Record what each study actually contributes and the limitation relative to transforming PPRk drawings and expert constraints into an explainable admissible area.

- [ ] **Step 4: Write the citation plan**

Replace the old `[1-9]` logic with claim-level groups of one to three sources. Fix the intended first-mention order before drafting the manuscript.

- [ ] **Step 5: Run citation tests**

Expected: PASS with no unsupported claim or excessive self-citation.

- [ ] **Step 6: Commit**

Commit the matrix, plan, and tests with message `docs: build source-specific literature review`.

### Task 5: Implement the deterministic admissible-area research API

**Files:**
- Create: `05_src/crane_plan/admissible_area.py`
- Create: `06_tests/test_admissible_area.py`

**Interfaces:**
- Consumes: `ProjectInput`, `CraneConfiguration`, `Point` from `crane_plan.models`.
- Produces: `CandidateEvaluation`, `AdmissibleAreaRun`, `evaluate_candidate(project, config, point) -> CandidateEvaluation`, `calculate_admissible_area(project, config, step_m, refinement_levels, run_id) -> AdmissibleAreaRun`.

- [ ] **Step 1: Write failing mathematical boundary tests**

Cover exact reach boundary, `Q(R)` equality, insufficient capacity by 1 kg, missing rigging mass producing `INPUT_BLOCKED`, insufficient height, base/restricted-zone conflict, route conflict, and deterministic repeated runs. Assert reason codes rather than only boolean status.

- [ ] **Step 2: Run tests and verify failure**

Run: `$env:PYTHONPATH=(Resolve-Path '05_src').Path; python -m unittest 06_tests.test_admissible_area -v`

Expected: FAIL because the module is missing.

- [ ] **Step 3: Define immutable result dataclasses**

`CandidateEvaluation` contains `point`, `passed`, `reason_codes`, `critical_operation_id`, `required_radius_m`, `capacity_margin_kg`, `height_margin_m`, and `source_locators`. `AdmissibleAreaRun` contains run settings, all candidate evaluations, counts by reason, accepted points, area estimate, connected-component count, duration, and input hashes.

- [ ] **Step 4: Implement candidate evaluation by composing existing geometry and catalog rules**

Do not duplicate normative numbers. Import them from `normative.py` or the selected configuration. Preserve all blocking reasons and prohibit load-chart extrapolation.

- [ ] **Step 5: Implement regular grid and local refinement**

Refine only cells whose corner statuses differ. Record each level and step. Keep selection and status deterministic by stable coordinate ordering.

- [ ] **Step 6: Run Task 5 tests and the existing optimizer/normative tests**

Expected: all new tests PASS; existing boundary and optimizer tests remain PASS.

- [ ] **Step 7: Commit**

Commit module and tests with message `feat: add reproducible admissible area calculations`.

### Task 6: Freeze the experiment protocol and result schemas

**Files:**
- Create: `08_dissertation/04_article_1_crane_placement/protocol/EXPERIMENT_PROTOCOL.md`
- Create: `08_dissertation/04_article_1_crane_placement/results/run_registry.csv`
- Create: `08_dissertation/04_article_1_crane_placement/results/results_summary.csv`
- Create: `08_dissertation/04_article_1_crane_placement/results/sensitivity.csv`
- Create: `04_experiments/run_admissible_area_study.py`
- Create: `06_tests/test_admissible_area_study.py`

**Interfaces:**
- Consumes: `calculate_admissible_area(...)` from Task 5 and case manifests from Task 2.
- Produces: CLI `python 04_experiments/run_admissible_area_study.py --case PPRK-005 --step 2 --refinement-levels 2 --run-id <id>` and canonical JSON/CSV exports.

- [ ] **Step 1: Write failing schema and protocol tests**

Assert Run IDs are unique; input hashes, algorithm version, catalog version, step, refinement levels, sensitivity thresholds, units, and timestamps are mandatory; changing an input requires a new Run ID. Assert case status cannot be altered by the runner.

- [ ] **Step 2: Run tests and verify failure**

Expected: FAIL because runner and schemas are missing.

- [ ] **Step 3: Write and sign off the experiment protocol before viewing results**

Fix the primary metrics, the 4 m, 2 m, and 1 m sensitivity series, the recommended-position rule, and the comparison rule. Register the exact stability criteria from Global Constraints and record the author approval date in the protocol.

- [ ] **Step 4: Implement the CLI and canonical exports**

The runner reads one manifest, constructs the project input, invokes Task 5, refuses duplicate Run IDs, writes immutable JSON plus registry rows, and never rewrites an earlier result.

- [ ] **Step 5: Run schema, determinism, and duplicate-ID tests**

Expected: PASS, including a test that a second identical Run ID is rejected without modifying the first file.

- [ ] **Step 6: Commit**

Commit protocol, schemas, runner, and tests with message `research: freeze admissible area experiment protocol`.

### Task 7: Execute and audit the three case studies

**Files:**
- Create: `08_dissertation/04_article_1_crane_placement/results/runs/PPRK-005/<run-id>.json`
- Create: `08_dissertation/04_article_1_crane_placement/results/runs/PPRK-006/<run-id>.json`
- Create: `08_dissertation/04_article_1_crane_placement/results/runs/PPRK-007/<run-id>.json`
- Modify: `08_dissertation/04_article_1_crane_placement/results/run_registry.csv`
- Modify: `08_dissertation/04_article_1_crane_placement/results/results_summary.csv`

**Interfaces:**
- Consumes: frozen protocol, manifests, and Task 6 CLI.
- Produces: one frozen primary run per case and a discrepancy classification for each comparison.

- [ ] **Step 1: Verify all mandatory inputs are confirmed**

Run the manifest validator. Stop a case if a required mass, rigging mass, scale, crane configuration, load chart, height, or boundary remains `UNKNOWN`.

- [ ] **Step 2: Run PPRK-005 and preserve the first output**

Record candidate count, accepted count, area, connected components, reason counts, margins, duration, and project-position status.

- [ ] **Step 3: Run PPRK-006 and preserve the first output**

Record the same metrics using the identical algorithm version and default settings.

- [ ] **Step 4: Register the historical first PPRK-007 output**

Use the original pre-expert output as the primary independent-pilot record. If recomputation is needed for missing metrics, label it as a separate retrospective analytical run and do not replace the historical output.

- [ ] **Step 5: Classify every discrepancy**

Use only: incomplete source, digitization error, normative-version difference, unmodeled organizational condition, mathematical-model defect, software defect, admissible alternative, or insufficient evidence.

- [ ] **Step 6: Audit summary values against run JSON**

Expected: every summary cell resolves to a Run ID, JSON field, unit, and input hash; no manual number exists only in the manuscript.

- [ ] **Step 7: Commit**

Commit sanitized run data and summaries with message `research: record three crane placement case results`.

### Task 8: Run the sensitivity study and generate publication figures

**Files:**
- Modify: `08_dissertation/04_article_1_crane_placement/results/sensitivity.csv`
- Create: `04_experiments/create_admissible_area_figures.py`
- Create: `06_tests/test_admissible_area_figures.py`
- Create: `08_dissertation/04_article_1_crane_placement/manuscript/FIGURE_REGISTER.md`

**Interfaces:**
- Consumes: frozen case input, Task 6 runner, original PPRk fragments, and permissions.
- Produces: figures 1-9 in `output/figures/admissible_area/` plus a registry containing source, permission, caption, dimensions, and manuscript section.

- [ ] **Step 1: Add failing figure and sensitivity tests**

Assert three sensitivity levels exist, thresholds predate runs, each figure has a source and publication status, captions explain all symbols, and no original stamp or unrelated plan area survives cropping.

- [ ] **Step 2: Run the sensitivity series**

Use the preselected case and exact 4 m, 2 m, and 1 m values. Record area, recommended coordinate, accepted-node count, reason distribution, and runtime.

- [ ] **Step 3: Evaluate stability without changing the threshold**

Report pass or fail and explain any instability. Do not rerun with a convenient threshold.

- [ ] **Step 4: Create the conceptual and case figures**

Generate the expert-to-math diagram, set-intersection diagram, algorithm diagram, three case comparisons, PPRK-007 accepted scheme, and sensitivity plot. Use sanitized/redrawn source geometry when publication permission is absent.

- [ ] **Step 5: Run figure tests and inspect every image**

Expected: tests PASS; labels, units, legends, scales, and north arrows are legible; no confidential content is visible.

- [ ] **Step 6: Commit**

Commit the figure generator, tests, registry, and reproducible figure data with message `research: add article sensitivity analysis and figures`.

### Task 9: Write the evidence-backed manuscript

**Files:**
- Create: `08_dissertation/04_article_1_crane_placement/manuscript/ARTICLE.md`
- Create: `08_dissertation/04_article_1_crane_placement/manuscript/CLAIM_EVIDENCE_MATRIX.md`
- Modify: `08_dissertation/04_article_1_crane_placement/EDITORIAL_RESPONSE_MATRIX.md`
- Create: `06_tests/test_article_manuscript.py`

**Interfaces:**
- Consumes: literature matrix, terminology, case manifests, verified results, figure registry, and approved spec.
- Produces: authoritative manuscript source with numbered citations, tables, figures, formulas, limitations, and conclusions.

- [ ] **Step 1: Add failing manuscript compliance tests**

Assert required sections exist; `[1-9]` and citation groups over 3 are absent; ППРк is expanded in abstract and body; retrospective and independent statuses use exact approved wording; every numeric claim maps to `CLAIM_EVIDENCE_MATRIX.md`; forbidden claims are absent.

- [ ] **Step 2: Write the introduction and source-specific review**

Follow the fixed citation plan. End with the research gap, purpose, tasks, and scope.

- [ ] **Step 3: Write the expert-to-mathematics and model sections**

Define all sets, variables, equations, blocking states, algorithm, and distinction between feasibility and optimization. Ensure notation matches Task 5 interfaces.

- [ ] **Step 4: Write materials and methods for all three cases**

Describe addresses only per publication status. Explain PPRK-005/006 as retrospective and PPRK-007 as a single independent pilot accepted for implementation.

- [ ] **Step 5: Write results from the verified tables**

Report all three objects separately, then sensitivity results. Do not write aggregate accuracy across mixed case statuses.

- [ ] **Step 6: Write discussion, limitations, conclusion, and abstract**

Write the abstract last and include actual numbers. State that five new independent objects are reserved for the third article.

- [ ] **Step 7: Run manuscript tests and editorial-matrix audit**

Expected: PASS; each editorial remark maps to a manuscript section and evidence artifact.

- [ ] **Step 8: Commit**

Commit manuscript, claim matrix, editorial matrix, and tests with message `docs: rewrite crane placement article from evidence`.

### Task 10: Generate the journal DOCX and response package

**Files:**
- Modify: `04_experiments/create_admissible_area_research_docs.py`
- Create: `08_dissertation/04_article_1_crane_placement/submission/RESPONSE_TO_EDITOR.md`
- Create: `08_dissertation/04_article_1_crane_placement/submission/SUBMISSION_CHECKLIST.md`
- Create: `output/docx/admissible_area/migin_elsheikh_ivd_revised.docx`
- Create: `output/docx/admissible_area/response_to_editor.docx`
- Modify: `06_tests/test_io_pdf_report.py` only if reusable document checks belong there; otherwise create `06_tests/test_article_docx.py`.

**Interfaces:**
- Consumes: `ARTICLE.md`, tables, figures, response matrix, journal formatting rules.
- Produces: final DOCX files with A4, margins 2/2/3/1.5 cm, Times New Roman 14 pt body at 1.5 spacing, 12 pt single-spaced affiliation/abstract/keywords, Russian Literature and BGN References.

- [ ] **Step 1: Mark the document edit operation before authoring**

Run the documents skill artifact marker exactly once for the two DOCX outputs, then use the bundled Python runtime and document helpers.

- [ ] **Step 2: Add failing structural DOCX tests**

Assert margins, fonts, paragraph spacing, title order, abstract, keywords, editable tables, figure captions, Literature, References, page count at least 7, and file size at most 1.5 MB.

- [ ] **Step 3: Refactor the generator to consume authoritative manuscript data**

Do not retain duplicated hard-coded prose from the rejected version. Load verified tables and figure registry; preserve formulas in editable Word equation form when supported.

- [ ] **Step 4: Generate the revised article and response letter**

The response letter includes the correction matrix and does not argue with the rejection. It states that the manuscript was fully rebuilt.

- [ ] **Step 5: Run structural tests**

Expected: PASS with no broken internal references, unexpanded abbreviation, missing caption, or oversized file.

- [ ] **Step 6: Render every DOCX page to PNG and inspect at 100 percent**

Use the documents skill renderer and bundled LibreOffice. Inspect every page for clipping, broken tables, missing glyphs, detached captions, excessive gaps, and unreadable drawings. Fix and rerender until clean.

- [ ] **Step 7: Commit source and generator changes**

Commit submission Markdown, generator, and tests with message `docs: generate revised IVD submission package`. Generated outputs remain under the repository's output policy.

### Task 11: Perform final scientific and editorial release gate

**Files:**
- Modify: `08_dissertation/04_article_1_crane_placement/submission/SUBMISSION_CHECKLIST.md`
- Create: `08_dissertation/04_article_1_crane_placement/submission/FINAL_AUDIT.md`

**Interfaces:**
- Consumes: final DOCX render, claim matrix, run registry, citation plan, response matrix.
- Produces: signed-off audit with `PASS`, `PASS_WITH_CONDITIONS`, or `BLOCKED` for every gate.

- [ ] **Step 1: Verify evidence and claim integrity**

Trace every number from DOCX to claim matrix, results summary, Run ID, and source hashes. Confirm no result exists only in prose.

- [ ] **Step 2: Verify scientific positioning**

Confirm the manuscript claims mathematical and computational validity, not full external validation; PPRK-007 wording is exactly «принят для реализации»; the third article's five new objects are not reported as completed work.

- [ ] **Step 3: Verify citations and bibliography**

Re-run citation tests, manually compare Literature and References, verify DOI/URLs against primary metadata, and confirm self-citation ratio.

- [ ] **Step 4: Verify privacy and permission**

Run hygiene tests; check every source drawing and address against the figure register and permission status; inspect Git staged content for private evidence.

- [ ] **Step 5: Run the full relevant test suite**

Run: `$env:PYTHONPATH=(Resolve-Path '05_src').Path; python -m unittest discover -s 06_tests -v`

Expected: all tests PASS. Any critical false-positive, missing mandatory input, unsupported claim, or permission gap sets final status to `BLOCKED`.

- [ ] **Step 6: Record final file hashes and release status**

Write SHA-256, page count, file size, test command/output summary, and render-review date to `FINAL_AUDIT.md`.

- [ ] **Step 7: Commit**

Commit checklist and final audit with message `docs: complete IVD submission audit`.
