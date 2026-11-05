# Final integration hardening — implementation and verification report

Base before hardening: `dff1c0444ae43f5388f05dca9ecf16ddb4bc90f7`.
User-requested pause checkpoint: `92a00fc` (retained; not amended).
Completion is a new commit over that checkpoint. No merge/push/publication or delegation.

## Nine findings

1. **Vertical geometry** — section mast/jib axes use `jib_level_m`; the section, joint plan and schedule share the actual separation check. The 32.4/42.4 m fixture prints `10.0 = 2.0 + 8.0`, including the minimum permitted clearance. Physical glyphs and both 7 mm mast rectangles are checked against their verified elevations; inconsistent schedule separation fails closed.
2. **Mandatory documents** — `crane_passport`, `foundation_project`, `erection_project` are required independently of the record's `required` flag. Tie and screen project IDs are conditional. The immutable bundle records the required ID set, and final assembly reapplies it to freshly read records. A file that disappears after preparation cannot pass as optional; prior output remains unchanged.
3. **Screen evidence** — passed authoritative `DANGER_ZONE_PROTECTED` evidence carries its mitigation type through context. `PROTECTIVE_SCREEN` includes the canonical protective-screen sheet and requires `protective_screen_project`. Missing project or clip blocks advanced status. Physical preliminary PDF contains the screen image and pending project row.
4. **Regulations** — frozen records preserve all eight CSV fields and explicitly stated validity dates. Required records appear by identifier/name in the basis section, including editions, locators, status and source notes. Exact issue date is persisted and editable; missing/invalid date, unverified status and out-of-date records block coordination/approval/production. No actual registry record was promoted or invented. Implementation/catalog/reference statuses are not legal verification.
5. **Forbidden references** — release inputs, final PDF text, Info metadata and XMP streams are scanned before atomic publication. The same validation inspects imported sources. The public legacy `generate_report(bundle=None)` also validates inputs and stages/scans its physical PDF before replacement; its compatibility signature and page selection are preserved. Physical Info/XMP contamination and forbidden project code fail while retaining old output. Existing atomic writes, source revision checks and sidecar rollback remain.
6. **Rigging completeness** — `Load` has defaulted typed fields for rigging type, branch count, sling identification, capacity, documentary evidence and explicit confirmation; the load editor reads/writes them. A mass checkbox does not confirm missing rigging. Context requires these fields, finite sufficient capacity and matching authoritative capacity evidence. A physical production card with complete evidence says confirmed and has no missing marker; preliminary cards remain explicitly pending. Legacy projects load empty/unconfirmed, without rewriting their source JSON.
7. **Variant identity** — immutable calculation binding carries `scenario_index` and protocol run identity; every calculated page prints the canonical number plus protocol/run and result digest prefix. Joint sheets receive that number, not constant 1. Sheet designations stay separate. Physical nonfirst-variant PDF checks all nine calculated pages.
8. **One set of requisites** — frozen release-card requisites feed an isolated effective project used by measured planning and all legacy drawing primitives. Titles, stamps, SOZR and text use the same values; original mutable project remains unchanged. Physical extraction excludes former organization/code/author and includes release-card replacements.
9. **Internal pagination/preparation** — final physical contents assembly always runs, even with no external records/issues. Contents continuations list every physical page once and retain drawing designations. The 38-active-load test calls `require_saveable_release`, then physically renders three or more contents leaves. Preparation exercises the production service/note fitters and contents cells, including actual expanded load-card titles; appendix planning and drawing share measured layout, so oversized headers/tables fail during preparation with the exact blocker.

## Status matrix

| Defect, otherwise complete controlled test evidence | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
|---|---|---|---|---|---|
| No defect | requested | requested | requested | requested | requested |
| Missing mandatory document | requested/pending | requested/pending | blocked → REVIEW | blocked → REVIEW | blocked → REVIEW |
| Missing exact issue date | requested/pending | requested/pending | blocked → REVIEW | blocked → REVIEW | blocked → REVIEW |
| Expired-at-issue-date regulation | requested/pending | requested/pending | blocked → REVIEW | blocked → REVIEW | blocked → REVIEW |
| Unverified regulation | requested/pending | requested/pending | blocked → REVIEW | blocked → REVIEW | blocked → REVIEW |
| Missing rigging/appendix evidence | pending draft | blocked → PRELIMINARY | blocked | blocked | blocked |
| Missing screen project or verified screen clip | pending draft | existing appendix rules apply | blocked | blocked | blocked |

The positive matrix deliberately uses controlled verified normative test records and generated/hash-verified test PDFs. The shipped registry retains its real unresolved statuses. No test-only bypass exists in production. Real tie scenarios retain the independent expert gate and can be saved only as explicit preliminary drafts with a genuine canonical protocol and no hard rejection.

## RED → GREEN

- Original nine regressions were written before fixes. `tmp/final-hardening-red.log`: 9 tests, 7 assertion failures and one setup error. Corrected the duplicate-showPage test setup and exercised the empty registry without implicit tie rows; `tmp/final-hardening-red-layout.log`: section assertion failure and the actual contents-overflow ValueError. Thus all nine original behaviors were observed RED.
- The public legacy report initially published a forbidden code; `test_legacy_report_cannot_publish_forbidden_reference_code` observed RED, then the common validated/atomic boundary and all 23 legacy PDF/IO tests passed.
- Editor evidence round-trip initially failed (`sling_identification` discarded), then passed after wiring typed load fields.
- Supplemental preparation cases observed RED before their fixes: `test_unsaveable_internal_text_layout_is_rejected_during_preparation`, `test_oversized_rigging_card_is_rejected_during_preparation`, `test_physical_load_card_contents_title_is_checked_during_preparation`.
- Final assembly race and XMP branches observed RED independently: `test_disappeared_mandatory_pdf_cannot_bypass_required_flag_at_render`, `test_forbidden_xmp_metadata_is_scanned_before_replacement`; both then passed, including physical positive production card extraction.
- Unfinished pre-pause focused run was recovered: 51 tests / 195.338 s / OK. Fresh final targeted suite and full discovery are recorded below.
- First full attempt after resumption was interrupted at a legacy fake three-byte PDF test, which opened an unexpected native error dialog after the new physical validator rejected it. Replaced that test fixture with a real generated PDF; no validator was weakened.
- Next full run: 441 tests / 328.166 s / one error, `test_joint_crane_sheet_contains_calculated_sectors`. Its legacy fixture claimed 3 m separation but supplied levels 58/59 m. Corrected the fixture to 58/61 m; original sector and clearance assertions retained. Focused legacy regression passed.

## Commands and final evidence

Every Python/test/build command uses bundled Python:
`C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
Environment: `PYTHONPATH=05_src;06_tests`, `PYTHONIOENCODING=utf-8`, `TEMP=TMP=<worktree>/tmp/test-temp`.

```text
python -m unittest test_pprk_final_hardening test_app_engine_integration test_pprk_merge -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
git diff --check
git diff --cached --check
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tools/build_portable_release.py --runtime <bundled-python-directory> --output tmp/final-hardening-portable-completion
Move-Item -LiteralPath tmp/final-hardening-portable-completion -Destination tmp/pprk-final
<worktree>/tmp/pprk-final/CranePlan_Portable_3.0.1/runtime/python.exe 06_tests/test_full_pprk_end_to_end.py --portable <worktree>/tmp/pprk-final/CranePlan_Portable_3.0.1
```

- Fresh final focused suite: **53/53**, **84.851 s**, exit 0 (`tmp/final-hardening-focused-completion.log`).
- Full final discovery: **446/446**, **342.410 s**, exit 0, no failures/errors/skips (`tmp/final-hardening-full-completion.log`). The prior 444-test run also passed; the intermediate 445-test run was deliberately interrupted after the final legacy-boundary change so the complete suite could restart against the final code.
- Compileall and unstaged whitespace check: exit 0; final staged and unstaged checks both passed after staging, exit 0.
- Evidence PDF: `tmp/task11-evidence/full-pprk.pdf`, **50 pages**, **15,189,892 bytes**, SHA-256 `ae878b2b289fe38708175ceebfebdf2d9b94f6ed830baaf25d71623a68923915`.
- Re-rendered **50/50 pages**, **six contact sheets**. Minimum raster ink ratio `0.008339601257019215`; no blank pages/edge clipping. Inspected all six contact sheets (all pages 1–50) plus full-page 31 (section), 38 (joint schedule), 42 (sling board/table). No clipping, table overlap or modification of canonical clips found. Final regeneration has exactly the same SHA-256 as the inspected PDF. Ordinary short-section whitespace and the intentional expert watermark remain.
- Page map is a literal ordered 50-page oracle: note 5–28 with basis continuation 7 and safety continuation 14; external register 29; calculated sheets 30–38; six canonical clip pages 39–44; contents continuation 45; external foundation 46 and tie pages 47–50. Mixed boxes/rotation/content and all six image pixel identities remain checked.
- Portable ZIP: `tmp/pprk-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,667,848 bytes**, SHA-256 `3aceaf36c727e5b908e8d1d918f75921bfce2bbf4b0e3217a111d10a7871bd22`.
- Own-runtime smoke passed: **8364 files / 6 canonical assets / 50 pages** through public GUI save; CRC, archive/disk inventory, offline library files, application import location and source-PDF/cache/secret-path exclusions passed (`tmp/final-hardening-portable-completion-smoke.log`). Initial execution under the long intermediate output path met the Windows DLL path-length limit; the identical ZIP/release was moved within the worktree to `tmp/pprk-final`, then the packaged runtime completed the smoke. No archive bytes changed.
- The builder used the same 19-file local library evidence input as prior Task 11. The temporary root copy was moved to `tmp/final-hardening-completion-library-input` after path-containment checks, not committed; original library and source reference PDF were not modified.
- Earlier ZIP iterations are superseded; only the above ZIP includes the final common legacy scan boundary.

## Scope and limits

Additive schema-4 fields preserve old positional callers and source projects; no schema rewrite is performed while loading. Missing historical dates/rigging evidence stay missing. No regulatory source was reverified as part of this code change. The ordinary registry's unresolved statuses therefore continue to prevent false advanced releases. Explicit expert tie rules, canonical protocol equivalence, stale-input checks, all-scenario guards, external revision binding, atomic output replacement and rollback are retained. PDF raster-only forbidden content is governed by the canonical reviewed asset bytes and visual QA; no OCR dependency was added. The native GUI save is exercised through the existing headless real workflow fixture, not an exhaustive new manual Tk acceptance test.

Final author self-review: checked the nine brief entries against code, status matrix, physical regressions, full test result and own-runtime payload. No known remaining finding from this brief. Independent integration re-review remains with the parent; no child reviewer was dispatched.

## Integration re-review: round 2

Base: `bd5ae1bb47e5f65cb49a25f9ad42a629121354a3`. The independent integration review rejected that revision with two Critical and seven Important findings. This section supersedes the affected round-1 assertions above. One new completion commit retains both earlier commits unchanged; no merge, push, publication or delegation.

### Resolution of all nine findings

