# CranePlan 2.1 Calculation Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new operation-centric, deterministic and independently verifiable calculation core that can become the stable foundation for CranePlan 2.2–3.0.

**Architecture:** Add a focused `crane_plan.engine` package alongside the current application. The engine accepts only the new `ProjectV3` schema, evaluates every lifting operation against hard constraints, and emits structured evaluations, an independent verification report and a reproducible calculation protocol. Existing UI and legacy project files remain untouched in this plan; integration follows after the core interfaces are stable.

**Tech Stack:** Python 3.12, standard-library dataclasses/enums/json/hashlib, existing `unittest` suite and existing `crane_plan.geometry`/`crane_plan.normative` pure functions. No new runtime dependency in version 2.1.

**Spec:** `docs/superpowers/specs/2026-10-20-craneplan-3-0-calculation-core-design.md`

## Global Constraints

- Do not preserve or migrate schema versions 1–2; version 3 input uses `schema_version = 3`.
- Do not change the existing Tkinter workflow, reports or `optimizer.py` in this plan.
- Safety conditions are hard constraints, never weighted score penalties.
- Missing mandatory data produces `INPUT_BLOCKED`; it is never replaced with zero or a hidden default.
- Any default assumption is represented explicitly in data with source kind `ASSUMPTION`.
- Capacity between chart radii uses the value at the next larger radius.
- Equality at a passport or geometric limit is accepted within `EPS = 1e-6`.
- All public engine dataclasses use SI units in names (`_m`, `_kg`, `_s`, `_deg`).
- Every task follows test-first development and commits only its own files.
- Preserve all unrelated dirty-tree changes.

## Review Focus

- NaN, infinity, negative mass and non-positive dimensions must block input; Task 1 tests each class.
- Empty, unsorted, duplicate-radius or increasing-capacity load charts must be rejected; Task 2 tests each case.
- An operation referencing an unknown stage or containing a zero lift count must block input; Task 3 tests both cases.
- A radius exactly on a capacity point and a load exactly equal to `Q(R)` must pass; Task 4 pins both boundaries.
- Protocol hashes must remain identical across dictionary ordering and repeated runs; Task 7 tests deterministic serialization.

---

## File Structure

Create:

- `05_src/crane_plan/engine/__init__.py` — stable public exports for the new engine.
- `05_src/crane_plan/engine/domain.py` — version 3 domain dataclasses and input validation.
- `05_src/crane_plan/engine/catalog.py` — versioned crane catalog and conservative capacity lookup.
- `05_src/crane_plan/engine/operations.py` — standard-load conversion and operation validation.
- `05_src/crane_plan/engine/constraints.py` — reason codes and deterministic candidate evaluation.
- `05_src/crane_plan/engine/verification.py` — independent solution verification.
- `05_src/crane_plan/engine/protocol.py` — canonical serialization, hashes and run protocol.
- `05_src/crane_plan/engine/service.py` — version 2.1 orchestration API.
- `06_tests/test_engine_domain.py`
- `06_tests/test_engine_catalog.py`
- `06_tests/test_engine_operations.py`
- `06_tests/test_engine_constraints.py`
- `06_tests/test_engine_solution.py`
- `06_tests/test_engine_verification.py`
- `06_tests/test_engine_protocol.py`
- `06_tests/test_engine_service.py`
- `02_processed_data/cranes/crane_configurations_v3.json` — source-specific configurations used by the new core.

Modify only after the producing task is complete:

- `05_src/crane_plan/engine/__init__.py` — export newly stable interfaces.
- `README.md` — document the parallel version 2.1 engine and its test command.
- `07_docs/changelog.md` — record the calculation-core milestone.

## Task 1: Version 3 Domain Model and Input Validation

**Files:**

- Create: `05_src/crane_plan/engine/__init__.py`
- Create: `05_src/crane_plan/engine/domain.py`
- Create: `06_tests/test_engine_domain.py`

**Interfaces:**

- Produces: `Point2D`, `SourceKind`, `SourceLocator`, `LiftEndpoint`, `LoadSpec`, `ConstructionStage`, `LiftingOperation`, `SiteGeometry`, `ProjectV3`, `InputIssue`, `validate_project(project: ProjectV3) -> tuple[InputIssue, ...]`.
- Later tasks rely on `ProjectV3.schema_version == 3`, immutable source records and stable operation/stage identifiers.

- [ ] **Step 1: Write failing domain validation tests**

Add tests named:

- `test_valid_project_has_no_input_issues`
- `test_nan_infinity_and_negative_mass_are_blocked`
- `test_non_positive_load_dimension_is_blocked`
- `test_duplicate_operation_and_stage_ids_are_blocked`
- `test_missing_source_locator_is_blocked_unless_assumption`

Assert reason codes exactly: `NON_FINITE_VALUE`, `NEGATIVE_MASS`, `NON_POSITIVE_DIMENSION`, `DUPLICATE_ID`, `SOURCE_REQUIRED`.

- [ ] **Step 2: Run the domain tests and verify failure**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path '.\05_src').Path
python -m unittest 06_tests.test_engine_domain -v
```

Expected: import failure for `crane_plan.engine.domain`.

- [ ] **Step 3: Implement immutable domain records**

Use frozen dataclasses. Define `SourceKind` values `PASSPORT`, `NORMATIVE`, `PROJECT`, `ASSUMPTION`, `MEASURED`. `LoadSpec.total_kg` returns `load_kg + rigging_kg`; `LoadSpec.largest_dimension_m` returns the maximum dimension. `ProjectV3` contains `project_id`, `name`, `city`, `stages`, `site`, `operations`, `normative_profile_id`, `catalog_version`, and `schema_version=3`.

- [ ] **Step 4: Implement `validate_project`**

Return all issues in deterministic order. Do not raise on user input. Each `InputIssue` contains `code`, `path`, `message`, and `blocking=True`.

- [ ] **Step 5: Run domain tests**

Expected: all `test_engine_domain` tests pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add 05_src/crane_plan/engine/__init__.py 05_src/crane_plan/engine/domain.py 06_tests/test_engine_domain.py
git commit -m "feat: add version 3 calculation domain"
```

## Task 2: Source-Specific Crane Catalog and Conservative Capacity

**Files:**

- Create: `05_src/crane_plan/engine/catalog.py`
- Create: `06_tests/test_engine_catalog.py`
- Create: `02_processed_data/cranes/crane_configurations_v3.json`
- Modify: `05_src/crane_plan/engine/__init__.py`

**Interfaces:**

- Consumes: `SourceLocator` from Task 1.
- Produces: `CapacityPoint`, `CraneConfigurationV3`, `CatalogIssue`, `load_catalog_v3(path: str | Path) -> tuple[CraneConfigurationV3, ...]`, `validate_capacity_curve(config: CraneConfigurationV3) -> tuple[CatalogIssue, ...]`, `conservative_capacity_kg(config: CraneConfigurationV3, radius_m: float) -> float`.

- [ ] **Step 1: Write failing catalog tests**

Add tests named:

- `test_capacity_at_exact_chart_radius_uses_exact_value`
- `test_capacity_between_points_uses_next_larger_radius_value`
- `test_capacity_outside_terminal_radius_is_zero`
- `test_empty_unsorted_duplicate_and_increasing_curves_are_rejected`
- `test_catalog_requires_document_page_and_sha256`

Use a curve `((25.0, 5900.0), (30.0, 5200.0))`; assert `conservative_capacity_kg(config, 28.75) == 5200.0`, not `5550.0`.

- [ ] **Step 2: Run catalog tests and verify failure**

Expected: import or missing-interface failure.

- [ ] **Step 3: Implement catalog dataclasses and validation**

`CraneConfigurationV3` contains identifiers for model and configuration, mounted jib length, maximum free-standing hook height, capacity points, allowed jib lengths, allowed tower section heights and source locator. Reject non-increasing radii and capacity increases with reason codes `CURVE_EMPTY`, `RADIUS_ORDER_INVALID`, `RADIUS_DUPLICATE`, `CAPACITY_NOT_MONOTONE`, `SOURCE_INCOMPLETE`.

- [ ] **Step 4: Implement conservative lookup**

Accept equality within `EPS`. For an intermediate radius, return the capacity of the first chart point whose radius is greater than or equal to the request. Return zero outside the terminal radius.

- [ ] **Step 5: Create the initial v3 catalog file**

Include only configurations whose local manufacturer brochure, page locator and SHA-256 are available. Preserve `130 EC-B 6` priority; do not invent missing configurations. Invalid entries must make `load_catalog_v3` raise `ValueError` containing all catalog issue codes.

- [ ] **Step 6: Run catalog tests and the existing catalog tests**

Run:

```powershell
python -m unittest 06_tests.test_engine_catalog 06_tests.test_geometry_catalog_optimizer.CatalogTests -v
```

