# Manual Crane Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent user-entered crane configurations that participate in preliminary optimization with mandatory expert-review status.

**Architecture:** A focused user-catalog module owns parsing, validation and atomic persistence. The legacy calculation catalog merges verified and user entries; the GUI is a thin editor over that module, while the V3 verifier continues to classify unknown user cranes as expert-review cases.

**Tech Stack:** Python 3, JSON, pathlib, Tkinter, unittest.

**Spec:** `docs/superpowers/specs/2026-10-21-manual-crane-catalog-design.md`

## Global Constraints

- Never modify the bundled verified catalog from the UI.
- User data must survive application replacement.
- User cranes participate only as `USER_INPUT_EXPERT_REVIEW` evidence.
- The application remains fully offline.

## Review Focus

- Malformed numeric input must produce a clear Russian validation error without corrupting the catalog.
- Duplicate generated IDs must not overwrite an existing configuration.
- A failed write or brochure copy must leave the previous JSON readable.
- Deleting a user crane must never delete bundled brochures or catalog entries.
- A user crane selected by the optimizer must remain blocked from verified release.

---

### Task 1: User catalog domain and persistence

**Files:**
- Create: `05_src/crane_plan/user_cranes.py`
- Create: `06_tests/test_user_cranes.py`

**Interfaces:**
- Produces: `parse_capacity_curve`, `validate_user_crane`, `load_user_cranes`, `save_user_cranes`, `add_user_crane`, `delete_user_crane`.

- [ ] Write failing tests for parsing, validation, unique IDs and atomic round-trip persistence.
- [ ] Run and confirm expected failures.
- [ ] Implement the minimal module.
- [ ] Run focused tests.
- [ ] Commit.
### Task 2: Calculation-catalog merge and expert status

**Files:**
- Modify: `05_src/crane_plan/catalog.py`
- Modify: `05_src/crane_plan/app.py`
- Test: `06_tests/test_geometry_catalog_optimizer.py`
- Test: `06_tests/test_app_engine_integration.py`

**Interfaces:**
- Consumes: Task 1 persisted schema.
- Produces: merged legacy catalog with verified-first ordering.

- [ ] Write failing tests for merge ordering and user-crane calculation selection.
- [ ] Run and confirm expected failures.
- [ ] Merge user configurations during calculation and retain V3 expert-review behavior.
- [ ] Run focused tests.
- [ ] Commit.

### Task 3: Manual editor UI and release metadata

**Files:**
- Modify: `05_src/crane_plan/app.py`
- Modify: `VERSION`
- Modify: `05_src/crane_plan/engine/service.py`
- Modify: `README.md`
- Modify: `07_docs/USER_GUIDE.md`
- Modify: `CHANGELOG.md`
- Test: `06_tests/test_version_consistency.py`

**Interfaces:**
- Consumes: Task 1 catalog API.
- Produces: catalog editor entry point and version 2.2.0 documentation.

- [ ] Write a failing pure-controller test for form conversion and validation feedback.
- [ ] Run and confirm expected failure.
- [ ] Add list, add, delete and brochure actions to the crane catalog UI.
- [ ] Update version and user documentation.
- [ ] Run focused tests, full suite and portable release smoke test.
- [ ] Commit.