1. **Critical / joint clearance:** the common section/schedule guard requires finite actual jib levels, finite nonnegative reported separation and structural height, a finite minimum clearance of at least 1 m, actual separation at least structure plus that minimum, consistent reported separation, and the actual higher-crane ordering. The minimum comparison has no tolerance that could admit a subminimum gap. Invalid priority indices also fail. The guard runs before preparation, saveability and both public PDF paths, so a preliminary fallback cannot print a negative clearance. The 32.4/42.4 m, structure 12 m case rejects at the real GUI boundary atomically. Valid section/schedule physical assertions remain. Bundle validation binds the canonical selected scenario; a separate RED→GREEN regression preserves a valid selection when an unrelated rejected scenario has invalid geometry.
2. **Critical / route screen:** authoritative passed `DANGER_ZONE_PROTECTED` and `DANGER_ROUTE_PROTECTED` checks both transfer `PROTECTIVE_SCREEN`. The existing composer then includes the canonical screen sheet and requires verified `protective_screen_project`. A physical public-GUI draft includes both the screen and pending project; production without the project is blocked. Existing verified-asset gates remain.
3. **Vector underlays:** plan and section source PDFs are scanned before rasterization in preparation and public `generate_report`, for bundle and legacy paths. Both source text and PDF metadata are inspected. A neutral filename containing vector `27.06-23` rejects before output, with prior project/protocol/revisions/PDF bytes preserved. There is no OCR: raster-only source content still needs visual review, as documented in README and guide.
4. **Entity XMP:** XMP is XML-parsed after raw validation, and decoded text nodes and attributes are scanned. Numeric character references and text split across XML nodes cannot hide forbidden tokens. DTD/entity declarations and malformed XML fail closed. External page-level XMP containing `27.06&#45;23` rejects physically and at GUI save, even with a matching previously recorded file hash. Forbidden external content is fatal in drafts too, rather than being silently downgraded to a pending attachment.
5. **Nine-column registry:** the on-disk CSV now has one explicit nine-column schema, including separate `verification_status` and `software_status`. All original fields/notes are retained. The original REG-007/008/009 nine-field rows now bind their locator, implementation status, summary and full note correctly; eight-field rows gain only an explicit verification classification copied from an existing source-verification flag or `UNVERIFIED_STATUS`. No source was reverified and no unresolved record was promoted. Header/row ambiguity raises; only explicit source-verification statuses permit advanced release. Physical public-GUI extraction checks the corrected fields/notes.
6. **Exact date and title:** validity is evaluated against the exact persisted `issue_date`. The physical title now prints it and derives its displayed year from it. A separately supplied conflicting `issue_year` raises `PPRK_ISSUE_YEAR_MISMATCH` for advanced statuses. The 2026-09-25 / 2028 example prints 2026 and the exact date in a draft, and cannot reach production. The year cannot extend a regulation's validity.
7. **Explicit approval roles:** additive `ApprovalSlot.role` is editable and persisted. Exact legacy position labels such as `Проверил` and `Утвердил` also identify the role without inventing it. Exactly one meaningful named signer per role supplies the frozen stamp requisites; the project manager never fills either role implicitly. Missing/duplicate roles remain blank and create `PPRK_APPROVAL_ROLE_REQUIRED` at APPROVED/PRODUCTION, matching the existing approval-scope policy. All eight approval rows and entered signatures remain preserved. Public physical PDFs prove distinct checker/approver stamps and no manager substitution; missing role rejects atomically.
8. **Rigging sentinels:** normalized whitespace, punctuation, brackets and placeholder variants (`НЕ ЗАПОЛНЕНО`, `Не заполнена`, `Н/Д`, `None`, etc.) are not meaningful evidence even when `rigging_verified=True`. All three rigging text fields share this gate. A physical public draft stays `НЕ ПОДТВЕРЖДЕНО`; production rejects. The separate 18-case sentinel matrix also covers zero-width whitespace. Historical missing data stays missing/unconfirmed.
9. **Actual external contents:** one formatter supplies the exact title / document ID / source-page strings to both preparation and final physical contents. Preparation measures every accepted external page string with the production cell fitter. A 400-W ID fails in `prepare_release` before `require_saveable_release` can approve or any public GUI output changes. Existing multi-page/multi-contents and 38-load physical regressions remain passing.

### Round-2 status matrix

All rows assume otherwise complete, genuine protocol-bound controlled evidence. The real unresolved registry is never bypassed in production.

| Defect | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
|---|---|---|---|---|---|
| Invalid joint geometry/order | fatal | fatal | fatal | fatal | fatal |
| Forbidden vector underlay / decoded external XMP | fatal | fatal | fatal | fatal | fatal |
| Oversized actual contents string | fatal | fatal | fatal | fatal | fatal |
| Ambiguous regulation CSV schema/row | fatal | fatal | fatal | fatal | fatal |
| Screen project absent/unverified, clip verified | pending | pending | blocked | blocked | blocked |
| Required screen clip absent/unverified | pending draft | blocked | blocked | blocked | blocked |
| Missing/invalid exact date, conflicting title year | pending; date-derived year | pending; date-derived year | blocked | blocked | blocked |
| Expired/unverified regulation | pending | pending | blocked | blocked | blocked |
| Missing explicit checker/approver | blank/pending | blank/pending | blank/pending | blocked | blocked |
| Sentinel/missing rigging evidence | unconfirmed draft | blocked | blocked | blocked | blocked |

The earlier five-status physical/status matrix remains covered by `test_status_matrix_rejects_unverified_expired_or_missing_required_evidence`. The new module adds public GUI, physical PDF and byte-preservation assertions for every round-2 finding. Its atomic helper preserves both prior preliminary and production PDFs plus all other project files.

### Round-2 RED → GREEN and verification