Expected: new tests pass; legacy behavior remains unchanged because the legacy module is untouched.

- [ ] **Step 7: Commit Task 2**

```powershell
git add 05_src/crane_plan/engine/catalog.py 05_src/crane_plan/engine/__init__.py 06_tests/test_engine_catalog.py 02_processed_data/cranes/crane_configurations_v3.json
git commit -m "feat: add traceable conservative crane catalog"
```

## Task 3: Operation Construction and Standard Loads

**Files:**

- Create: `05_src/crane_plan/engine/operations.py`
- Create: `06_tests/test_engine_operations.py`
- Modify: `05_src/crane_plan/engine/__init__.py`

**Interfaces:**

- Consumes: domain records from Task 1 and `02_processed_data/loads/standard_monolithic_loads.json`.
- Produces: `OperationRequest`, `load_standard_loads(path: str | Path) -> dict[str, LoadSpec]`, `build_operations(requests: Iterable[OperationRequest], load_library: Mapping[str, LoadSpec]) -> tuple[LiftingOperation, ...]`, `validate_operations(project: ProjectV3) -> tuple[InputIssue, ...]`.

- [ ] **Step 1: Write failing operation tests**

Cover:

- standard load values and sources are preserved;
- user overrides create an explicit `PROJECT` source and do not mutate the library;
- an unknown load ID returns `UNKNOWN_LOAD_TEMPLATE`;
- an unknown stage returns `UNKNOWN_STAGE`;
- zero or negative lift count returns `INVALID_LIFT_COUNT`;
- operation identifiers are deterministic for identical requests.

- [ ] **Step 2: Run operation tests and verify failure**

Expected: missing module or interface.

- [ ] **Step 3: Implement standard-load loading and operation construction**

Do not add implicit destinations. Every request supplies source and destination coordinates, destination elevation and stage ID. Default rigging height is 1.5 m only when stored as a `SourceKind.ASSUMPTION` locator.

- [ ] **Step 4: Run operation and domain tests**

Expected: both test modules pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add 05_src/crane_plan/engine/operations.py 05_src/crane_plan/engine/__init__.py 06_tests/test_engine_operations.py
git commit -m "feat: build traceable lifting operations"
```

## Task 4: Deterministic Placement Constraints

**Files:**

- Create: `05_src/crane_plan/engine/constraints.py`
- Create: `06_tests/test_engine_constraints.py`
- Modify: `05_src/crane_plan/engine/__init__.py`

**Interfaces:**

- Consumes: `ProjectV3`, `LiftingOperation`, `CraneConfigurationV3`, `conservative_capacity_kg` and existing pure geometry/normative functions.
- Produces: `ConstraintCode`, `OperationEvaluation`, `PlacementEvaluation`, `evaluate_operation(operation, crane_point, config, project) -> OperationEvaluation`, `evaluate_placement(project, stage_id, crane_point, config) -> PlacementEvaluation`.

- [ ] **Step 1: Write failing boundary and rejection tests**

Cover exact reason codes:

- `INPUT_BLOCKED`
- `BASE_OUTSIDE_SITE`
- `BASE_INSIDE_BUILDING`
- `RESTRICTED_ZONE_CONFLICT`
- `BASE_CLEARANCE_CONFLICT`
- `REACH_EXCEEDED`
- `CAPACITY_INSUFFICIENT`
- `HEIGHT_INSUFFICIENT`
- `ROUTE_CONFLICT`
- `DANGER_ZONE_CONFLICT`
- `CONFIGURATION_UNSUPPORTED`

Add explicit tests that a radius exactly equal to the terminal jib radius passes and a load exactly equal to `Q(R)` passes with zero capacity margin.

- [ ] **Step 2: Run constraint tests and verify failure**

Expected: missing interface.

- [ ] **Step 3: Implement per-operation evaluation**

Calculate and store radius, available capacity, capacity margin, utilization, required hook height, height margin and reason codes. Evaluate source-to-destination route segments against restricted zones. Preserve every failure instead of returning after the first one, except for `INPUT_BLOCKED`.

- [ ] **Step 4: Implement placement aggregation**

Evaluate every operation active in the requested stage. A placement passes only when every operation passes. Report the critical operation IDs for minimum capacity margin and minimum height margin.

- [ ] **Step 5: Run constraint tests plus legacy admissible-area tests**

Run:

```powershell
python -m unittest 06_tests.test_engine_constraints 06_tests.test_admissible_area -v
```

Expected: all pass; no legacy regression.

- [ ] **Step 6: Commit Task 4**

```powershell
git add 05_src/crane_plan/engine/constraints.py 05_src/crane_plan/engine/__init__.py 06_tests/test_engine_constraints.py
git commit -m "feat: evaluate every lifting operation"
```

## Task 5: Version 2.1 Candidate and Solution Types

**Files:**

- Modify: `05_src/crane_plan/engine/domain.py`
- Create: `06_tests/test_engine_solution.py`
- Modify: `05_src/crane_plan/engine/__init__.py`

**Interfaces:**

- Consumes: identifiers from Tasks 1–4.
- Produces: `CranePlacementV3`, `OperationAssignment`, `StageSolutionV3`, `ProjectSolutionV3`.

- [ ] **Step 1: Write failing solution integrity tests**

Assert that:

- every operation is assigned exactly once;
- assignments reference existing operations and placements;
- duplicate placement IDs are blocked;
- a stage solution cannot claim a different stage;
- serialization order is deterministic.

- [ ] **Step 2: Run tests and verify failure**

- [ ] **Step 3: Implement solution records and `validate_solution_structure`**

Signature:

```python
def validate_solution_structure(project: ProjectV3, solution: ProjectSolutionV3) -> tuple[InputIssue, ...]:
    ...
