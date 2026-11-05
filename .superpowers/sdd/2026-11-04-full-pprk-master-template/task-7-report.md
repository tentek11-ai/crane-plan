# Task 7 report — calculated PPRk sheets and automatic format

## Result

Implemented bundle-driven planning and rendering of calculated PPRk sheets
without a second engineering-calculation path. The renderer consumes one
canonically bound `ScenarioResult`, uses existing plan/section/SOZR/joint-work
primitives, expands logical graphical references to physical sheets before the
contents page is rendered, and appends those sheets in bundle order.

Delivered behavior:

- deterministic smallest-fitting A3/A2/A1 choice with a 1.8 mm text gate and
  fail-closed A1 overflow;
- content bounds include site/building/logistics/restricted polygons, work
  points, complete crane radii, per-crane SOZR points/contours/routes, and all
  accepted crane/jib/tie/building elevations;
- site-plan planning and fallback drawing share the same padded transform, so
  complete radius strokes remain inside the viewport;
- no inferred below/above-zero engineering stages: in the absence of verified
  stage snapshots the single accepted configuration is rendered unchanged;
- one SOZR/route sheet per crane with confirmed SOZR data and a responsive
  drawing viewport beside the fixed-size point table;
- load schedules split deterministically at 24 rows; 100 active loads produce
  five physical sheets rather than unreadable or clipped output;
- every emitted physical sheet is inserted into bundle parts and contents
  exactly once, with stable designations such as `ГЧ-01.1`;
- production report generation invokes `calculated_sheet_page_map()` from the
  actual explanatory-page count and validates the physical order;
- the existing faded raster/vector PDF underlay path is preserved unchanged.

## Canonical scenario binding

`PPRKContext` now transfers the ordered crane models in addition to existing
protocol hashes and verified traces. `compose_pprk()` stores an immutable
calculation binding containing protocol identity and ordered placement
identity/geometry. Bundle report generation matches that binding against the
supplied scenarios and requires exactly one result. Zero or multiple matches
block output. Positional `scenarios[0]` selection has been removed.

Legacy/synthetic bundles without a binding remain compatible only when exactly
one scenario is supplied.

## TDD evidence

Fix-round RED regressions reproduced:

- first scenario rejected/different while the second is the selected scenario;
- duplicate matching scenarios (ambiguous binding);
- invented below/above-zero sheets and modified tie/height values;
- restricted zone at X=1000 m;
- 200 m building and 200 m accepted crane elevation;
- 100 active loads;
- contents/designation parity after physical-sheet expansion.

Focused verification:

```text
python -m unittest 06_tests.test_pprk_sheets -v
Ran 10 tests
OK

python -m unittest 06_tests.test_pprk_sheets 06_tests.test_pprk_context \
  06_tests.test_pprk_composer 06_tests.test_pprk_text_report \
  06_tests.test_sozr_report 06_tests.test_io_pdf_report -v
Ran 77 tests
OK
```

Full-suite verification:

```text
python -m unittest discover -s 06_tests -v
Ran 340 tests in 120.110s
OK
```

`git diff --check` completed without whitespace errors.

## Visual QA

Generated `tmp/task7-qa-a3-a2-a1.pdf`, rendered it with Poppler at 120 dpi,
and inspected all three pages:

1. A3 load schedule: table, frame and stamp readable; no clipping.
2. A2 vertical section: both accepted crane configurations, jib levels, tie P1,
   elevation table, legend and stamp visible without overlap.
3. A1 site plan: full working-radius circles, site/building/logistics polygons,
   crane symbols, legend and stamp remain inside the drawing viewport. A final
   two-metre world-space padding was added after this inspection.

## Scope and limits

- No load chart, placement, tie, route, SOZR or collision value is recalculated
  by the report layer.
- Explicit verified stage snapshots are not yet present in `PPRKContext`, so
  this task deliberately emits one accepted configuration rather than
  fabricating construction stages.
- Exact reference slinging clips remain Task 8 scope.

## Fix round 2 — fail-closed transfer and measured physical pages