- Initial nine regressions: `tmp/hardening-r2-red.log`, 9 tests / 49.194 s, 11 assertion failures and one missing-screen `KeyError`, reproducing all nine findings. The error was the intended missing canonical screen sheet, not fixture setup. First corrected run: 9/9 / 114.702 s (`hardening-r2-green-first.log`).
- Sentinel extension: 12 failing subcases before the common meaningful-text gate; then 20/20 / 4.492 s including composer compatibility (`hardening-r2-sentinel-compat-green.log`).
- Canonical selected-scenario extension: one RED error before binding the geometry guard, then 1/1 / 19.446 s (`hardening-r2-selected-green.log`).
- Final boundary self-review: the new structure 9.0005 m subcase reproduced acceptance of a 0.9995 m gap (1 failure / 1.789 s). Removed the minimum comparison's 1 mm tolerance, then 1/1 / 1.174 s (`hardening-r2-minimum-red.log`, `hardening-r2-minimum-green.log`). All final suites/builds below were restarted after that last production change. An earlier 11/11 / 136.967 s run had also verified the strengthened helper preserves both old PDF names.
- Additional data/migration audit compared every original field of all 13 CSV rows with the normalized records, rejected three ambiguous header/row shapes, confirmed an old role-less approval remains role-less, and round-tripped explicit checker/approver roles; all assertions passed.
- Compatibility pass: 87 tests with one stale title-field oracle missing the newly printed `issue_date`; updated the oracle without relaxing behavior. An early full run was deliberately interrupted before final physical evidence assertions were refreshed; it is not counted as a completed verification.
- Fresh focused after the strict-minimum fix: **48/48 / 228.090 s / OK**, exit 0 (`tmp/hardening-r2-focused-completion.log`).
- Fresh full discovery after the strict-minimum fix: **457/457 / 488.381 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r2-full-completion.log`).
- `python -m compileall -q 05_src tools 06_tests`, `git diff --check` and `git diff --cached --check`: exit 0 after the strict-minimum fix.

Exact commands (the same bundled Python and worktree-local TEMP/TMP used above):

```text
python -m unittest test_pprk_final_round2 test_pprk_final_hardening test_pprk_merge -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
git diff --check
git diff --cached --check
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r2-final
tmp/pprk-r2-final/CranePlan_Portable_3.0.1/runtime/python.exe 06_tests/test_full_pprk_end_to_end.py --portable <worktree>/tmp/pprk-r2-final/CranePlan_Portable_3.0.1
```

- Evidence: `tmp/task11-evidence/full-pprk.pdf`, **50 pages / 15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`. Regenerated and rendered after the strict-minimum fix; SHA is identical to the visually inspected PDF. The exact-date fixture and corrected registry preserve the literal 50-page map; the basis continuation anchor is updated to its actual retained source note.
- Rendered **50/50**, six contact sheets inspected; minimum ink ratio `0.008339601257019215`. Full-page title/date, basis register/continuation, section, joint schedule and rigging board were also inspected. No new clipping/overlap; intentional expert watermark and ordinary short-section whitespace remain.
- Portable: `tmp/pprk-r2-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,671,159 bytes**, SHA-256 `9b58c49a48c5e217ddc8116a0d6a87e3b023f1a1f076d0e7046c78de5367b605`. Own-runtime smoke passed, exit 0: **8364 files / six canonical assets / 50-page public-GUI save**, including CRC, disk/archive inventory, offline library and excluded-source/cache/secret-path checks (`tmp/hardening-r2-portable-completion-smoke.log`). Byte comparison confirms all **44 Python modules**, README, packaged guide and registry match current worktree (**47 files**). Earlier `tmp/pprk-r2` ZIP is superseded by the strict-minimum fix.
- Temporary 19-file library evidence input was copied from the prior local input for the builder, then moved to `tmp/hardening-r2-final-library-input` after absolute containment checks. Original library and source reference PDF were not modified. No network or OCR dependency was added.

Author self-review covers the public save boundary, canonical bundle binding, legacy rasterization/report path, atomic source inspection and final publication, approval migration, real CSV fields, exact date, and contents preparation/assembly. Independent integration re-review remains with the parent.

## Integration re-review: round 3

Base: `ca08ed0bc1f8405d2ebd1691d155e3ebe5c32876`. Five Important findings, addressed in one new commit without delegation, merge, push or publication. This section supersedes round 2's exact floating-point comparison and source/XMP scope claims.

1. **Floating-point boundary:** the minimum-clearance check permits only absolute representation noise of `1e-12` m, with relative tolerance zero. The valid optimizer-style 30.8 / (30.8 + 3), 31.3/34.3 and 61.1/64.1 pairs pass real GUI and public legacy generation; physical sections print a 1.0 m clear gap. A genuine 0.9995 m gap still rejects at both boundaries, preserving old files. All finite/nonnegative, ordering, canonical-selection and schedule guards remain.
2. **Underlay TOCTOU:** public generation captures each selected existing source path once into bytes, validates those bytes, then makes a controlled temporary snapshot used by both layout and raster/vector rendering. The mutable original path is never reopened for rendering. Plan/section copies retain their original basenames, and the caller retains its original paths and snapshots never enter persisted project data; the existing GUI managed-source copying remains unchanged. The temporary root avoids deep Windows GUI-report paths and is cleaned on success/failure. An actual independent thread watches the legacy/assembly staging directory and replaces the original with a forbidden black-page PDF. All four plan/section × bundle/legacy outputs retain exactly the clean validated image pixels; the prior destination remains unchanged at the swap. GUI races additionally reject via the existing source fingerprint and retain both prior PDFs, project, protocol and revision sidecars. No production function is patched to create the race.
3. **Semantic rigging completeness:** the central normalized evidence predicate rejects `НЕ ЗАПОЛНЕНО`, `ОТСУТСТВУЕТ`, `НЕТ`, `НЕ ПРИМЕНИМО`, `НЕ ПРОВЕРЕНО`, `УТОЧНИТЬ`, including whitespace, punctuation, brackets and case variants, in type/sling/document fields. The 54-case context matrix and three physical public cards cannot falsely confirm a sentinel; production remains blocked. No historical evidence is fabricated.
4. **Recursive metadata:** the reachable PDF dictionary/array/indirect-object graph is traversed with direct and indirect identity guards. All `/Metadata` entries and XML metadata streams are inspected, including nested Form XObject resources and cycles. Decoded XML text and attributes still undergo forbidden-token normalization; decimal/hex entities are covered. Forbidden nested metadata rejects external attachments and both underlay types before output, including public legacy output. A safe cyclic Form with benign numeric entities still publishes a physical external page.
5. **Fatal unsafe XML:** DTD/entity declarations, decoding failures, malformed XML and unusable metadata streams raise `UnsafePDFMetadataError`, a fatal forbidden-source subtype. Merge inspection preserves `PPRK_UNSAFE_PDF_METADATA` instead of converting it to an ordinary unreadable/pending issue. Existing selected files are inspected before presence/verification flags can hide unsafe metadata. Both preparation and `require_saveable_release` reject unsafe sources; the latter rechecks prepared source records before ordinary status blockers, covering replacement after preparation. No preliminary publication is permitted merely because an attachment was downgraded.

Round-3 status matrix (other requirements still apply):

| Source condition | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
|---|---|---|---|---|---|
| Exact valid boundary with representation noise only | geometry accepted | geometry accepted | geometry accepted | geometry accepted | geometry accepted |
| Actual 0.9995 m gap under 1 m minimum | fatal | fatal | fatal | fatal | fatal |
| Forbidden recursive metadata / unsafe XML | fatal | fatal | fatal | fatal | fatal |
| Unsafe source marked absent/unverified | fatal | fatal | fatal | fatal | fatal |
| Sentinel rigging | unconfirmed draft | blocked | blocked | blocked | blocked |
| Original underlay replaced after capture, GUI save | stale/rejected | stale/rejected | stale/rejected | stale/rejected | stale/rejected |

Direct bundle/legacy report generation can publish the already validated immutable snapshot after an original path replacement; it cannot publish replacement bytes. GUI save additionally retains its existing whole-release fingerprint gate. The all-status prepared-release XML matrix has 20 combinations (page/Form × DTD/malformed × five statuses); six presence/verification combinations exercise the source-classification boundary separately.

RED evidence: `tmp/hardening-r3-red.log` — 9 tests / 336.959 s, 62 assertion failures plus the three expected real valid-boundary ValueErrors (not fixture errors). This reproduced all five findings. Supplemental source-flag check: `tmp/hardening-r3-flags-red.log` — 1 test / 7.183 s, six failing cases; `tmp/hardening-r3-flags-green.log` — 1/1 / 3.726 s. The source-inspection order was temporarily restored to flag-first for that RED run, then the fix restored; no mocked production functions were used.

Verification and artifacts:

- The first full discovery ran **467 tests / 778.616 s** with one compatibility failure: `test_app_pprk_release.ReleaseEditorTests.test_unverified_or_corrupt_source_is_pending_in_preliminary_copy`. Early source inspection changed the ordinary diagnostic from `PPRK_EXTERNAL_UNVERIFIED` to `PPRK_EXTERNAL_NOT_PDF` for an unverified corrupt file. The implementation now always propagates unsafe/forbidden source issues while retaining existing presence/verification priority for ordinary file errors. The existing test was not changed. It and the six unsafe flag cases then passed together: **2/2 / 4.153 s** (`tmp/hardening-r3-compat-green.log`). All final suites/artifacts were restarted after this last production change; the final focused command additionally includes the 16 editor tests.
- First GREEN: **9/9 / 273.013 s / OK** (`tmp/hardening-r3-green-first.log`); supplemental flags **1/1 / 3.726 s / OK**. Ten new test methods total. Final races also assert the prior direct-report destination still contains its original bytes at the swap; the shared GUI atomic helper seeds both PDFs plus old project, protocol and revision files.
- Earlier focused: **58/58 / 514.907 s / OK** before the ordinary-diagnostic compatibility fix. Final expanded focused: **74/74 / 527.939 s / OK**, exit 0 (`tmp/hardening-r3-focused-final.log`).
- Final full discovery: **467/467 / 774.097 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r3-full-final.log`).
- `python -m compileall -q 05_src tools 06_tests`, `git diff --check` and `git diff --cached --check`: exit 0 after the final compatibility fix.
- Additional real GUI positive with both underlay roles sharing one source: caller project unchanged, both managed-source copies match the selected bytes, both physical embedded images match, and no `.pprk-underlays-` paths enter JSON (`tmp/hardening-r3-positive-underlays.log`).
- Evidence: `tmp/task11-evidence/full-pprk.pdf`, **50 pages / 15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`. Regenerated and rendered **50/50**; all six new contact sheets inspected, no clipping/overlap. PDF is byte-identical to the inspected round-2 artifact; literal page map and canonical pixel identities retained. Minimum ink ratio `0.008339601257019215`.
- Final portable: `tmp/pprk-r3-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,672,845 bytes**, SHA-256 `f07345408ff1b23617f6d83a09e00e85c891b81a296a6c69d68f6198cc8ddb3a`. Own-runtime smoke **passed / exit 0**, **8364 files / six canonical assets / 50 public-GUI pages**, including CRC, archive/disk inventory, offline-library and source/cache/secret exclusions (`tmp/hardening-r3-portable-final-smoke.log`). All **44 Python modules + README + guide + registry (47 files)** match the final source bytes. The temporary 19-file library input was moved to `tmp/hardening-r3-final-library-input` after absolute containment checks. The earlier `tmp/pprk-r3` ZIP is superseded by the compatibility fix; original library/source PDF unchanged.

Exact commands, using the bundled Python and worktree-local TEMP/TMP/PYTHONPATH stated above:

```text
python -m unittest test_pprk_final_round3 test_pprk_final_round2 test_pprk_final_hardening test_pprk_merge test_app_pprk_release -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
git diff --check
git diff --cached --check
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r3-final
tmp/pprk-r3-final/CranePlan_Portable_3.0.1/runtime/python.exe 06_tests/test_full_pprk_end_to_end.py --portable <worktree>/tmp/pprk-r3-final/CranePlan_Portable_3.0.1
```

No new persisted fields or migration are needed. Snapshot paths are transient; source JSON, approval roles, exact dates, real regulation flags, canonical assets and ordinary rigging evidence remain intact. Raster-only forbidden markings still require visual review; no OCR or network dependency was added. Independent integration re-review remains with the parent.

## Integration re-review: round 4

Base: `a9d36c458d162fcb1a0a0e4e9920da6ddb459160`. Three Important findings; one new completion commit, no delegation/merge/push/publication. This section extends round 3's source-snapshot, XML-declaration and semantic-evidence guarantees.

1. **Absent underlays are immutable absence:** the copied rendering project clears each underlay path before checking/capturing it. If the selected path does not resolve to a file, no live path survives in the rendering snapshot. A later file creation cannot be read by either layout or raster/vector rendering. Four actual staging-thread races cover plan/section × bundle/legacy: the newly created forbidden black PDF exists at the original path, but the physical drawing has no background image, the prior destination is untouched at the swap and the caller's project is unchanged. Two GUI races additionally preserve all prior actual status-report filenames, project, protocol and revision sidecars. Existing background/completeness requirements remain; optional backgrounds can stay absent without importing later bytes.
2. **Encoding-aware pre-parser XML rejection:** a byte-normalized declaration guard runs first. BOM (UTF-32 before UTF-16), byte-order signatures and the XML encoding declaration then select a strict text decoder; contradictory/unknown encodings fail closed. A second Unicode declaration guard runs before namespace-aware `ET.iterparse`, which receives decoded Unicode rather than original bytes. Thus the parser cannot reinterpret BOM-less bytes and expand hidden internal declarations. Eleven encoding/BOM configurations × page/nested Form are audited using real parser-entry profiling (`sys.setprofile`), with no function patched. Safe XML and decoded forbidden numeric/hex entity values are separately checked for the same 22 configurations, preventing a blanket encoding rejection. The exact UTF-16LE/no-BOM/declaration/DTD nested-Form repro is fatal in preparation, prepared saveability and public save across all five statuses; both underlay types also reject it at public/legacy boundaries atomically.
3. **Bounded semantic phrases anywhere:** evidence checks find meaningful missing/unverified phrases after field labels and within categorical text, not only at position zero. NFKC/case/whitespace/punctuation variants, common joined labels and Russian grammatical forms are covered. Word/phrase boundaries prevent accidental matches inside ordinary identifiers such as `НЕТТО-42`; `No.42`, clarified and checked passports remain valid. Physical cards with `Номер: НЕ ЗАПОЛНЕНО`, `Паспорт: НЕ ПРОВЕРЕНО` and `Тип оснастки отсутствует` remain unconfirmed and cannot reach production. A positive real-GUI production card with valid labeled evidence is confirmed and contains no missing marker; its normative prerequisites use an isolated registry data-path fixture, without changing a production function or any shipped registry row.

Round-4 status matrix (other independent requirements still apply):

| Condition | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
|---|---|---|---|---|---|
| Underlay absent at capture, then created | remains absent | remains absent | remains absent | remains absent | remains absent |
| GUI input bytes change after capture | stale/rejected | stale/rejected | stale/rejected | stale/rejected | stale/rejected |
| Encoded DTD/ENTITY or conflicting/unsafe XML encoding | fatal | fatal | fatal | fatal | fatal |
| Labeled/inflected missing rigging evidence | unconfirmed draft | blocked | blocked | blocked | blocked |
| Valid exact labeled evidence | eligible | eligible | eligible | eligible | eligible |

RED: `tmp/hardening-r4-red.log`, **9 tests / 260.578 s / 69 assertion failures**, no fixture errors. Core/earlier sentinel compatibility then **5/5 / 18.814 s**; first full new module **9/9 / 177.507 s**.

Author self-review found a bounded-matching regression for grammatical missing forms such as `НЕПРОВЕРЕННЫЙ`. Added a separate test before extending the inflection vocabulary: **1 test / 2.271 s / seven failures** (`hardening-r4-grammar-red.log`), then **4/4 / 20.852 s** including prior sentinel compatibility and positive clarified/checked evidence (`hardening-r4-grammar-green.log`). Early focused/full runs were deliberately interrupted before completion so the final suites/build could restart from the corrected source. Eleven new round-4 methods total; all actual report-status targets are seeded by the shared atomic helper.

The parent agreed to fold an adjacent original forbidden-metadata gap into this round: ElementTree removes `xmlns` attributes and expands namespace URIs into tag/attribute names. Namespace RED (`tmp/hardening-r4-namespaces-red.log`) reproduced **nine failures / 19.862 s** across decimal/hex used, default, attribute and unused declarations on page/nested Form plus public publication. Guarded Unicode is now parsed with `start` and `start-ns` events, scanning namespace declarations (including unused), expanded names, attribute keys/values and complete text. GREEN **4/4 / 42.617 s** also proves safe namespaces survive public GUI save with byte-identical original metadata. The parser-entry profiler now watches both parser APIs and C parser methods, with final audit **1/1 / 0.077 s**. Prior active final runs/builds were superseded and restarted after this source edit.

