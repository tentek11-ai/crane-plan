# Task 8 report - exact reference appendices

## Scope and boundary

Implemented `build_slinging_cards(bundle)`, `draw_asset_appendix(canvas,
appendix, assets)`, `AppendixRenderResult`, appendix planning and bundle
expansion, and report insertion after the existing explanatory/calculated
pages. The six Task 1 PNGs and manifest are unchanged. No source PDF is opened,
copied, embedded or packaged by this implementation.

Coordinated scope exception, explicitly authorized by the parent: extended
Task 4/5 context and composer with frozen `PPRKActiveLoad` evidence. Existing
bundles had no load payload. Reading ProjectInput from the appendix renderer
would break the immutable reporting boundary and allow stale data. The context
now copies the original index, name, active flag, source load and rigging masses,
`Load.total_kg`, all three dimensions, operation IDs and confirmation/warnings;
the composer passes the tuple unchanged into the bundle. An optional immutable
sling-field tuple is supported. The current Load model has no independent load
type, sling designation or branch fields, so these are not invented. Missing
legacy payload is distinguished from an explicitly empty active-load tuple.

The public entry point consumes only the bundle. A regression exercises real
ProjectInput -> build_pprk_context -> compose_pprk -> appendix selection and
changes the mutable source project afterwards: published mass stays 1920 kg.

## Selection and release behavior

Task 1 provides one verified 24-scheme slinging board. It remains one entire PNG
on A1 portrait, with no cropping, highlighting, painting, resampling, retouching,
redrawing or content overlays. Explicit conservative name rules select board
number 1 for armature in bundles, 2 for panel formwork and 17 for a concrete
bucket. Matching is normalized and deterministic; other names require a visible
placeholder and blocking issue, without a reference image or phantom sketch.
Inactive loads produce no cards. An inactive-only appendix is removed and its
note reference states that it is not applicable.

Project name, source load mass, rigging mass, full lifted mass, dimensions,
selected scheme, available sling/branch fields, confirmation, operation IDs and
warnings are rendered in a separate generated table below the complete board.
The remaining five categories use A4 portrait and the canonical titles. Included
bundle reference parts determine standard applicability and order. Unimplemented
nonasset/external appendices keep the existing explicit pending behavior.

All selected assets must match the complete canonical manifest record, bundle
identity, SHA-256, PNG dimensions, category, reference_clip source and verified
quality. Missing, changed, wrong-category, altered-metadata and unverified
records are rejected by the drawing boundary. Planning turns failures into
required visible placeholders for preliminary output. Coordination, approved
and production requests with appendix issues fail before creating the PDF.
Expansion preserves verified asset identities on each physical card. No status
or signatures are approved automatically.

## RED evidence

All commands used PowerShell, the bundled Python below, PYTHONPATH=05_src and
TEMP/TMP set to the worktree's tmp/test-temp:

```powershell
$python = 'C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$env:PYTHONPATH = '05_src'
$env:TEMP = Join-Path (Get-Location) 'tmp/test-temp'
$env:TMP = $env:TEMP
& $python -m unittest discover -s 06_tests -p test_pprk_appendices.py -v
```

Before production edits, corrected the test setup's stale graphical references
and observed **Ran 9 tests / FAILED (failures=9)**. Expected assertions were
`exact appendix renderer is missing` and `bundle must bind immutable load
payload`. The initial run before correcting setup also showed 7 failures and 2
errors; it was not treated as valid completed RED evidence. Log:
`tmp/task8-red.txt`.

The second boundary cycle observed **Ran 12 tests / FAILED (failures=1,
errors=1)**: inactive-only references lacked the explicit not-applicable value,
and formatting a missing dimension raised TypeError instead of producing its
required placeholder. Both were corrected (`tmp/task8-red-2.txt`).

Self-review added two more targeted RED tests before their fixes:

```powershell
& $python -m unittest discover -s 06_tests -p test_pprk_appendices.py -k incomplete_dimension -v
# Ran 1 test; FAILED (failures=1): 'slinging' != '' for a two-value dimension tuple
& $python -m unittest discover -s 06_tests -p test_pprk_appendices.py -k expansion_keeps -v
# Ran 1 test; FAILED (failures=1): () != ('slinging',) after physical expansion
```

Logs: `tmp/task8-red-3.txt` and `tmp/task8-red-4.txt`.

## GREEN verification

```powershell
& $python -m unittest discover -s 06_tests -p test_pprk_appendices.py -v
# Ran 14 tests in 17.241s; OK
& $python -m unittest discover -s 06_tests -p 'test_pprk*.py' -v
# Ran 109 tests in 26.240s; OK (final production code)
& $python -m unittest discover -s 06_tests -p test_io_pdf_report.py -v
# Ran 23 tests in 3.450s; OK
& $python -m unittest discover -s 06_tests -v
# Ran 369 tests in 99.779s; OK (final production code)
& $python -m compileall -q 05_src 06_tests
# Exit 0, no output
git diff --check
# Exit 0, no whitespace errors
```

Earlier full runs also passed: 367 tests in 100.297s, and 368 tests in 101.518s.
Final focused PPRk log is `tmp/task8-focused-verified.txt`; focused appendix log
is `tmp/task8-green-final.txt`; final full-suite log
is `tmp/task8-full-verified.txt`. A duplicate full-suite launch initially failed
because its log was already open by the preceding run; it did not execute tests
and was rerun with the unique final log filename. No test failures are omitted.
Git reports the repository's existing LF-to-CRLF normalization notice for the
two extended files; it reports no whitespace defects.

## Page and asset integrity evidence

The generated-PDF test exercises explanatory pages, a real calculated load
schedule and asset appendices together. Four service pages, one explanatory
page, one calculated page and then exactly the applicable reference pages are
present. Every emitted appendix's physical page appears both in the contents
and in explanatory references. The load table uses 1800 + 120 = 1920 kg from
the immutable bundle even when the report's ProjectInput has different values.

Each of the six generated PDF images was extracted and compared against its
real canonical PNG after RGB decoding: exact byte equality and original pixel
dimensions. The slinging board is 6575x6729, and its drawn ratio equals
6575/6729. The tests raise pypdf's 75 MB decompression cap only in the trusted
large-board comparison; production does not change that global library limit.
PDF glyph geometry confirms generated text does not intersect the slinging
image rectangle. The QA file contains exactly six reference pages, no original
71-page PDF, and no additional source pages.

| Asset | Source dimensions | Verified SHA-256 |
|---|---|---|
| slinging | 6575 x 6729 | 1f4690b5bf2ef169c9f5227e6048105c48dd065650969d25ebb6b4330ec16009 |
| fencing | 2020 x 2770 | 1cc4be145b2d5755e8988fc3173d4dd88ee37a709d9f52a607c44e7c7d94a860 |
| safety_signs | 2020 x 3012 | c88d9f3af2fdc37a4f4f78ed680c4e533e356a9c9830bb20611e2a1e06b7885a |
| hand_signals | 2037 x 3020 | 3f52c6b2be5541aac15a3c9e3d5d6c8b53141245b7af5e708c9af307bd43383e |
| storage | 1700 x 2670 | 5849dd82537a609dcb9efd60f1937c6ab74aa2628f19a7f1ab86d538eb0da975 |
| protective_screens | 2025 x 2950 | 39b953ff42bb2d6ebe28d4956e01d256908a44ebcf1962c11beeefbec3f74877 |

## Visual QA

Generated `tmp/task8-qa.pdf` using `tmp/task8_qa.py`, with the PDF skill's
artifact marker run before QA authoring. Rendered all six pages using:

```powershell
& $python tmp/task8_qa.py
pdftoppm -r 50 -png tmp/task8-qa.pdf tmp/task8-qa
```