```

Do not add optimization scores in version 2.1.

- [ ] **Step 4: Run solution and domain tests**

Expected: all pass.

- [ ] **Step 5: Commit Task 5**

```powershell
git add 05_src/crane_plan/engine/domain.py 05_src/crane_plan/engine/__init__.py 06_tests/test_engine_solution.py
git commit -m "feat: define version 3 solution records"
```

## Task 6: Independent Solution Verifier

**Files:**

- Create: `05_src/crane_plan/engine/verification.py`
- Create: `06_tests/test_engine_verification.py`
- Modify: `05_src/crane_plan/engine/__init__.py`

**Interfaces:**

- Consumes: project, catalog mapping and solution records.
- Produces: `VerificationStatus`, `VerificationCheck`, `VerificationReport`, `verify_solution(project: ProjectV3, configurations: Mapping[str, CraneConfigurationV3], solution: ProjectSolutionV3) -> VerificationReport`.

- [ ] **Step 1: Write failing verifier independence tests**

Cover:

- a valid solution returns `VALID`;
- missing source evidence returns `EXPERT_REVIEW_REQUIRED`;
- an explicit permitted protective measure returns `VALID_WITH_CONDITIONS`;
- a corrupted coordinate or configuration returns `INVALID`;
- the verifier catches a load changed after candidate generation;
- monkeypatching `constraints.evaluate_placement` to return pass does not affect verification.

- [ ] **Step 2: Run verifier tests and verify failure**

- [ ] **Step 3: Implement independent verification**

The module may reuse low-level pure capacity, geometry and normative functions, but must not call `evaluate_placement` or consume `PlacementEvaluation`. Every `VerificationCheck` records code, pass/fail, measured value, limit, units, operation ID, crane ID and source locators.

- [ ] **Step 4: Run verifier, constraint and catalog tests**

Expected: all pass.

- [ ] **Step 5: Commit Task 6**

```powershell
git add 05_src/crane_plan/engine/verification.py 05_src/crane_plan/engine/__init__.py 06_tests/test_engine_verification.py
git commit -m "feat: independently verify crane solutions"
```

## Task 7: Reproducible Calculation Protocol

**Files:**

- Create: `05_src/crane_plan/engine/protocol.py`
- Create: `06_tests/test_engine_protocol.py`
- Modify: `05_src/crane_plan/engine/__init__.py`

**Interfaces:**

- Consumes: project, catalog, placement evaluations, solution and verification report.
- Produces: `CalculationProtocolV3`, `canonical_json(value: object) -> str`, `sha256_hex(value: object) -> str`, `build_protocol(...) -> CalculationProtocolV3`, `save_protocol(path: str | Path, protocol: CalculationProtocolV3) -> Path`.

- [ ] **Step 1: Write failing protocol tests**

Cover:

- identical hashes across dictionary ordering;
- identical hashes on repeated runs with fixed `run_id` and `created_at`;
- changed load mass changes the input hash;
- algorithm, normative profile and catalog versions are mandatory;
- source locators and rejected reason counts are serialized;
- NaN and infinity are rejected before serialization.

- [ ] **Step 2: Run protocol tests and verify failure**

- [ ] **Step 3: Implement canonical JSON and protocol records**

Use sorted keys, UTF-8, compact separators and `allow_nan=False`. Runtime duration and timestamp are stored but excluded from the deterministic input hash.

- [ ] **Step 4: Run protocol tests twice**

Expected: both runs pass with identical expected hashes.

- [ ] **Step 5: Commit Task 7**

```powershell
git add 05_src/crane_plan/engine/protocol.py 05_src/crane_plan/engine/__init__.py 06_tests/test_engine_protocol.py
git commit -m "feat: add reproducible calculation protocol"
```

## Task 8: Version 2.1 Engine Service

**Files:**

- Create: `05_src/crane_plan/engine/service.py`
- Create: `06_tests/test_engine_service.py`
- Modify: `05_src/crane_plan/engine/__init__.py`

**Interfaces:**

- Consumes: all interfaces from Tasks 1–7.
- Produces: `EngineRequestV21`, `EngineResultV21`, `run_engine_v21(request: EngineRequestV21) -> EngineResultV21`.

- [ ] **Step 1: Write failing end-to-end service tests**

Test three fixtures:

1. a valid one-crane project returns placement evaluations, a `VALID` verification and a protocol;
2. insufficient capacity returns no accepted solution and reports `CAPACITY_INSUFFICIENT` with measured capacity and required mass;
3. incomplete source evidence returns `EXPERT_REVIEW_REQUIRED` and cannot be promoted to `VALID` by the service.

Also assert that the service is deterministic for identical candidate coordinates and configuration order.

- [ ] **Step 2: Run service tests and verify failure**

- [ ] **Step 3: Implement the orchestration service**

`EngineRequestV21` supplies a validated project, catalog, explicit candidate coordinates and optional proposed solution. Version 2.1 does not search or rank coordinates; those belong to version 2.2. If no proposed solution is supplied, the service returns evaluations only. If supplied, it invokes independent verification and builds the protocol.

- [ ] **Step 4: Run all new engine tests**

```powershell
python -m unittest discover -s 06_tests -p "test_engine_*.py" -v
```

Expected: all engine tests pass.

- [ ] **Step 5: Run the full existing suite**

```powershell
python -m unittest discover -s 06_tests -v
```

Expected: all non-GUI tests pass. GUI tests must be run with the portable Tk runtime; a missing `init.tcl` is an environment failure and must not be reported as an application pass.

- [ ] **Step 6: Commit Task 8**

```powershell
git add 05_src/crane_plan/engine/service.py 05_src/crane_plan/engine/__init__.py 06_tests/test_engine_service.py
git commit -m "feat: expose version 2.1 calculation service"
```

## Task 9: Documentation and Release Gate

**Files:**

- Modify: `README.md`
- Modify: `07_docs/changelog.md`

**Interfaces:**

- Consumes: stable `run_engine_v21` API from Task 8.
- Produces: documented developer entry point, known limitations and version 2.1 acceptance record.

- [ ] **Step 1: Document the new core**

State explicitly that version 2.1 provides deterministic evaluation and independent verification, but not adaptive coordinate search, Pareto ranking, scheduling or UI integration.

- [ ] **Step 2: Record verification evidence**

Add the exact test commands, pass counts, Python version and date. Do not claim GUI verification unless run with a functional Tk runtime.

- [ ] **Step 3: Run documentation and source checks**

```powershell
rg -n "T[B]D|T[O]DO|F[I]XME|P[L]ACEHOLDER" 05_src/crane_plan/engine 06_tests/test_engine_*.py README.md 07_docs/changelog.md
python -m compileall -q 05_src/crane_plan/engine
git diff --check
```

Expected: no placeholders, compilation succeeds, no whitespace errors.

- [ ] **Step 4: Run the final engine and full suites**

Expected: engine tests pass; full-suite result is recorded accurately.

- [ ] **Step 5: Commit Task 9**

```powershell
git add README.md 07_docs/changelog.md
git commit -m "docs: record CranePlan 2.1 engine milestone"
```

## Completion Criteria

Version 2.1 is complete only when:

- all active operations are evaluated individually;
- the new catalog uses conservative lookup and traceable sources;
- every rejection has a stable reason code and measured values;
- proposed solutions are independently verified;
- deterministic protocol JSON is generated;
- all new engine tests pass;
- legacy non-GUI tests show no regression;
- limitations are documented without overstating readiness for PPRk release.