- Final focused: **85/85 / 736.591 s / OK**, exit 0 (`tmp/hardening-r4-focused-namespace-final.log`).
- Final full: **478/478 / 980.882 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r4-full-namespace-final.log`).
- Compileall and staged/unstaged diff checks: **exit 0**, final frozen source, after namespace extension.
- Evidence: **50 pages / 50 rendered PNGs / six inspected contact sheets**, no new clipping/overlap; literal page map and canonical image identities retained. `tmp/task11-evidence/full-pprk.pdf`, **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`; namespace-final regeneration is byte-identical to the inspected artifact, minimum ink `0.008339601257019215`.
- Portable: `tmp/pprk-r4-ns/CranePlan_Portable_3.0.1_Windows.zip`, **174,675,022 bytes**, SHA-256 `0d8e36323b95df733f363a1c5804e2d8137bde73dd79357e799ff008fa61df39`. Own-runtime smoke **passed / exit 0**, **8364 files / six assets / 50 public-GUI pages**, CRC/inventory/offline-library/source/cache/secret exclusions passed (`tmp/hardening-r4-portable-namespace-smoke.log`). All **44 Python modules + README + guide + registry (47 files)** match. Temporary 19-file library input moved to `tmp/hardening-r4-ns-library-input` after containment checks; original library/source unchanged; earlier round-4 ZIPs superseded.

Commands use the same bundled Python, `PYTHONPATH=05_src;06_tests`, UTF-8 and worktree-local TEMP/TMP:

```text
python -m unittest test_pprk_final_round4 test_pprk_final_round3 test_pprk_final_round2 test_pprk_final_hardening test_pprk_merge test_app_pprk_release -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
git diff --check
git diff --cached --check
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r4-ns
tmp/pprk-r4-ns/CranePlan_Portable_3.0.1/runtime/python.exe 06_tests/test_full_pprk_end_to_end.py --portable <worktree>/tmp/pprk-r4-ns/CranePlan_Portable_3.0.1
```

No persisted schema fields, invented confirmation, regulatory promotion, network or OCR dependency. Caller/source paths remain unchanged; controlled temporary copies never enter project JSON. Author self-review covers the exact three reviewer repros, real races, parser entry, physical cards and valid production control. Independent integration re-review remains with the parent.

## Integration re-review: round 5

Base: `d299d33d36dff64752441e2dbb848f0bb23699b5`. Two Important findings addressed together at the central rigging-text predicate; one completion commit, no delegation/merge/push/publication.

1. **Grammatical missing evidence:** finite suffix enumeration was the cause of the accepted accusative forms. The predicate now uses bounded Russian stems with open case/gender endings, including separated/punctuated negative prefixes. `Заявка на отсутствующую схему строповки`, `Ссылка на непроверенную ведомость оснастки`, `не заполненную` and `не применимую` are incomplete in all three rigging text fields. No status/confirmation flag promotes them. Preliminary physical cards remain unconfirmed; all four advanced statuses block at prepared/public boundaries and retain prior PDF/project/protocol/revision bytes.
2. **Negation scope and field identity:** context passes the explicit field role (`rigging_type`, `sling_identification`, `rigging_evidence`) into the central predicate. Bare/essential `нет`, missing label assignments and targeted absence of a scheme/sling/evidence remain incomplete. Bounded statements about absent defects, damage, remarks or inapplicable elements are removed only from semantic evaluation; they remain unchanged in the physical card. Remaining identifying information is required for the selected field. A positive exact inspection sentence can therefore support a confirmed production card; a quality statement by itself or an independent missing/unverified reference in the same value cannot. Generic approval-name validation receives no rigging quality allowance.

Nine new methods exercise literal positive/negative corpora across all three fields, reviewer physical repros, every advanced status, atomic outputs and valid production. A controlled registry data-path fixture isolates existing regulatory prerequisites without patching any production gate or changing a shipped registry row.

| Condition | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
|---|---|---|---|---|---|
| Inflected missing/unverified rigging reference | unconfirmed draft | blocked | blocked | blocked | blocked |
| Essential `нет`, missing label assignment, targeted noun + `нет` | unconfirmed draft | blocked | blocked | blocked | blocked |
| Only a no-defect/quality statement, no identity | unconfirmed draft | blocked | blocked | blocked | blocked |
| Actual identities plus positive inspection remarks | eligible | eligible | eligible | eligible | eligible |
| Positive remark plus independent missing reference | unconfirmed draft | blocked | blocked | blocked | blocked |

Other independent release requirements still apply; the shipped registry is not promoted.

TDD: `tmp/hardening-r5-red.log`: **7 tests / 73.578 s / 40 assertion failures + one expected positive-production gate error**, all caused by the reviewed semantic behavior, no fixture errors. First core/old-sentinel compatibility GREEN: **9/9 / 46.374 s**, `tmp/hardening-r5-core-green.log`. Author negation-scope self-review added quality-only noun lists/labels before the next source change: **1 test / 5.994 s / 13 failures** (`tmp/hardening-r5-scope-red.log`), proving that a remark or its generic subject must not substitute for identity.

- Round-5 module: **8/8 / 106.627 s / OK**, exit 0 before the final qualifier extension (`tmp/hardening-r5-green.log`); all nine final methods are included in the fresh focused/full suites.
- Final focused: **94/94 / 858.666 s / OK**, exit 0 (`tmp/hardening-r5-focused-clause-final.log`).
- Final full: **487/487 / 1109.583 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r5-full-clause-final.log`).
- Compileall and staged/unstaged diff checks: **exit 0**, compileall plus staged/unstaged diff checks after the final clause-scope edit.
- Evidence/render/contact sheets: **50 pages / 50 fresh PNGs / six inspected contact sheets**, no new clipping/overlap; literal page map and canonical image identities retained. `tmp/task11-evidence/full-pprk.pdf`, **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, byte-identical to the previous inspected artifact. Minimum ink `0.008339601257019215`.
- Final portable/own-runtime/source bytes: `tmp/pprk-r5-clause-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,676,697 bytes**, SHA-256 `67c1ecfc9e66b50d8587b22f22d9200feeaaa616d27dc8b1c3a5225de7f61328`. Own runtime with `-B`: **8364 files / six assets / 50 public-GUI pages**, exit 0; CRC, archive/disk inventory, offline-library and source/cache/secret exclusions passed (`tmp/hardening-r5-portable-clause-final-smoke.log`). All **44 Python modules + README + guide + registry (47 files)** match current source bytes. Temporary 19-file library input moved to `tmp/hardening-r5-clause-final-library-input` after containment checks; original library/source unchanged; earlier round-5 builds superseded.

Exact commands use `C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`, `PYTHONPATH=05_src;06_tests`, `PYTHONIOENCODING=utf-8` and worktree-local `TEMP=TMP=<worktree>/tmp/test-temp`:

```text
python -m unittest test_pprk_final_round5 -v
python -m unittest test_pprk_final_round5 test_pprk_final_round4 test_pprk_final_round3 test_pprk_final_round2 test_pprk_final_hardening test_pprk_merge test_app_pprk_release -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
git diff --check
git diff --cached --check
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r5-clause-final
tmp/pprk-r5-clause-final/CranePlan_Portable_3.0.1/runtime/python.exe -B 06_tests/test_full_pprk_end_to_end.py --portable <worktree>/tmp/pprk-r5-clause-final/CranePlan_Portable_3.0.1
```

No new persisted fields or migration; no invented confirmation, regulatory relaxation, network or OCR dependency. Author self-review specifically covers grammatical inflection, negation scope, quality-only input, independent missing clauses and real production output. Independent integration re-review remains with the parent.

Round-5 author qualifier self-review: `Пока нет`, `Паспорт: ещё нет`, `Схемы пока нет` and quality-only `Вообще нет замечаний` still counted filler words as identity. Added a ninth method before the next source edit: **1 test / 6.697 s / 24 assertion failures** (`tmp/hardening-r5-qualifier-red.log`), then **4/4 / 20.029 s / OK** including positive/mixed/list scopes (`tmp/hardening-r5-qualifier-green.log`). Bounded absence qualifiers now participate in targeted absence and cannot themselves identify a field; qualified no-defect subjects remain eligible with real evidence. The earlier focused/full runs were interrupted, not counted as final, and source/PDF/build verification restarted after this edit.

The first portable-smoke invocation omitted bytecode suppression: Python generated 462 `.pyc` files in the extracted folder, so the strict archive/disk inventory failed as intended. After retaining that folder/log and extracting the unchanged ZIP afresh, the own runtime with `-B` passed the unchanged 8364-file inventory and GUI smoke. That initial ZIP was subsequently superseded by the final qualifier source edit; the final build/smoke uses `-B` from its first invocation. No archive check was weakened.

Retained real public-GUI card evidence: `tmp/round5-card-evidence/{positive,missing,unverified}-card.png`, all page 42, generated after the qualifier edit and before the final clause-boundary change (`tmp/hardening-r5-cards-evidence.log`). The production card retains exact passport/inspection text, `ПОДТВЕРЖДЕНО` and no missing marker; both reviewer draft cards show `НЕ ПОДТВЕРЖДЕНО`/pending data. All three rendered cards inspected without clipping/overlap. Final 50-page evidence regeneration remains byte-identical to the inspected six contact sheets.

Clause-scope self-review found that a quality phrase could cross punctuation after an actual missing passport. RED **1 / 4.862 s / nine failures** (`tmp/hardening-r5-clause-red.log`) covers comma/colon/dash after `Паспорт №123 отсутствует`; comma-separated quality-only lists additionally gave RED **1 / 8.226 s / six failures** (`tmp/hardening-r5-comma-list-red.log`). Leading quality predicates now govern their subject directly without crossing punctuation; suffix `Дефектов — нет` and explicit quality noun lists remain supported. GREEN **4/4 / 24.587 s / OK**, including qualifier and positive scopes (`tmp/hardening-r5-clause-green.log`). Prior qualified focused/full runs and build were superseded; final focused/full, evidence and own-runtime build restarted after this last source edit.

## Integration re-review: round 6

Base: `417324feb95ef0cc3b226d3a92850ce12291e064`. Two Important findings require a positive field contract and clause-scoped absence, rather than another suffix/adjacency exception. One completion commit; no delegation/merge/push/publication.

1. **Target absence survives intervening identity:** the shared clause scanner tests a target noun and `нет` anywhere in the same clause. `Паспорт(а) №123 нет`, `Строп 4СК нет` and longer reference/mark phrases cannot gain confirmation from their identifiers. Existing bounded missing/unverified stems continue to block `схема по акту 42 отсутствует`. Sentence/clause boundaries stop this relation; number/date punctuation and decimal marks stay intact. Bare labels bind their following value (`Паспорт: №123`, `Марка: TR-ABC`), while an already identified left clause ends at a colon/spaced dash. Russian word/number boundaries are separated only for semantic scanning; raw role identity and rendered/project values remain unchanged, including `4СК-5,0`.
2. **Explicit positive identities by role:** generic leftover prose is no longer evidence. Type requires a concrete equipment/material term or known sling family. Sling identification requires a whole mark/number clause: numeric identity, an alphanumeric mark, or an explicitly labeled uppercase separator code. Evidence requires a named passport/act/certificate/protocol/witness document plus number/date/code in the same clause. Exact document lexemes/case forms prevent `актуальные сведения` and `протокольная запись` from impersonating document names. Quality-only text, inspection preambles, a document without a reference and values from the wrong role remain incomplete even with the checkbox set. Standard actual values (`Канатный`, `4СК-1`, `4СК-TEST`, `4СК-5,0`, passport 123), explicit decimal-mark/serial and uppercase-code production controls remain supported.