Inspected all six PNGs with the image tool: full A1 slinging board, complete
independent project table, clear page label, and complete fencing, signs,
signals, armature storage and screen images on A4. No clips, overlaps, changed
content, source frames/stamps or object-specific source details were introduced.
After the final wording/title adjustments, re-rendered all pages and reinspected
the A1 board and fencing page. The geometry script checks every generated glyph
within its physical page bounds; evidence is `tmp/task8-qa-evidence.txt`.

Poppler emitted three nameToUnicode lookup warnings for its non-ASCII installation
path (Bulgarian/Greek/Thai files), returned exit 0 and produced all six PNGs.
The rendered Cyrillic headers and tables are legible. This is an environment
lookup warning, not an omitted PDF rendering failure.

## Self-review and concerns

Reviewed canonical identity checks, report page convergence, deterministic
bundle order, immutable source copies, inactive exclusion, mass semantics,
physical expansion, no text/image overlap, default-compatible dataclass fields,
and unchanged legacy generate_report calls. Corrected the incomplete-dimension
and identity-preservation cases through RED/GREEN cycles. No reviewer or child
agent was spawned.

Selection intentionally covers only the explicit verified scheme matches above.
Other names and ambiguous equipment require developer identification and remain
visible blockers. The entire board is repeated for each supported active load;
this preserves the only approved Task 1 clip and its readable proportions.
The supplied reference artwork's faint strokes are preserved exactly. Missing
sling/branch data is displayed for developer confirmation; the current source
model has no such fields. External/nonasset document attachment work remains
outside Task 8, with its existing pending references preserved.

## Fix round 1 - review findings

Addressed all three Important findings without delegation. Read the receiving
review and systematic debugging skills, traced each faulty data path, reproduced
each finding before its fix, then implemented and verified it independently.

1. `generate_report(bundle=..., document_status=...)` previously merged the
   legacy diagonal overlay onto the already embedded reference image. The
   actual generated-PDF regression observed a rotated status glyph intersecting
   the slinging image (first glyph bounds x=756.00..778.25,
   y=1140.67..1166.46 pt). Status now stays diagonal on pre-appendix pages and
   uses a bounded red footer on reference pages: y=5..13 mm, ending below all
   reference images and the generated tables. The right footer remains reserved
   for page numbering. Status is still present on every page; legacy calls
   retain their original behavior.
2. The calculated load schedule previously read `project.loads` while the card
   read immutable bundle evidence. Planning and measured pagination now use
   `bundle.active_loads`, and every calculated sheet plan retains that frozen
   tuple. Drawing reads the plan, including names, source/rigging/total masses,
   dimensions and lift count. Missing bundle evidence renders a required
   placeholder, never values taken from the current ProjectInput. Public legacy
   table measurement and the nonbundle report path remain compatible.
3. Load confirmation previously copied only `loads_verified`. Context creation
   now checks every related assigned operation/crane against exactly one passed
   authoritative protocol `CAPACITY_INSUFFICIENT` check. Both measured mass and
   limit must be finite nonnegative numbers, units must be exactly `kg`, review
   must not be pending, measured mass must be within capacity, and project
   `Load.total_kg` must match measured lifted mass with absolute tolerance
   **0.001 kg (1 gram), zero relative tolerance**. Every valid measurement is
   transferred as an immutable trace with operation/crane, units, protocol path,
   rule and algorithm version. Matched payloads carry `verified_total_kg` and
   `capacity_evidence`; missing/mismatched evidence creates
   `PPRK_LOAD_EVIDENCE_REQUIRED`, false confirmation, visible warnings and
   unverified input traces. A developer checkbox alone cannot confirm the card.

### Round 1 RED and GREEN

Same bundled Python, PYTHONPATH and worktree-local TEMP/TMP setup as above.
Before production fixes:

```powershell
& $python -m unittest discover -s 06_tests -p test_pprk_appendices.py -k status_is_visible -v
# Ran 1; FAILED (failures=1): actual rotated R glyph intersects reference image
& $python -m unittest discover -s 06_tests -p test_pprk_appendices.py -k every_bundle -v
# Ran 1; FAILED (failures=1): schedule contains 1320, not immutable bundle 1920
& $python -m unittest discover -s 06_tests -p test_pprk_context.py -k load_confirmation -v
# Ran 2; FAILED (failures=6): stale input plus missing/wrong-unit/failed/wrong-crane/nonfinite protocol evidence wrongly confirmed
& $python -m unittest discover -s 06_tests -p test_pprk_context.py -k every_operation -v
# Ran 1; FAILED (failures=2): missing authoritative traces and inconsistent second operation wrongly confirmed
```

The initial status test used pdfplumber's reading-order text for rotated
pre-appendix watermarks and stopped before geometry. Corrected it to extract
status with pypdf and independently check geometry with pdfplumber, then reran
RED and observed the actual intersecting glyph. Logs are
`tmp/task8-fix1-red-status.txt`, `-red-masses.txt`, `-red-evidence.txt` and
`-red-multi.txt`.

After their individual fixes the status and stale-table regressions passed.
The context suite passed 16 tests in 0.017s and appendix suite passed 16 tests
in 20.885s. Initial sheet regression run exposed two fixture assumptions:
`test_one_hundred_loads_are_split_into_listed_physical_sheets` and
`test_long_load_names_split_by_measured_wrapped_height_and_fit_each_sheet`
created synthetic bundles without loads and expected mutable ProjectInput to
supply them. Updated test fixtures to explicitly freeze the intended source
loads into the bundle, preserving all original split/fit assertions. The
50-load contents fixture was updated for the same immutable boundary.

```powershell
& $python -m unittest discover -s 06_tests -p 'test_pprk*.py' -v
# Ran 114 tests in 30.350s; OK
& $python -m unittest discover -s 06_tests -p test_io_pdf_report.py -v
# Ran 23 tests in 3.239s; OK
& $python -m unittest discover -s 06_tests -v
# Ran 374 tests in 103.895s; OK
& $python -m compileall -q 05_src 06_tests
# Exit 0
git diff --check
# Exit 0; only existing LF-to-CRLF notices
```

Logs: `tmp/task8-fix1-focused.txt`, `tmp/task8-fix1-io.txt`,
`tmp/task8-fix1-full.txt`.

### Round 1 physical and visual QA

Generated a real 12-page report with four service pages, explanatory page,
calculated schedule and all six canonical references, passing the actual
`document_status='ПРЕДВАРИТЕЛЬНО - НЕ ДЛЯ ПРОИЗВОДСТВА РАБОТ'` argument.
`tmp/task8_fix1_qa.py` compares all six extracted images to the canonical PNGs
after the status operation and checks every generated glyph against each image
rectangle. Evidence in `tmp/task8-fix1-qa.txt`:

```text
page 7 slinging status visible; image pixel-identical; glyph intersections = 0
page 8 fencing status visible; image pixel-identical; glyph intersections = 0
page 9 safety_signs status visible; image pixel-identical; glyph intersections = 0
page 10 hand_signals status visible; image pixel-identical; glyph intersections = 0
page 11 storage status visible; image pixel-identical; glyph intersections = 0
page 12 protective_screens status visible; image pixel-identical; glyph intersections = 0
Schedule + appendix: immutable 1920 kg; stale project 1320 kg excluded
Pages: 12
```

Rendered pages 7..12 with Poppler at 55 dpi and inspected all six PNGs. The red
status footer is outside each canonical clip and outside the slinging project
table. Complete artwork, readable page numbering and proportions are preserved.
A raster footer check found 408 red status pixels on every rendered reference
page. Poppler returned exit 0 with the same three environment-specific Unicode
installation path lookup warnings documented above; all PNGs were produced.

Round-1 self-review checked that the renderer has no mutable project fallback
for bundle load tables, mass checks use the authoritative protocol instead of
unrelated engine evidence, all assigned operations must match, old input traces
lose verified status on mismatch, footer bounds avoid all canonical rectangles,
and existing legacy report/status APIs stay compatible. No new scheme names,
source assets, project persistence changes or approval behavior were added.
