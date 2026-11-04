# Section Coordinate System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make vertical-section calibration and building markup invariant under zoom and scrolling.

**Architecture:** Put document/view conversion and image sizing in pure helpers, then make the Tk handlers use those helpers consistently. Persist only document/world coordinates.

**Tech Stack:** Python 3, Tkinter Canvas, Pillow, unittest.

**Spec:** `docs/superpowers/specs/2026-10-21-section-coordinate-system-design.md`

## Global Constraints

- Existing project files must remain compatible.
- Crop rebasing semantics remain unchanged.
- Zoom and scroll must never mutate section geometry.

## Review Focus

- Zoom above 100% must resize both the PDF image and markup.
- A click after horizontal or vertical scroll must land under the cursor.
- Repeated zoom in/out must preserve source coordinates.
- A zero or invalid scale must be rejected.
- Plan rendering must not regress when the shared sizing helper is adopted.

---

### Task 1: Pure viewport transforms

**Files:**
- Modify: `05_src/crane_plan/pdf_workspace.py`
- Test: `06_tests/test_io_pdf_report.py`

**Interfaces:**
- Produces: `display_size(source_size, scale)` and document/view conversion helpers.

- [ ] Write failing tests for enlargement, scroll-aware click conversion and round-trip invariance.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Implement the minimal pure helpers.
- [ ] Run the focused tests and the PDF workspace test module.
- [ ] Commit.
### Task 2: Vertical-section integration

**Files:**
- Modify: `05_src/crane_plan/app.py`
- Test: `06_tests/test_section_viewport.py`

**Interfaces:**
- Consumes: Task 1 viewport helpers.

- [ ] Write failing handler-level regression tests using a deterministic fake Canvas.
- [ ] Run them and confirm markers differ from saved points before the fix.
- [ ] Use Canvas coordinates for all clicks and resize images at every zoom factor.
- [ ] Run focused tests and the non-GUI suite.
- [ ] Commit.