Nine new methods cover literal positive/negative corpora for all three roles, paraphrases, date/decimal punctuation, label/colon/dash scope, word-number adjacency, physical cards and public atomic gates. Five invalid cases (intervening passport ID, each missing role and implicit equipment absence) produce unconfirmed preliminary cards; all four advanced statuses reject them while preserving prior report filenames, project, protocol and revision bytes. Three positive real-GUI production cards retain exact decimal/serial and uppercase document/mark text. Existing independent normative prerequisites use only an isolated verified registry data-path fixture; no production gate or shipped regulatory row is patched.

Two older test fixtures were corrected to the new contract: the round-5 near-sentinel positives are now assigned to their proper roles rather than every field, and the overflow fixture includes passport number 123 so it still exercises layout overflow with semantically complete evidence. Cross-role rejection is directly covered by the new corpus; no assertion or production policy was relaxed.

| Condition | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
|---|---|---|---|---|---|
| Target noun + intervening ID + absence | unconfirmed draft | blocked | blocked | blocked | blocked |
| Generic inspection/quality prose instead of any role identity | unconfirmed draft | blocked | blocked | blocked | blocked |
| Named document without number/date/code | unconfirmed draft | blocked | blocked | blocked | blocked |
| Concrete type + actual mark + named document identity | eligible | eligible | eligible | eligible | eligible |
| Real identity followed by separate positive quality clause | eligible | eligible | eligible | eligible | eligible |

All other engineering/approval/source/regulatory gates still apply. No persisted schema fields or migration are added; legacy values are reevaluated fail closed without filling any invented identity.

TDD evidence:

- Initial RED: **6 tests / 154.571 s / 63 assertion failures**, no fixture errors (`tmp/hardening-r6-red.log`). Extended wrong-role/preamble/document-name corpus RED **1 / 6.034 s / 25 failures** (`tmp/hardening-r6-role-red.log`).
- Core GREEN **5/5 / 19.280 s**, including the meaningful overflow fixture (`tmp/hardening-r6-core-green.log`). Label-versus-clause self-review RED **1 / 3.445 s / five failures** (`tmp/hardening-r6-clause-red.log`), followed by combined new/round-5/older sentinel compatibility GREEN **20/20 / 315.566 s** (`tmp/hardening-r6-green.log`).
- Before the final suites, paraphrase/word-number self-review RED **1 / 5.915 s / five failures** (`tmp/hardening-r6-paraphrase-red.log`); interim core/grammar/overflow GREEN **9/9 / 47.309 s** (`tmp/hardening-r6-paraphrase-green.log`). The semantic word-number split leaves original mark/document bytes untouched. First final suites/artifacts started after this edit and were superseded by the subsequent shared-scope self-review.
- Final focused: **103/103 / 1103.973 s / OK**, exit 0 (`tmp/hardening-r6-focused-quality-final.log`).
- Final full: **496/496 / 1358.717 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r6-full-quality-final.log`).
- Compileall and staged/unstaged diff checks: **exit 0**, final-source compileall and staged/unstaged diff checks.
- Evidence/render/contact sheets: **50 pages / 50 fresh PNGs / six inspected contact sheets**, no new clipping/overlap; physical page map and canonical assets retained. `tmp/task11-evidence/full-pprk.pdf`, **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`; quality-final regeneration is byte-identical to the inspected artifact, minimum ink `0.008339601257019215` (`tmp/hardening-r6-evidence-quality-final.log`).
- Portable/own-runtime/source bytes: `tmp/pprk-r6-quality-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,679,047 bytes**, SHA-256 `c20a5d6121a2fb0fb444c2e945f41665c48e4a629941a9bdd07f4d9f4ef41c2d`. Own-runtime `-B` smoke passed, **8364 files / six assets / 50 public-GUI pages**, exit 0; CRC/inventory/offline-library/source/cache/secret exclusions passed (`tmp/hardening-r6-portable-quality-final-smoke.log`). All **44 production Python modules + README + guide + registry (47 files)** match current bytes. Temporary 19-file library input moved to `tmp/hardening-r6-quality-final-library-input` after containment checks. Original library/source unchanged; earlier round-6 ZIPs superseded.

Exact commands use `C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`, `PYTHONPATH=05_src;06_tests`, `PYTHONIOENCODING=utf-8` and worktree-local `TEMP=TMP=<worktree>/tmp/test-temp`:

```text
python -m unittest test_pprk_final_round6 test_pprk_final_round5 test_pprk_final_round4 test_pprk_final_round3 test_pprk_final_round2 test_pprk_final_hardening test_pprk_merge test_app_pprk_release -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
git diff --check
git diff --cached --check
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r6-quality-final
tmp/pprk-r6-quality-final/CranePlan_Portable_3.0.1/runtime/python.exe -B 06_tests/test_full_pprk_end_to_end.py --portable <worktree>/tmp/pprk-r6-quality-final/CranePlan_Portable_3.0.1
```

Author self-review specifically covers identifier distance, inflected targets, preambles, cross-role prose, lookalike document words, number/word adjacency, decimal marks and clause punctuation before final verification. Independent integration re-review remains with the parent.

Further author self-review reproduced implicit own-role absence (`Траверса нет`, `4СК-5,0нет`) and uppercase-code colon binding: RED **1 / 2.443 s / six failures** (`tmp/hardening-r6-single-scope-red.log`). Positive and negative evaluation now consume one case-preserving clause parse; identity itself can be the implicit subject of an absence predicate. GREEN **10/10 / 49.271 s** (`tmp/hardening-r6-single-scope-green.log`). Equipment-word self-review RED **1 / 6.415 s / two failures** (`Канатныйнет`, construction `Захватка №123`, `tmp/hardening-r6-equipment-word-red.log`) led to positive whole-term grammatical forms rather than arbitrary prefix suffixes; open negative stems remain unchanged. Interim GREEN **10/10 / 50.293 s** (`tmp/hardening-r6-core-final-green.log`). The public matrix adds implicit equipment absence and the positive uppercase production record includes a colon-separated quality remark. Earlier active final suites and ZIP were superseded; fresh focused/full/evidence/build/smoke run after these edits.


The scope-final focused run exposed **three positive compatibility subtest failures** in round-5 `test_quality_scope_does_not_hide_an_independent_missing_reference` (`Дефектов — нет` in all three roles); that run and the active full run were interrupted and are not final verification. Standalone RED **2 tests / 8.686 s / six failures** reproduces the old/new positive cases (`tmp/hardening-r6-quality-dash-red.log`). Quality-word guard RED **1 / 3.287 s / four failures** proves malformed quality words must not erase a missing-equipment/document predicate (`tmp/hardening-r6-quality-word-red.log`). Whole quality terms with proper boundaries are now annotated once, case-preservingly, before clause segmentation; their stored/rendered text remains unchanged. This keeps `Дефектов — нет` bound to its subject and retains unsafe missing predicates. Expanded compatibility GREEN **19/19 / 95.293 s**, including every prior positive/negative core case and overflow (`tmp/hardening-r6-quality-compat-green.log`). The public production matrix includes a third control with dash-quality remarks in all three roles. Scope-final ZIP/evidence/runs are superseded; final quality-final suites/render/build/smoke start after this last source change.

Quality-final retained card evidence: `tmp/round6-card-quality-evidence`, six public-GUI PDFs with full page-42 PNGs and `card-tables-contact.png` (`tmp/hardening-r6-card-quality-evidence.log`). All six tables inspected: three production cards (decimal/serial, uppercase protocol+colon remark, and dash-quality remarks in all three roles) retain exact identifying text and confirmation; absent passport, implicit absent equipment and quality-only sling drafts remain unconfirmed. No clipping/overlap; full PNGs retained. Generated after the last quality-annotation/whole-word source edit.

## Integration re-review: round 7

Base: `e4de994522c8dbbbbb687afbbd61ae5e14073bc6`. One Important finding: a numeric quality/engineering metric after a document noun incorrectly counted as that document's identity.

The central document predicate now consumes a bounded document heading followed immediately by an explicit reference marker (`№`, number/`N`/`No`/`ID`, `шифр`, registered number) and its concrete code, or by `от`/`дата` and a valid calendar date. It never searches later prose for any convenient numeric token. Unknown heading words and metric names stop the parse. Decimal capacities cannot match a truncated integer code. Number abbreviations and full-width digits normalize without changing stored/displayed text. The narrow, complete first-clause legacy format `Испытательный паспорт 123` remains supported; units, qualifiers plus bare counts, plural counts and later numeric prose cannot use that exception. No schema/migration or invented user identifier is introduced. The old synthetic compound-heading fixtures now explicitly link their existing number with `№`; their original number and release assertions remain.

Five new test methods cover 36 non-identities and 25 explicit/date/legacy controls, loaded legacy project immutability, real public-GUI physical preliminary/production cards and every advanced status. Exact reviewer strings `Паспорт: дефектов 0` and `Акт проверки (замечаний 0)`, plus a decimal capacity, produce unconfirmed preliminary cards and atomically reject REVIEW/COORDINATION/APPROVED/PRODUCTION while retaining every prior PDF/project/protocol/revision byte. All four requested positive document controls reach confirmed physical production with exact decimal sling mark/serial text. Only the isolated normative registry data path is controlled; no shipped registry row or release gate is changed.

| Document evidence | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
|---|---|---|---|---|---|
| Defect/remark count, mass/capacity/pages instead of reference | unconfirmed draft | blocked | blocked | blocked | blocked |
| Unlinked inspection date, invalid calendar date, unknown metric before a later number | unconfirmed draft | blocked | blocked | blocked | blocked |
| Explicit heading-bound document number/code or document date | eligible | eligible | eligible | eligible | eligible |
| Complete direct legacy document-name + integer first clause | eligible | eligible | eligible | eligible | eligible |

All other engineering/source/approval/regulatory gates continue to apply; checked boxes never fabricate documentary identity.

TDD and author review:

- Initial RED: **5 tests / 395.373 s / 54 assertion failures**, no fixture errors (`tmp/hardening-r7-red.log`), including actual public saves and falsely confirmed physical draft cards before the fix.
- Core GREEN **7/7 / 25.131 s** (`tmp/hardening-r7-core-green.log`); role/grammar/overflow compatibility GREEN **22/22 / 114.615 s** (`tmp/hardening-r7-compat-green.log`). Full new-module GREEN **5/5 / 185.504 s** (`tmp/hardening-r7-green.log`) before the final registration abbreviation correction.
- Registration self-review RED **1 / 5.107 s / one failure** (`Паспорт рег. №РП-42`, `tmp/hardening-r7-registration-red.log`). Explicit registered-number marker now binds numeric and alphabetic codes. Final core/older scope/overflow GREEN **10/10 / 36.855 s** (`tmp/hardening-r7-final-core-green.log`). All final suites/artifacts started after this source edit.
- Additional numeric-metric self-review: **16 negative paraphrases rejected / four linked controls accepted**, exit 0 (`tmp/hardening-r7-numeric-self-review.log`), including pressure, volume, weight, thickness, speed, height and metric-specific number/ID labels. No further source edit was needed.
- Final focused: **108/108 / 2104.564 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r7-focused-final.log`).
- Final full: **501/501 / 2525.920 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r7-full-final.log`).
- Compileall and staged/unstaged diff checks: **exit 0** (`tmp/hardening-r7-compile-final.log`), after the final source edit; no production source changed during final verification.
- Main evidence: **50 fresh pages / 50 fresh PNGs / six inspected contact sheets**, no new clipping/overlap; physical page map/canonical images retained (`tmp/hardening-r7-evidence-final.log`). `tmp/task11-evidence/full-pprk.pdf`, **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, byte-identical to the previously inspected geometry; minimum ink `0.008339601257019215`.
- Retained public-GUI card evidence: **seven PDFs/full page-42 PNGs and one inspected table contact sheet** in `tmp/round7-card-evidence` (`tmp/hardening-r7-cards-evidence.log`): defect/remark/capacity drafts are pending, all four requested linked-reference production controls are confirmed with exact text; no clipping/overlap. The first auxiliary screenshot script incorrectly expected an unverified source value to be printed on a pending card; its assertion was corrected to the existing suppression behavior before rerunning. No production code/test gate changed for this auxiliary-script correction.
- Portable build and own-runtime smoke: **exit 0 / 8364 files / six assets / 50 public-GUI pages**, strict archive/disk inventory, CRC, offline library and source/cache/secret exclusions passed (`tmp/hardening-r7-portable-final-smoke.log`). `tmp/pprk-r7-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,680,395 bytes**, SHA-256 `fed05571cf4e6436a9d319b770f24a29c872c43347f1d9ef9fa3a37d62548a36`. All **44 production Python modules + README + guide + shipped registry (47 files)** match current source bytes (`tmp/hardening-r7-artifact-verification.log`). Temporary 19-file library input moved to `tmp/hardening-r7-final-library-input` after absolute containment checks; original library/source unchanged. Own runtime invoked with `-B` from its first invocation; no inventory exemption.