The calculation binding now stores a canonical snapshot and SHA-256 of the
complete `ScenarioResult`. Report generation accepts exactly one non-rejected
scenario with the identical snapshot. Regressions mutate accepted height,
sectors, ties, routes, SOZR data, joint-work schedule and status independently;
every substitution is rejected, as are zero and duplicate matches.

The remaining layout and transfer findings were closed as follows:

- vertical-sheet sizing includes the actual section contour in both axes,
  crane-to-building offsets, crane/jib/tie elevations and the measured tie
  table; 200 m, ±1000 m and remote-axis adversarial inputs fail before output;
- load and SOZR tables use the same ReportLab `Paragraph`/`Table` objects for
  planning and drawing, repeat headers, split into physical sheets by measured
  wrapped height, and fail if one row cannot fit A1;
- the verified danger-zone offset is transferred from protocol evidence through
  `PPRKContext`; canonical bundle rendering never invokes the legacy normative
  helper and blocks when required verified evidence is absent;
- physical sheets are expanded before final contents/reference rendering; the
  stabilized production page map supplies actual designations and PDF pages;
- the template aggregate `CALCULATED_DRAWINGS` resolves to concrete targets,
  while any unknown graphical key raises an explicit error.

Round-2 RED evidence covered canonical substitutions, negative/oversize section
geometry, 100 extremely long load names, 120 long SOZR conditions, forbidden
danger-zone recalculation, page-map parity and unknown graphical references.

Verification after GREEN:

```text
Focused Task 7/context/composer/text/SOZR/IO: Ran 84 tests — OK
Full suite after the final vertical-bound regression: Ran 347 tests in 80.354s — OK
```

Visual QA re-rendered A3/A2/A1 representative sheets at 80 dpi and inspected
them for clipping. A separate long-table packet confirmed five heavily wrapped
load rows fit an A3 page and 24 heavily wrapped SOZR rows fit an A2 page with
the stamp and safety note unobstructed.

## Fix round 3 — external references and exact section transform

Two RED regressions reproduced the remaining review findings:

1. A bundle produced by `compose_pprk()` reached the production physical page
   map and then failed because `appendix.EXTERNAL_DOCUMENT_REGISTER` was
   incorrectly validated as if it were a calculated drawing.
2. A 200 m `max_free_standing_height_m` marker passed A2 planning, and a
   calibrated section with an origin 50,000 pixels from the page also passed
   planning although its rendered coordinates were far outside the sheet.

GREEN changes now resolve only `drawing.*` keys through the physical graphical
page map and fail closed if such a key is missing. `appendix.*` and `external.*`
keys remain visible as stable `ОЖИДАЕТ ВКЛЮЧЕНИЯ` targets until their physical
pages are implemented in Tasks 8–9.

Vertical planning and drawing now use the same `SectionTransformContract` for
calibrated and uncalibrated sections. The preflight includes the building
contour, accepted/required/jib/tie elevations and the rendered free-standing
height marker. Coordinates are transformed with the actual PDF media box,
crop, render scale, calibration origin/axes and selected A3/A2/A1 page size.
Any transformed point outside the printable frame fails before drawing; no
engineering value is recalculated.

Verification evidence:

```text
Two targeted RED tests: appendix ValueError + missing vertical overflow failure
Two targeted GREEN tests: Ran 2 tests — OK
Focused Task 7/context/composer/text/SOZR/IO: Ran 86 tests in 7.075s — OK
Full suite: Ran 349 tests in 81.006s — OK
```

Visual QA regenerated the representative A3/A2/A1 packet and inspected the A2
vertical sheet at 90 dpi. Crane towers, free-standing marker, tie, building,
table, inset and stamp remain inside the frame without overlap.

## Fix round 4 — measure and replay the complete vertical drawing

The previous preflight inspected transformed anchors before the renderer added
paper-space symbols and annotations. The new tests failed on the previous
implementation: a 300 x 200 pt source at render scale 1.5, 0.5 m/px,
origin (450, 270), axes (0, -1) and a 20 x 30 m contour produced a report
instead of failing. At origin (380, 270), the planner chose A2 instead of A1.