Exact final commands (from this worktree, primary Python `C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`; `PYTHONPATH=05_src;06_tests`, UTF-8 output and isolated `tmp/test-temp`):

```powershell
python -m unittest test_pprk_final_round7 test_pprk_final_round6 test_pprk_final_round5 test_pprk_final_round4 test_pprk_final_round3 test_pprk_final_round2 test_pprk_final_hardening test_pprk_merge test_app_pprk_release -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tmp/round7_card_evidence.py
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r7-final
tmp/pprk-r7-final/CranePlan_Portable_3.0.1/runtime/python.exe -B 06_tests/test_full_pprk_end_to_end.py --portable tmp/pprk-r7-final/CranePlan_Portable_3.0.1
git diff --check
git diff --cached --check
```

No subagents, merge, push or publication. Parent owns independent integration re-review.

## Integration re-review: round 8

Base: `690628c4e87711ccb7beafc9e2683a091bc29f9f`. Two Important findings: date identity accepted a valid prefix of a malformed token; explicit references rejected natural document title qualifiers/conjunctions/adjectives.

Implementation plan (before production edits):

1. Reproduce complete date-token failures and natural-title false negatives through literal context corpora and real public-GUI physical/atomic assertions; preserve valid leap dates, sentence punctuation, missing/sentinel semantics and the round-7 metric corpus.
2. Preserve a linked date's complete candidate token through clause segmentation, then validate its entire format and calendar value. A malformed prefix/suffix must never become a valid date when a punctuation separator is removed. A single sentence punctuation mark remains a delimiter.
3. For an explicit reference marker only, accept alphabetic/hyphenated natural title words before it within the same clause. Stop at numeric components and clause punctuation; bind the marker to its immediate concrete code. Keep the narrower date/legacy paths and all missing-evidence gates.
4. Run core/compatibility and complete focused/full suites, compile/diff checks, regenerate/render every evidence page and exact card controls, rebuild portable and smoke it on its own runtime with `-B`, compare payload bytes, finalize documentation/ledger and one commit with a clean worktree. No merge/push/publication.

1. **Complete date identity:** a linked date candidate is preserved through clause segmentation, including malformed punctuation tails. Its entire captured value must match the date format and a real calendar date. Numeric/letter/slash/underscore/dot/hyphen prefixes or suffixes cannot be discarded to recover a valid prefix. One terminal sentence period/comma is a delimiter; doubled/malformed components remain part of the invalid candidate. A signed date is not normalized into a label. Date-only identity retains the narrower document-heading grammar, so an unrelated inspection date cannot substitute for the document's own date.
2. **Natural explicit-reference titles:** the explicit marker path consumes alphabetic/hyphenated title words, including adjectives/conjunctions, before an immediate concrete identifier. It stops at numbers and clause punctuation; initial document-label binding and the existing parenthetical reference form are retained. Missing/unverified/absent evidence is evaluated by the unchanged central semantic guards. The two exact requested natural titles and varied marker/grammar forms are supported; bare numbers after a longer title remain incomplete. No persisted schema/migration or invented user evidence is introduced.

Six new methods cover **42 malformed dates / nine valid calendar/punctuation controls / 20 natural explicit titles / 13 clause/missing controls**, plus public-GUI physical/atomic matrices. Three invalid date strings (both reviewer tails and a negative prefix) must produce unconfirmed drafts and preserve all prior PDF/project/protocol/revision bytes for all four advanced statuses. The two exact natural titles and a valid leap date must reach confirmed physical production. Only the isolated normative registry data path is controlled; no shipped row or production gate is patched.

| Evidence condition | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
|---|---|---|---|---|---|
| Malformed complete date / invalid calendar | unconfirmed draft | blocked | blocked | blocked | blocked |
| Title and reference separated by clause punctuation/newline | unconfirmed draft | blocked | blocked | blocked | blocked |
| Missing/unverified document, including an explicit number | unconfirmed draft | blocked | blocked | blocked | blocked |
| Natural same-clause title + explicit number/code | eligible | eligible | eligible | eligible | eligible |
| Complete document date, valid leap/calendar value | eligible | eligible | eligible | eligible | eligible |

Other independent engineering/source/approval/regulatory requirements still apply. Existing raw project values and flags are not promoted or rewritten.

TDD and author review:

- Original core RED **4 / 12.872 s / 28 assertion failures**, no fixture errors (`tmp/hardening-r8-core-red.log`). Original public/physical RED **6 / 334.181 s / 45 assertion failures**, no fixture errors (`tmp/hardening-r8-red.log`); actual invalid-date advanced saves succeeded before the fix, and exact natural title controls were blocked.
- Expanded date-tail/title paraphrase RED **2 / 12.616 s / 46 failures** (`tmp/hardening-r8-paraphrase-red.log`); final pre-edit core RED **4 / 17.778 s / 48 failures** (`tmp/hardening-r8-final-core-red.log`). Century leap controls and clause-boundary controls distinguish valid document dates from malformed tokens.
- Initial core attempt **6 / 28.973 s / two failures**, both `test_entire_malformed_date_token_cannot_supply_document_identity` with trailing double dots (`03.11.2026..`, `2026-11-03..`): removing one delimiter and parsing again still recovered a valid prefix. Invalid-format candidates now retain the complete original match, including that delimiter. The core log filename was reused for the rerun; the interim result remains recorded in the tool transcript and here.
- Core/round-7 compatibility GREEN **6/6 / 29.166 s / OK**, exit 0 (`tmp/hardening-r8-core-green.log`).
- Complete new-module interim GREEN **6/6 / 169.628 s / OK**, exit 0 (`tmp/hardening-r8-module-green.log`), on the date/token + natural-title implementation before the final compatibility restoration.
- Extended compatibility **26 / 134.108 s / one failure** (`tmp/hardening-r8-compat-green.log`): round-6 `test_label_colons_bind_identity_but_identified_clauses_stop_at_colon_or_dash`, positive `Протокол испытаний: №42`. The existing narrow known-heading label path was restored; expanded natural title words still stop at punctuation. Final new-date/round-7/legacy-label/quality compatibility GREEN **10/10 / 46.229 s / OK**, exit 0 (`tmp/hardening-r8-final-core-green.log`). Fresh focused/full/artifacts started after this last source edit.
- Final focused: **114/114 / 1454.425 s / OK**, exit 0, no failures/errors/skips, completed before the user-requested pause on the same frozen source (`tmp/hardening-r8-focused-final.log`). Fresh post-resume full: **507/507 / 2875.072 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r8-full-resumed-final.log`). Post-resume compileall and staged/unstaged diff checks: **exit 0** (`tmp/hardening-r8-compile-resumed-final.log`).
- Fresh evidence/render/card QA: **50 pages / 50 fresh PNGs / six inspected contact sheets**, no new clipping/overlap (`tmp/hardening-r8-evidence-final.log`). Main `tmp/task11-evidence/full-pprk.pdf`, **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, byte-identical geometry; minimum ink `0.008339601257019215`. Six retained public-GUI PDFs/full page-42 PNGs and one inspected table contact in `tmp/round8-card-evidence`: three invalid-date drafts pending, exact two natural titles and valid leap date confirmed in production; exact text retained, no clipping (`tmp/hardening-r8-cards-evidence.log`).
- Portable rebuild/own-runtime/payload verification: **exit 0 / 8364 files / six assets / 50 public-GUI pages**, strict CRC/archive-disk inventory/offline/source/cache/secret checks passed (`tmp/hardening-r8-portable-final-smoke.log`). `tmp/pprk-r8-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,681,617 bytes**, SHA-256 `13474b98e77561dcb2cf696772b80dd344262c210c297cad0ad03ad5e45d7a37`. All **44 production Python modules + README + guide + registry (47 files)** match current bytes; temporary 19-file library input moved to `tmp/hardening-r8-final-library-input` after absolute containment checks; original library/source unchanged. Own runtime invoked with `-B` from its first call (`tmp/hardening-r8-artifact-verification.log`).
- Additional legacy-load self-review: **six literal date/title cases**, saved and loaded through real project IO, pass expected derived confirmation while retaining raw text, checked flags, saved JSON bytes and original caller (`tmp/hardening-r8-artifact-verification.log`); no source change required.

The user-requested pause was saved as checkpoint `99e961effb9f1a04d1146df295866d7915e607cf`. After `ГО`, the entire 507-test suite was rerun from that clean, frozen checkpoint with worktree `TEMP`/`TMP`. The interrupted pre-pause `tmp/hardening-r8-full-final.log` is excluded from completion evidence regardless of its terminal text. The completion commit is added above the checkpoint without rewriting it; only this report, the ledger and checkpoint record change. Production/test/README/guide payload is unchanged, so the existing ZIP is retained as instructed. Post-commit runtime/hash/payload confirmation uses the commands below and is recorded in the completion handoff.

Exact final commands (primary Python and UTF-8/isolated temporary environment as above):

```powershell
python -m unittest test_pprk_final_round8 test_pprk_final_round7 test_pprk_final_round6 test_pprk_final_round5 test_pprk_final_round4 test_pprk_final_round3 test_pprk_final_round2 test_pprk_final_hardening test_pprk_merge test_app_pprk_release -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tmp/round8_card_evidence.py
python tmp/round8_artifact_verification.py
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r8-final
tmp/pprk-r8-final/CranePlan_Portable_3.0.1/runtime/python.exe -B 06_tests/test_full_pprk_end_to_end.py --portable tmp/pprk-r8-final/CranePlan_Portable_3.0.1
git diff --check
git diff --cached --check
```

Post-commit artifact confirmation (same primary Python / `PYTHONPATH=05_src;06_tests` / worktree temporary environment):

```powershell
python tmp/round8_artifact_verification.py
tmp/pprk-r8-final/CranePlan_Portable_3.0.1/runtime/python.exe -B 06_tests/test_full_pprk_end_to_end.py --portable tmp/pprk-r8-final/CranePlan_Portable_3.0.1
```

No subagents, merge, push or publication. Parent owns independent integration re-review.

## Integration re-review: round 9

Base `5635f19cfd0f43ec344f8be9d09ccec96d0b7833`. One Important finding: the explicit-reference title path accepted arbitrary prose and borrowed a page/test/application reference as the document's own identity.

Plan before production edits:

1. Reproduce exact reviewer strings, relational paraphrases, nominal title controls, malformed phrase grammar, saved legacy values, physical preliminary/production cards and all advanced atomic gates with real consumers.
2. Replace arbitrary alphabetic words with an explainable positive nominal-token classifier: domain noun case forms, technical adjective families with standard case endings and hyphenated terms, conjunction `и`, and only the existing initial nominal `для`/`о` constructions with an actual noun head. Unknown words, finite verbs, relational/locative prepositions and incomplete phrases fail closed. Keep immediate explicit marker/code binding; use `Акт №42` as the documented fallback.
3. Permit the explicitly requested optional colon before a marker. Preserve colon-versus-dash identity during existing label binding so this permission cannot cross a dash boundary. Move the prior round-8 colon negative to its newly authorized positive contract; preserve the dash negative and all other role/date/missing semantics.
4. Freeze the source after core/public compatibility GREEN, then fresh focused/full suites, compile/diff checks, complete evidence/card render inspection, portable rebuild/own-runtime/payload checks, report/ledger and one completion commit. No further scope expansion, spawn, merge, push or publication.

The explicit-reference path now uses a positive token classifier: a small case-specific domain noun vocabulary, technical adjective families with ordinary Russian case endings and hyphenated combining forms, conjunction `и`, and the existing initial `для`/`о` nominal constructions with a required noun head. It does not enumerate bad sentences. Unknown words, finite/relational predicates, locative/reference prepositions, incomplete conjunction/preposition phrases and page/test/application nouns fail closed. The marker must immediately follow the completed nominal title (optionally one colon or the existing parenthetical marker form). An attribute/approved introductory prefix check prevents jumping to a different document name inside a relational sentence; `По паспорту №123` and `Согласно протоколу №42` remain supported. Short `Акт №42` is the documented fallback for an unknown expanded title.

Colon and dash are retained as different separators when an unnumbered label is bound. This is required by the explicitly permitted optional colon: treating every dash as a colon would incorrectly borrow a marker across a clause boundary. Existing labeled sling/type/quality behavior is retained; complete date-token rules are unchanged. The old round-8 `Акт проверки и испытаний: №42` negative moves to the positive corpus under the explicit round-9 requirement; its dash counterpart remains negative. No persisted schema/migration, fabricated identifier or trust-flag promotion is introduced.

Six new methods exercise **29 relational/borrowed-reference negatives / 18 incomplete-or-punctuation negatives / 16 nominal controls plus all 21 current round-8 title controls**, real legacy load immutability, three pending physical draft cases with all four advanced atomic gates, and four confirmed physical production controls. The normative fixture controls only the existing isolated data path; no release gate or shipped regulatory row is patched.

| Evidence condition | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
|---|---|---|---|---|---|
| Relational prose / page, test or application reference | unconfirmed draft | blocked | blocked | blocked | blocked |
| Incomplete nominal phrase / crossed punctuation / missing document | unconfirmed draft | blocked | blocked | blocked | blocked |
| Nominal title + own explicit marker/code, optional colon | eligible | eligible | eligible | eligible | eligible |
| Short named document + own explicit marker/code | eligible | eligible | eligible | eligible | eligible |

All other independent engineering/source/approval/normative requirements still apply. Original text and checked flags are retained and reevaluated fail closed.

TDD: initial complete RED **6 / 447.729 s / 60 assertion failures**, no fixture errors (`tmp/hardening-r9-red.log`). Final initial core RED **4 / 19.279 s / 45 failures** (`tmp/hardening-r9-core-red.log`); owner-jump self-review RED **1 / 6.683 s / 29 failures**, including the three nested document-reference cases (`tmp/hardening-r9-owner-red.log`). Core/new/old date/marker/label compatibility GREEN **10/10 / 57.570 s / OK**, exit 0 (`tmp/hardening-r9-core-green.log`).

Complete new module GREEN **6/6 / 207.542 s / OK**, exit 0 (`tmp/hardening-r9-module-green.log`). Extended role/date/label/quality/overflow compatibility GREEN **30/30 / 167.426 s / OK**, exit 0 (`tmp/hardening-r9-compat-green.log`). No production edit followed these results; all final runs/artifacts started from this frozen source.
Final focused **120/120 / 2382.286 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r9-focused-final.log`). Final full **513/513 / 2665.248 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r9-full-final.log`). Final compileall and staged/unstaged diff checks **exit 0** (`tmp/hardening-r9-compile-final.log`). No production edit after the frozen-source compatibility results; no final verification run was superseded.
Evidence: **50 fresh pages / 50 PNGs / six inspected contact sheets**, no new clipping/overlap, canonical images and page map retained (`tmp/hardening-r9-evidence-final.log`). Main `tmp/task11-evidence/full-pprk.pdf`, **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, minimum ink `0.008339601257019215`. Seven retained public-GUI PDFs/full page-42 PNGs and one inspected table contact in `tmp/round9-card-evidence`: exact two reviewer strings plus application reference pending; four nominal/colon production controls confirmed with exact text and no clipping (`tmp/hardening-r9-cards-evidence.log`).