Each candidate now captures the actual ReportLab commands and wrapped table at
their final coordinates, with the actual sheet designation. PDFium measures
the stroke and glyph bounds on an in-memory proof, including both cranes,
jibs and counterweights, hooks, ties, building and floors, dimension line
and text, inset, legends, and sheet frame/stamp. The calibrated crop has a
fixed, separately checked image destination. The physical sheet retains the
accepted drawing and replays it directly. The lower edge of a wrapped tie
table must also clear its inset. The nominal elevation-scale guard remains.

GREEN verification with the bundled Python and worktree-local TEMP/TMP:

- Three regressions passed, including an overwide crane label and stamp field.
- Focused sheets/context/composer/text/SOZR/IO suite passed 89 tests in 7.790 s.
- Full unittest discovery passed 352 tests in 80.615 s.
- compileall for 05_src and 06_tests and git diff --check passed.

Poppler previews were inspected for the representative A3/A2/A1 packet and
three vertical sheets. The ordinary uncalibrated section and the calibrated
origin (225, 270) fit A2. Origin (380, 270) uses A1 and its joint-work
dimension and label are visible inside the right frame. At (450, 270), the
planner fails before creating the output file. The existing uncalibrated
A2 layout still places part of the lower note across the mast, as in the
round-3 preview; this is an internal overlap, not a frame overflow.

### Round 4 follow-up — lower-note clearance

The issued A2 PDF reproduced the overlap above. The new regression locates
the full text of all three notes and both 7 mm-wide crane mast rectangles.
It compares the PDF glyph boxes against the mast strokes, including half the
stroke width, and requires at least 3 mm clearance. Before the change both
the joint-work note and the calibration note failed this check.

Uncalibrated sheets now wrap and stack the notes in the checked lower-left
area beside the stamp. The sheet proof and issued output replay the same
text commands. The format planner rejects a candidate if its wrapped block
exceeds the available width or height. Only printed note positions changed.

Poppler visual inspection of the new ordinary A2 showed the notes under the
crane bases and clear of the stamp. All three complete lines were extracted.
Measured minimum stroke-to-text clearances were 16.87, 20.87 and 24.87 mm,
respectively. All four targeted tests and all 90 focused tests passed.
Full unittest discovery passed 353 tests in 81.460 s. compileall for 05_src
and 06_tests and git diff --check passed.

## Fix round 5 — calibrated section-note clearance

RED reproduced the issued A2 with a 300 × 200 pt source, render factor 1.5,
0.5 m/px, vertical axis (0, −1), origin (200, 300) and a 20 × 30 m contour.
The calibration note crossed a mast stroke by 3.133 mm. The passport note
also came within 3 mm of the reserved inset area.

Both section modes now select a free horizontal interval within the footer.
The planner measures the recorded engineering drawing and stamp, expands the
occupied intervals by the required 3 mm plus a one-point printing allowance,
and places complete wrapped notes at 7 pt. The accepted proof and issued
sheet use the same commands. The existing format loop retries larger sheets
when the complete block does not fit. A controlled stroke across the A2 note
area forced promotion to A1. Extending the stroke to the stamp on each
candidate forced rejection even though the stroke stayed inside each frame.

The issued-page regression checks complete note text, font size, every
crane-colored path, the stamp and the inset. A second origin (65, 323) moves
the bases into the footer and forces the block 124.29 mm to the right.
Temporarily ignoring obstacles made that test fail at 0.880 mm.

Poppler previews at 70 dpi showed three clear lines on both requested A2
sheets and on the displaced-base fixture. Minimum measured glyph-to-tower
clearance across all three notes was 52.03 mm at (200, 300), 14.87 mm on the
uncalibrated section, and 3.61 mm at (65, 323). PDF extraction confirmed all
three captions in full. Poppler emitted optional name-map warnings for
Bulgarian, Greek and Thai and produced all three PNGs.

GREEN verification passed 92 focused tests in 8.237 s and all 355 tests
in 80.523 s. Full discovery used the README's worktree-local `05_src` in
`PYTHONPATH` after an initial run omitted it and could not import
`test_admissible_area` and `test_admissible_area_study`. Both modules passed
on the configured run. The 180 dpi footer crops confirmed legibility in
both requested cases. Compileall and whitespace checks passed.