Portable rebuild: `tmp/pprk-r9-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,642,193 bytes**, SHA-256 `9c75d88d6d83c482e0df04bd84b29d4e4429616e0a00b92af7cf69e2a3a37688`. Own-runtime `-B` smoke **8364 files / six assets / 50 public-GUI pages**, exit 0, with strict CRC/inventory/offline/source/cache/secret checks (`tmp/hardening-r9-portable-final-smoke.log`). All **47 production Python/README/guide/registry files** match current source bytes. Temporary 19-file library input moved to `tmp/hardening-r9-final-library-input` after absolute containment checks; original library/source unchanged. Seven real save/load self-review cases retain raw text/checked flags/project JSON bytes/caller while deriving expected confirmation (`tmp/hardening-r9-artifact-verification.log`).

Exact final commands (primary Python/UTF-8/worktree `TEMP`/`TMP` as above):

```powershell
python -m unittest test_pprk_final_round9 test_pprk_final_round8 test_pprk_final_round7 test_pprk_final_round6 test_pprk_final_round5 test_pprk_final_round4 test_pprk_final_round3 test_pprk_final_round2 test_pprk_final_hardening test_pprk_merge test_app_pprk_release -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tmp/round9_card_evidence.py
python tmp/round9_artifact_verification.py
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r9-final
tmp/pprk-r9-final/CranePlan_Portable_3.0.1/runtime/python.exe -B 06_tests/test_full_pprk_end_to_end.py --portable tmp/pprk-r9-final/CranePlan_Portable_3.0.1
git diff --check
git diff --cached --check
```

No spawn, merge, push or publication; parent owns independent integration re-review.

## Integration re-review: round 10

Base `b9b42dfce20fd7a9af1daa1aee88a1823b748ed8`. One Important finding: the existing owner/prefix guard protected explicit numbers but not linked dates, allowing a nested document inside relational prose to supply date identity.

Plan before production edits: reproduce exact nested dates, colon/dash/heading boundaries, immutable legacy strings/flags, public physical drafts and all advanced atomic gates; retain direct dates, currently valid natural date headings and exact `По акту приёма-передачи оснастки №42`. Apply the same existing owner/prefix guard before either reference branch, without changing title/date vocabulary, calendar rules, persistence, trust flags or other gates. Then targeted focused and entirely fresh full suites, compile/diff, complete evidence/card render inspection, portable rebuild/own-runtime/payload checks and one commit. No other scope, spawn, merge, push or publication.

Resolution: `_document_reference_prefix` is evaluated once for each document-name candidate before either explicit-number or date acceptance. A rejected owner prefix skips that candidate; it cannot jump to a nested act/passport across relational prose, colon or dash. The same existing number guard and all date-heading vocabulary, complete-token/calendar validation, persistence and fail-closed release rules are retained. Production diff is three added/two removed lines in one predicate; no wider identity grammar or other behavior is changed.

TDD baseline before the production edit: four semantic/legacy methods completed in **12.490 s**, with **15 assertion failures** and no fixture errors (`tmp/hardening-r10-core-red.log`). The full new-module RED additionally reproduced a physically confirmed bad draft and incorrect advanced public-GUI saves for the first exact reviewer string. That expected-RED process was deliberately interrupted after these failures; its incomplete run is not counted as a completed suite (`tmp/hardening-r10-red.log`). No source was edited before those failures were observed.

New corpus: **12 relational/nested-date negatives, 12 direct-date/natural-heading positives, six punctuation/heading-boundary negatives and the exact approved number control** `По акту приёма-передачи оснастки №42`. Exact reviewer negatives, nested titles and qualifiers, colon/dash owner jumps and original R8/R9 controls are covered. Two real legacy round trips retain raw strings and the checked flag, derive no false confirmation and leave saved JSON bytes unchanged. Additional manual self-review runs seven real round trips, also retaining caller data.

| Public GUI case | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
| --- | --- | --- | --- | --- | --- |
| `Паспорт содержит ссылку на акт от 03.11.2026` | physical pending card | blocked atomically | blocked atomically | blocked atomically | blocked atomically |
| `Акт приложен к паспорту от 2024-02-29` | physical pending card | blocked atomically | blocked atomically | blocked atomically | blocked atomically |
| `Паспорт содержит ссылку: акт от 03.11.2026` | physical pending card | blocked atomically | blocked atomically | blocked atomically | blocked atomically |
| Direct act date, leap-valid passport date, existing natural passport title and approved nominal number | semantic eligibility retained | existing policy | existing policy | existing policy | four physical confirmed controls |

Each blocked save checks the existing preliminary, production and four status PDFs, project JSON, protocol and revision sidecars byte for byte and checks `PPRK_RIGGING_EVIDENCE_REQUIRED` at prepare/require. Physical controls use the public GUI and real generated pages; only the isolated normative registry data path is controlled, no production gate or shipped registry row is patched.

Evidence regenerated from the frozen source: **50 physical pages / 50 PNGs / six contact sheets**, all visually inspected without new clipping or overlap. Main PDF **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, minimum ink `0.008339601257019215`. Seven additional public-GUI cards are retained under `tmp/round10-card-evidence` for three pending nested-date drafts and four valid production controls.

Portable rebuild `tmp/pprk-r10-final/CranePlan_Portable_3.0.1_Windows.zip`: **174,642,468 bytes**, SHA-256 `328294d40940c5f97a2065a35450aa79a9a5a83fb223d20966b83c84c1999a7c`. Builder and own-runtime `-B` smoke exit 0; **8364 files / six canonical assets / 50 GUI pages**, strict CRC/inventory/offline/source/cache/secret checks pass. All **47 payload source/README/guide/registry files** match current bytes. After containment checks, the temporary 19-file library copy is retained at `tmp/hardening-r10-final-library-input`; originals are unchanged. Artifact and seven real legacy IO checks exit 0 in `tmp/hardening-r10-artifact-verification.log`.

Final new-module GREEN **6/6 / 272.015 s**, focused R7–R10 **23/23 / 884.477 s** (`tmp/hardening-r10-focused-final.log`) and entirely fresh full **519/519 / 2332.027 s** (`tmp/hardening-r10-full-final.log`), all **OK / exit 0 / no failures, errors or skips**. Compileall and unstaged/staged diff checks exit 0 (`tmp/hardening-r10-compile-final.log`). All final runs and artifacts correspond to the frozen minimal production edit; none was interrupted or superseded. Seven card table crops were visually inspected together: no false confirmation, missing-field contradiction, new clipping or overlap. The shared guard, required negative/positive public paths and unchanged legacy persistence were self-reviewed; no further scope expansion.

Exact commands (primary Python, UTF-8 and worktree `TEMP`/`TMP` as above):

```powershell
python -m unittest test_pprk_final_round10 -v
python -m unittest test_pprk_final_round10.Round10Tests.test_relational_nested_document_dates_do_not_supply_identity test_pprk_final_round10.Round10Tests.test_direct_dates_existing_natural_headers_and_approved_number_stay_valid test_pprk_final_round10.Round10Tests.test_date_owner_binding_does_not_cross_punctuation_or_heading_boundaries test_pprk_final_round10.Round10Tests.test_loaded_nested_date_strings_and_flags_are_retained_without_confirmation -v
python -m unittest test_pprk_final_round10 test_pprk_final_round9 test_pprk_final_round8 test_pprk_final_round7 -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tmp/round10_card_evidence.py
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r10-final
tmp/pprk-r10-final/CranePlan_Portable_3.0.1/runtime/python.exe -B 06_tests/test_full_pprk_end_to_end.py --portable tmp/pprk-r10-final/CranePlan_Portable_3.0.1
python tmp/round10_artifact_verification.py
git diff --check
git diff --cached --check
```

No spawn, merge, push or publication; parent owns independent integration re-review.

## Integration re-review: round 11

Base `55e86fc82ebe398fb4461f6afb0f4e79c0154c07`. One Important root cause: clause segmentation treated any numeric token before a colon/dash as identification and discarded the left owner context, allowing an independently valid nested reference to confirm the field.

Plan before production edits: TDD numeric-count classes across colon/dash, all three field roles, raw legacy text/flags, physical public drafts and every advanced atomic gate. Replace incidental-token/label heuristics with the same role-specific positive identity predicate already selected by the field; retain owner context when that predicate is false. Preserve explicit number/ID/code/direct-date identities, approved nominal titles and existing labels. No phrase blacklist, document grammar expansion, schema/persistence or other release-policy change. Then focused R6–R11, fresh full, compile/diff, all-page/card visual evidence, portable rebuild/own-runtime/payload checks and one commit. No spawn, merge, push or publication.

Resolution: `_rigging_clauses` receives the already selected typed role identity predicate. Only that predicate can establish an identified left side and permit a new colon/dash clause. Otherwise the complete left context and original separator remain attached to the next fragment. The generic label/any-concrete-token heuristic is removed, including its non-label fallback; incidental counts cannot expose a standalone nested document, equipment type or sling mark. No document-title/date grammar, semantic vocabulary, schema/persistence, trust flag or other gate is changed.

TDD baseline: four new semantic/legacy methods completed in **20.558 s**, with **41 assertion failures**, no fixture errors (`tmp/hardening-r11-core-red.log`). The separate public physical baseline reproduced a falsely confirmed draft and an incorrect REVIEW save for exact `Паспорт содержит 1 ссылку: акт от 03.11.2026`; it was deliberately interrupted after those expected failures and is not counted as a completed suite (`tmp/hardening-r11-physical-red.log`). The subsequent core GREEN **6/6 / 25.025 s / OK**, exit 0, includes four new semantic/legacy methods and two existing R6 label/absence-scope methods (`tmp/hardening-r11-core-green.log`).

At the coordinator's explicit acceleration instruction, the redundant focused R6–R11 process was intentionally stopped after all six R11 methods had passed (plus partial R10), before suite completion (`tmp/hardening-r11-focused-final.log`). It is not counted as a completed focused suite and is not restarted. The fresh full process was never stopped or restarted and continues alone after the already completed artifact jobs. Targeted core GREEN plus the fresh full suite are the final verification basis.

Corpus: **33 numeric-owner document negatives, eight cross-role owner-context negatives and 19 role-specific positive controls**. It covers counts of links/pages/tests/defects, mass/capacity, number/code/date nested references, repeated separators, unlabelled preambles, explicit number/ID/code/direct-date identities, nominal titles and existing labels. Additional self-review checks **120 combinations** of four headings, three separators and ten numeric forms (zero, large/leading-zero/fullwidth values, decimals and negatives), all rejected without patched functions (`tmp/hardening-r11-number-self-review.log`). Its first manual invocation omitted `PYTHONPATH` and failed to import; the corrected environment passed, with no code change. Two real legacy regressions and seven additional round trips preserve raw fields, checked flags, saved JSON bytes and caller data while deriving the expected confirmation.

| Public GUI case | PRELIMINARY | REVIEW | COORDINATION | APPROVED | PRODUCTION |
| --- | --- | --- | --- | --- | --- |
| `Паспорт содержит 1 ссылку: акт от 03.11.2026` | physical pending card | blocked atomically | blocked atomically | blocked atomically | blocked atomically |
| `Акт содержит 1 ссылку — паспорт от 2024-02-29` | physical pending card | blocked atomically | blocked atomically | blocked atomically | blocked atomically |
| `Акт содержит 12 страниц: паспорт от 2024-02-29` | physical pending card | blocked atomically | blocked atomically | blocked atomically | blocked atomically |
| `Паспорт №1: дефектов нет`, `Акт №1 — рисков нет`, direct act date and approved nominal number | semantic eligibility retained | existing policy | existing policy | existing policy | four physical confirmed controls |

Each blocked GUI save preserves existing preliminary/production/status PDFs, project JSON, protocol and revision sidecars byte for byte; prepare/require explicitly report `PPRK_RIGGING_EVIDENCE_REQUIRED`. Tests use actual public GUI saves and physical PDF text; the verified normative fixture controls only an isolated data path and patches no production gate or shipped registry row.

Fresh evidence: **50 pages / 50 PNGs / six visually inspected contacts**, no new clipping/overlap, canonical assets and ordered page map retained. PDF **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, minimum ink `0.008339601257019215`. Seven public-GUI card pages and their table contact under `tmp/round11-card-evidence` were inspected: three pending drafts, four confirmed production controls, no false confirmation or placeholder contradiction.

Portable `tmp/pprk-r11-final/CranePlan_Portable_3.0.1_Windows.zip`: **174,642,723 bytes**, SHA-256 `0f72aacc380f7cf0ba759f7c46c1f89b885ffa59abe79b7fa2b0c854253a0da6`. Builder and own-runtime `-B` smoke exit 0: **8364 files / six assets / 50 GUI pages**, strict CRC/inventory/offline/source/cache/secret checks pass. All **47 payload source/README/guide/registry files** match current bytes. The temporary 19-file library copy is retained after containment checks at `tmp/hardening-r11-final-library-input`; originals unchanged. Artifact and seven real legacy checks exit 0 in `tmp/hardening-r11-artifact-verification.log`.

Final verification basis: targeted core **6/6 / 25.025 s / OK**, exit 0, and entirely fresh full **525/525 / 2494.732 s / OK**, exit 0 (`tmp/hardening-r11-full-final.log`), no failures/errors/skips. The full run was never interrupted or superseded; after the coordinator stopped only the redundant focused process, it ran alone. All six R11 methods passed within full. The partial focused is explicitly not reported as a completed suite. Final compileall and staged/unstaged diff checks exit 0 (`tmp/hardening-r11-compile-final.log`). All evidence, payload and smoke correspond to the frozen production source; no further behavior/grammar edits occurred. Self-review confirms the arbitrary-number class, supported role identities and raw legacy persistence, without phrase patches or scope expansion.

Exact commands (primary Python, UTF-8 and worktree `TEMP`/`TMP` as above):

```powershell
python -m unittest test_pprk_final_round11.Round11Tests.test_arbitrary_number_before_separator_does_not_discard_document_owner test_pprk_final_round11.Round11Tests.test_unidentified_owner_context_survives_separators_for_each_role test_pprk_final_round11.Round11Tests.test_role_specific_identified_left_sides_and_supported_labels_stay_valid test_pprk_final_round11.Round11Tests.test_loaded_numeric_prose_and_checked_flags_are_retained_without_confirmation -v
python -m unittest test_pprk_final_round11.Round11Tests.test_numeric_owner_cards_are_pending_and_all_advanced_gui_saves_are_atomic -v
python -m unittest test_pprk_final_round11.Round11Tests.test_arbitrary_number_before_separator_does_not_discard_document_owner test_pprk_final_round11.Round11Tests.test_unidentified_owner_context_survives_separators_for_each_role test_pprk_final_round11.Round11Tests.test_role_specific_identified_left_sides_and_supported_labels_stay_valid test_pprk_final_round11.Round11Tests.test_loaded_numeric_prose_and_checked_flags_are_retained_without_confirmation test_pprk_final_round6.Round6Tests.test_label_colons_bind_identity_but_identified_clauses_stop_at_colon_or_dash test_pprk_final_round6.Round6Tests.test_implicit_role_absence_and_uppercase_clause_binding_use_one_scope -v
python -m unittest test_pprk_final_round11 test_pprk_final_round10 test_pprk_final_round9 test_pprk_final_round8 test_pprk_final_round7 test_pprk_final_round6 -v
python -m unittest discover -s 06_tests -v
python -m compileall -q 05_src tools 06_tests
python 06_tests/test_full_pprk_end_to_end.py --evidence
python tmp/round11_card_evidence.py
python tools/build_portable_release.py --runtime C:/Users/Владимир/.cache/codex-runtimes/codex-primary-runtime/dependencies/python --output tmp/pprk-r11-final
tmp/pprk-r11-final/CranePlan_Portable_3.0.1/runtime/python.exe -B 06_tests/test_full_pprk_end_to_end.py --portable tmp/pprk-r11-final/CranePlan_Portable_3.0.1
python tmp/round11_artifact_verification.py
git diff --check
git diff --cached --check
```

No spawn, merge, push or publication; parent owns independent integration re-review.

