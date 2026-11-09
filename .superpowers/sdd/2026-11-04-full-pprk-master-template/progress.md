# SDD ledger — plan: docs/superpowers/plans/2026-11-04-full-pprk-master-template.md

Workspace: `C:/Users/Владимир/Documents/Codex/2026-09-30/files-pasted-by-the-user-senior/crane_plan/.worktrees/full-pprk-master-template`
Branch: `codex/full-pprk-master-template`
Baseline: `a0fd87d`; 257 unittest tests passed, 0 failures, with TEMP/TMP set to `tmp/test-temp`.

## Pre-flight conflict scan

| Scope | Producer / test | Consumer / code | Finding / ruling |
|---|---|---|---|
| Task 1 | Asset manifest and validator | Task 8 appendix renderer | Clean: Task 8 consumes stable asset IDs and checksums from Task 1. |
| Task 2 | Release dataclasses and schema v4 | Tasks 3, 5, 9, 10 | Clean: serialization precedes all consumers. |
| Task 3 | Template catalog and overrides | Tasks 5 and 6 | Clean: composer selects sections; renderer only lays them out. |
| Task 4 | Traceable `PPRKContext` | Tasks 5 and 7 | Clean: no engineering recalculation is allowed downstream. |
| Task 5 | Immutable bundle and numbering | Tasks 6–10 | Clean: bundle is the single composition source. |
| Tasks 6/7/8/9 | All modify `report.py` | Sequential integration | Ruling: keep `generate_report()` backward compatible and have each task rebase on prior task; do not parallelize implementers. |
| Tasks 6/7 | Text report and calculated sheets | Task 10 preview UI | Clean: UI consumes finished bundle/report API. |
| Task 8 | Exact clips and dynamic tables | Task 11 visual QA | Clean: checksum/proportion checks are repeated end to end. |
| Task 9 | External PDF merge | Task 11 mixed-format fixture | Clean: Task 11 verifies actual integrated output. |
| Task 10 | Preview hash and release guards | Task 11 end-to-end release | Clean: stale-preview behavior is pinned before final fixture. |
| Task 1 self-check | Tests require OCR forbidden-string scan | Validator implementation | Ruling: OCR is best-effort; deterministic filename/manifest/checksum and visual QA remain mandatory. Do not add a new OCR dependency. |
| Task 2 self-check | Dataclass tests vs schema migration | `ProjectInput` change | Clean: defaults preserve current callers. |
| Task 3 self-check | Full catalog vs strict placeholders | JSON resource and renderer | Clean: stable paragraph IDs prevent override loss. |
| Task 4 self-check | Traces required for every numeric output | Existing verification protocol | Ruling: when the engine lacks a source field, emit an explicit missing trace and completeness issue; never invent provenance. |
| Task 5 self-check | Exact first-four-page order | Composer implementation | Clean. |
| Task 6 self-check | PDF order/text tests | A4 service-page renderer | Clean. |
| Task 7 self-check | A3/A2/A1 selection | Existing report supports A3/A4 only | Ruling: introduce A2/A1 through ReportLab page-size tuples without changing existing drawing geometry APIs. |
| Task 8 self-check | Exact clip checksums | PDF embedding may decode/re-encode | Ruling: validate source asset bytes before rendering; final PDF verifies dimensions/visual identity, not embedded-stream byte identity. |
| Task 9 self-check | Preserve mixed page sizes | pypdf atomic merge | Clean. |
| Task 10 self-check | UI tests and release guards | Existing report tab | Clean: extend current tab, do not create a second workflow. |
| Task 11 self-check | Full regression and portable build | All prior tasks | Clean. |
| Test runner | Plan says `pytest` | Bundled runtime has no pytest | Ruling: use `python -m unittest` equivalents and always set TEMP/TMP inside the worktree; no network dependency installation is needed. The GUI integration save test also pins its own temporary project directory under `tmp/test-temp` and captures `showerror`, preventing Windows Sandbox temp failures from opening a misleading real dialog. |
| Reference PDF | Task 1 needs source outside repo | Read-only extraction | Ruling: use `F:/работа/аспирантура/апробация/ППРк_Труженников пер (1).pdf`; do not modify or package the source PDF. |

## Task status

- Task 1: complete; implementation `63215bf`, fix round 1 `17e0530`; scoped re-review found no Critical/Important/Minor issues; focused 12/12 and full 267/267 passed
- Task 2: complete; implementation `4806b56`; fresh review found no Critical/Important/Minor issues; focused 34/34 and full 274/274 passed
- Task 3: complete; implementation `7311276`, fix rounds `b6d3f76`, `ce58a05`, `0803784`; final scoped review found no Critical/Important/Minor issues; 14/14 focused and 288/288 full tests passed
- Task 4: complete; implementation `1d54b8a`, fix rounds `be0e43c`, `312d568`, `6bc851a`; final scoped review found no Critical/Important/Minor issues; 39/39 integration and 299/299 full tests passed
- Task 5: complete; implementation `104c259`, fix rounds `a372c82`, `5386e0b`, `1fb4b18`; final scoped review found no Critical/Important/Minor issues; 319/319 full tests passed
- Task 6: complete; implementation `c1f62cc`, fix rounds `6b1bfb3`, `427c1db`; final scoped review found no Critical/Important/Minor issues; 330/330 full tests passed
- Task 7: complete; implementation `743a8c3`, fix rounds through `fb29121`; scoped review clean; 355/355 full tests passed
- Task 8: complete; implementation `b310b20`, fix round `0a08bb7`; scoped review clean; 374/374 full tests passed
- Task 9: complete; implementation `3593969`, fix round `f1d9659`; scoped review clean; 393/393 full tests passed
- Task 10: complete; implementation `1a16600`, fix round `0025795`; scoped re-review clean; 411/411 full tests passed
- Task 11: implementation `1e4e116`, fix rounds `41534e0`, `dff1c04`; round 2 canonical-protocol Important addressed; targeted 38/38 + 25/25 and full 428/428 passed; portable rebuilt with 49-page GUI-save smoke; scoped re-review pending

## Pause checkpoint — 2026-11-04

User requested an immediate pause before shutting down the laptop. Worktree is clean at `b857c37` (`fix: bind and expand calculated PPRk sheets`); no round-2 partial edits exist.

Resume Task 7 fix round 2 from the accepted review findings:

1. Store and enforce a canonical hash/snapshot of every `ScenarioResult` field consumed by drawings; reject changed status, accepted height, sectors, ties, routes, SOZR or joint-work data.
2. Include the actual section contour in vertical-format bounds and fail closed beyond A1.
3. Split load schedules from measured wrapped ReportLab row heights, not fixed row counts.
4. In bundle mode, transfer the verified danger-zone envelope from `PPRKContext`; do not call the legacy normative recalculation helper.
5. Measure and split/fail-close long SOZR point tables as well as load schedules.
6. Feed the physical-sheet page map into the rendered contents/references, not only an assertion.
7. Unknown legacy graphical references must be preserved or rejected explicitly; never silently disappear during expansion.

After implementation: rerun focused/full tests, visual QA, scoped re-review, then mark Task 7 complete. Do not start Task 8 before Task 7 is clean.

Task 7: fix round 2/5 (5 addressed, 2 open — appendix references incorrectly validated against drawing-only page map; vertical planner omits rendered free-standing elevation and calibrated coordinates; commits b857c37..902201c)
Task 7: fix round 3/5 (1 addressed, 1 open — calibrated vertical preflight omits crane-symbol/offset/dimension envelope; commits 902201c..c4b4f5d)
Task 7: fix round 4/5 (1 addressed, 1 open — calibrated lower note intersects mast; commits c4b4f5d..7b035d2)
Task 7: fix round 5/5 (1 addressed, 0 open; commits 7b035d2..fb29121)
Task 7: complete (commits 743a8c3..fb29121, final scoped review clean; 355/355 full tests passed)
Task 8: fix round 1/5 (3 addressed, 0 open; commits b310b20..0a08bb7)
Task 8: complete (commits b310b20..0a08bb7, scoped review clean; 374/374 full tests passed)
Task 9: fix round 1/5 (2 addressed, 0 open; commits 3593969..f1d9659)
Task 9: complete (commits 3593969..f1d9659, scoped review clean; 393/393 full tests passed)
Task 10: fix round 1/5 (4 addressed, 0 open; commits 1a16600..0025795)
Task 10: complete (commits 1a16600..0025795, scoped re-review clean; 411/411 full tests passed)

Task 11: Ruling: real gui_adapter intentionally marks every tie-in scenario TIE_INS_NOT_VERIFIED; primary E2E therefore asserts a real independent VALID two-crane protocol plus integration EXPERT_REVIEW_REQUIRED and full preliminary output; a companion case without ties is VERIFIED_WITH_CONDITIONS. Do not forge VERIFIED or relax engineering policy for the fixture.
Task 11: implementation ready (commits 0025795..1e4e116; focused 102/102, full unittest 420/420, compileall and staged/worktree diff checks passed; 49-page PDF / all PNGs / six contact sheets reviewed; portable 8362 files and six assets verified and own runtime generated 49 pages; scoped review pending)

Task 11: fix round 1/5 (3 Important addressed, 0 unaddressed; commit 41534e0): shared planner/PDF sector normalization including reverse/full/tiny arcs RED→GREEN; actual GUI preliminary tie-in save RED→GREEN with fatal/rejected/protocol/stale/scenario guards; exact ordered 49-part/page map and external ID/range binding RED→GREEN with physical/title/range mutation negatives.
Task 11: fix round 1 verified — focused 144/144, full unittest 425/425, compileall, staged/worktree diff-check passed; GUI-save artifact 49 pages, all PNGs/contact sheets re-rendered and inspected; rebuilt tmp/task11-portable-review1/CranePlan_Portable_3.0.1_Windows.zip (174658679 bytes, SHA256 c092e6525519b37125148481bff31faf8d6ca54bfa1c6fb7d71813748745e226); own runtime 8362 files/6 assets and 49-page GUI-save smoke passed; scoped re-review pending.

Task 11: fix round 2/5 (1 Important addressed, 0 unaddressed; commit dff1c04): saving now compares all serialized protocol fields with the canonical engine-result protocol using the existing canonical snapshot serializer; foreign real index-1 protocol on index-0 verification RED→GREEN, prior output/sidecars preserved, all 17 field mutations + nested mass/crane-ID mutations rejected, typed canonical JSON-roundtrip equivalent accepted.
Task 11: fix round 2 verified — targeted 38/38 + 25/25, full unittest 428/428 (233.290 s), compileall and staged/worktree diff-check passed; new tmp/task11-portable-review2/CranePlan_Portable_3.0.1_Windows.zip (174658935 bytes, SHA256 66ea731f5a7dee7330b7796fb30a8cb211f60da107a4411b8134076567dd755f), own runtime 8362 files/6 assets/49-page GUI-save smoke passed; scoped re-review pending.

## Final integration hardening — complete after user-authorized resume

Checkpoint `92a00fc` retained unchanged; completion is a new commit above it. The following list closes the nine Important findings in `final-hardening-brief.md`; report: `final-hardening-report.md`.

- Final: fixed vertical geometry — actual 32.4/42.4 m mast axes, physical PDF rectangles and section/schedule clearance equation RED→GREEN.
- Final: fixed mandatory external evidence — three unconditional IDs plus conditional tie/screen IDs; immutable required-ID set reapplied during actual assembly, including a disappeared file with `required=False` RED→GREEN.
- Final: fixed screen mitigation transfer — canonical passed mitigation selects verified screen sheet and requires its external project; physical preliminary sheet/register and advanced status blockers checked.
- Final: fixed normative registry — immutable metadata/validity records, actual names in PDF, exact issue date and unverified/expired gates RED→GREEN; real registry statuses unchanged.
- Final: fixed forbidden reference leakage — inputs + physical text/Info/XMP, bundle and public legacy API, before atomic replacement; old-output preservation RED→GREEN.
- Final: fixed rigging completeness — explicit defaulted persisted/editor fields, source/protocol evidence, physical confirmed production card without missing markers; legacy load stays unconfirmed.
- Final: fixed selected variant identity — canonical scenario number plus protocol identity on all nine calculated pages; nonfirst physical scenario checked.
- Final: fixed requisites — frozen release-card snapshot shared by planning/stamps/SOZR; physical old/new tokens and original-project immutability checked.
- Final: fixed internal-only contents — 38 active loads, multiple continuation leaves and exact physical page map; production text, expanded card titles and appendix layouts measured during preparation. Oversized cases RED→GREEN with exact blockers.

Ruling: additive schema-4 primitive defaults are the minimal compatible migration — no historical issue date or rigging approval is fabricated and loading does not rewrite source files.
Ruling: advanced external-document gating means COORDINATION/APPROVED/PRODUCTION — REVIEW can retain pending external records, while missing rigging/appendix data keeps the pre-existing preliminary-only rule.
Ruling: implementation/catalog/reference registry labels do not prove legal verification — actual unresolved rows remain blockers; controlled verified copies exist only in isolated tests.
Ruling: the final portable folder was shortened to `tmp/pprk-final` after the Windows DLL loader rejected the long intermediate path — identical archive bytes were retained, then the actual packaged runtime passed.

Fresh verification: focused `python -m unittest test_pprk_final_hardening test_app_engine_integration test_pprk_merge -v` → 53/53, 84.851 s; full `python -m unittest discover -s 06_tests -v` → 446/446, 342.410 s, no failures/errors/skips. Bundled Python, worktree-local TEMP/TMP and PYTHONPATH=05_src;06_tests. Compileall and staged/unstaged whitespace checks passed.

Evidence: 50-page PDF, 50 PNGs / six contact sheets inspected; targeted page 31/38/42 inspection and exact image/page-map assertions. PDF 15,189,892 bytes, SHA-256 `ae878b2b289fe38708175ceebfebdf2d9b94f6ed830baaf25d71623a68923915`.

Final portable: `tmp/pprk-final/CranePlan_Portable_3.0.1_Windows.zip`, 174,667,848 bytes, SHA-256 `3aceaf36c727e5b908e8d1d918f75921bfce2bbf4b0e3217a111d10a7871bd22`. Own runtime: 8364 files / six assets / 50-page GUI-save smoke; CRC, inventory, source-PDF/cache/secret-path exclusions and offline library checks passed. Original local library/source PDF unchanged; temporary library copy moved under tmp after containment verification.

No merge/push/external publication. No subagents. Parent owns independent integration re-review.

## Final integration hardening — round 2

Independent integration review blocked `bd5ae1b` with 2 Critical + 7 Important. All nine were reproduced RED before production fixes; detailed evidence and status matrix are appended in `final-hardening-report.md`.

1. Critical: finite/nonnegative structural geometry, actual separation ≥ structure + minimum, higher-crane ordering and schedule now gate preparation/public bundle/legacy generation; invalid 32.4/42.4 + structure12 fails atomically. Final boundary RED→GREEN removes the 1 mm minimum-comparison tolerance: 0.9995 m cannot pass a 1 m minimum. A canonical selected-scenario regression prevents unrelated rejected variants from blocking valid output.
2. Critical: both protected-zone and protected-route `PROTECTIVE_SCREEN` checks require the canonical screen clip and verified external screen project; physical draft/pending and production gate checked.
3. Plan/section source PDF text/metadata scanned before rasterization for new and legacy output; neutral forbidden source rejects before publication. Raster-only content requires visual review; no OCR.
4. XMP XML entities/text/attributes decoded and scanned; `27.06&#45;23` page metadata rejects atomically, including a matching attachment hash. Forbidden content is fatal even in drafts.
5. Explicit nine-column regulation CSV fixes real REG-007/008/009 alignment and retains every note; legal verification and software status are separate. Ambiguous rows fail closed; unresolved source statuses remain unresolved.
6. Exact issue date is printed and drives normative validity and title year. Conflicting supplied year blocks advanced status; no year-based validity extension.
7. Explicit persisted/editor approval role (or exact historical role position) supplies checker/approver independently; manager never fills both. Missing/duplicate role stays blank and blocks APPROVED/PRODUCTION.
8. Rigging sentinel/whitespace/bracket variants never become confirmed evidence. Physical pending card and production rejection checked.
9. Preparation measures exact external title/ID/page strings with the final contents formatter; 400-W ID fails before any output. Existing large internal/external pagination preserved.

Ruling: additive `ApprovalSlot.role` defaults empty; historical role/evidence is not fabricated. Joint minimum-clearance field is defaulted to the existing 1 m policy. Schema-4 load/release compatibility is retained. Registry normalization records existing explicit source flags only; no normative source was reverified.

Fresh focused after strict-minimum fix: `python -m unittest test_pprk_final_round2 test_pprk_final_hardening test_pprk_merge -v` → **48/48**, 228.090 s. Fresh full discovery after that fix → **457/457**, 488.381 s, no failures/errors/skips. Compileall and staged/unstaged diff checks exit 0. Eleven new round-2 tests cover public GUI, physical PDFs, atomic previous-file preservation and canonical selection.

Evidence: **50 pages / 50 PNGs / six inspected contact sheets**, targeted title/date, registry, section, schedule and rigging pages; minimum ink 0.008339601257019215. PDF **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`.

Round-2 portable: `tmp/pprk-r2-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,671,159 bytes**, SHA-256 `9b58c49a48c5e217ddc8116a0d6a87e3b023f1a1f076d0e7046c78de5367b605`. Rebuilt after strict minimum fix. Own-runtime smoke exit 0: **8364 files / six assets / 50-page GUI save**; CRC/inventory/offline library/exclusion checks passed. Byte match: all 44 Python modules plus README, packaged guide and registry. Temporary library input moved under `tmp/hardening-r2-final-library-input` after absolute containment checks; original source/library unchanged. Earlier round-2 ZIP superseded.

No subagents, merge, push or external publication. Parent owns independent integration re-review.

## Final integration hardening — round 3

Base `ca08ed0`; five Important findings reproduced before fixes. Report: round-3 section of `final-hardening-report.md`.

- Boundary accepts only absolute `1e-12` m floating representation noise; valid 30.8/(30.8+3), 31.3/34.3 and 61.1/64.1 GUI/legacy cases, physical 1.0 m note, genuine 0.9995 m negative retained.
- Source byte capture/validation and controlled plan/section snapshots remove render TOCTOU. Actual independent-thread replacement after staging is tested for all four bundle/legacy combinations, with clean source pixel identity. GUI source-fingerprint rollback preserves both PDFs and project/protocol/revision sidecars.
- Central semantic completeness rejects six specified sentinel families and normalized variants in all three rigging fields; physical pending cards and production blockers retained.
- Recursive metadata graph traversal includes nested Form XObjects, resources and cycles; decimal/hex entity text/attributes scanned. Safe cyclic metadata remains accepted.
- Unsafe XML has a fatal source classification at preparation and saveability in all five statuses, including a file replaced after preparation. Absent/unverified flags cannot hide an existing unsafe selected source.

Initial RED: 9 tests / 336.959 s, 62 assertion failures + three expected valid-boundary ValueErrors. Supplemental flag-order RED: six failing cases; GREEN 1/1 / 3.726 s. No production function patched for thread races. No persisted schema change or fabricated evidence.

First GREEN: 9/9 / 273.013 s; supplemental flags 1/1 / 3.726 s. Earlier focused 58/58 / 514.907 s passed. First full 467 / 778.616 s had one compatibility failure, `test_unverified_or_corrupt_source_is_pending_in_preliminary_copy`: fixed ordinary diagnostic priority without suppressing unsafe/forbidden issues; existing test unchanged. Compatibility + six unsafe flag cases GREEN 2/2 / 4.153 s. Final expanded focused: **74/74 / 527.939 s / OK**, exit 0 (`tmp/hardening-r3-focused-final.log`). Final full: **467/467 / 774.097 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r3-full-final.log`). All final suites/builds restarted after that last production fix. Ten new methods, 54 sentinel combinations, 20 prepared-release unsafe-XML status combinations, six flag cases, four actual-thread pixel-identity races plus two GUI rollback races. Separate real GUI positive proves original caller/source bytes and managed JSON paths remain correct for shared plan/section source.

Evidence: 50 pages / 50 fresh PNGs / six inspected contact sheets; literal physical map and canonical image identities retained, byte-identical PDF **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`.

Final portable: `tmp/pprk-r3-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,672,845 bytes**, SHA-256 `f07345408ff1b23617f6d83a09e00e85c891b81a296a6c69d68f6198cc8ddb3a`. Own runtime **8364 files / six assets / 50 GUI-save pages**, exit 0. CRC/inventory/offline library/exclusions and all 47 payload-file byte matches passed. Temporary library input moved under `tmp/hardening-r3-final-library-input` after containment checks. Earlier `tmp/pprk-r3` build superseded. No original library/source changes, schema changes, network or OCR dependency.

No subagents, merge, push or external publication. Parent owns independent integration re-review.

## Final integration hardening — round 4

Base `a9d36c4`; three Important reviewer repros addressed with eleven new test methods.

- Missing-source absence is captured explicitly by clearing only the copied rendering project's path. Four actual late-creation thread races prove no background image enters plan/section bundle/legacy output; original caller unchanged. GUI races retain all prior actual status reports and project/protocol/revision sidecars.
- XML raw-byte and decoded-Unicode guards reject DTD/ENTITY before any parser. BOM/byte order/declaration are decoded consistently, including UTF-16LE/BE and UTF-32 without BOM. Eleven configurations × page/Form parser-entry audit plus safe/numeric-entity controls; exact nested UTF-16LE/no-BOM DTD fatal across five statuses and both underlays.
- Bounded sentinel phrases work after labels and in grammatical forms without confusing ordinary identifiers. Physical missing cards stay unconfirmed; valid labeled evidence retains a confirmed real-GUI production card under isolated verified normative data.

Initial RED 9 / 260.578 s / 69 failures, no fixture errors; core GREEN 5/5 / 18.814 s; new-module GREEN 9/9 / 177.507 s. Self-review grammatical extension RED seven cases, then GREEN 4/4 / 20.852 s. Early final runs interrupted before completion and restarted after that last source fix; no function patched for races/parser audits, no shipped registry data changed.

Parent-approved namespace extension: RED nine cases / 19.862 s, then GREEN 4/4 / 42.617 s; start/start-ns scans used/unused namespaces, expanded names, attrs and text. Safe namespaces preserve exact physical metadata in public GUI output. Parser-entry audit updated/passed 1/1 / 0.077 s. Prior final runs/builds superseded; all restarted after source edit.

Final focused: **85/85 / 736.591 s / OK**, exit 0 (`tmp/hardening-r4-focused-namespace-final.log`). Full: **478/478 / 980.882 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r4-full-namespace-final.log`). Checks: **exit 0**, final frozen source, after namespace extension.
Evidence: **50 pages / 50 rendered PNGs / six inspected contact sheets**, no new clipping/overlap; literal page map and canonical image identities retained. `tmp/task11-evidence/full-pprk.pdf`, **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`; namespace-final regeneration is byte-identical to the inspected artifact, minimum ink `0.008339601257019215`.
Portable: `tmp/pprk-r4-ns/CranePlan_Portable_3.0.1_Windows.zip`, **174,675,022 bytes**, SHA-256 `0d8e36323b95df733f363a1c5804e2d8137bde73dd79357e799ff008fa61df39`. Own-runtime smoke **passed / exit 0**, **8364 files / six assets / 50 public-GUI pages**, CRC/inventory/offline-library/source/cache/secret exclusions passed (`tmp/hardening-r4-portable-namespace-smoke.log`). All **44 Python modules + README + guide + registry (47 files)** match. Temporary 19-file library input moved to `tmp/hardening-r4-ns-library-input` after containment checks; original library/source unchanged; earlier round-4 ZIPs superseded.

No schema change, fabricated evidence, merge, push, publication or subagents. Parent owns independent integration re-review.

## Final integration hardening — round 5

Base `d299d33`; two Important rigging semantics findings, nine new methods. Central predicate receives each explicit field role. Bounded Russian stems cover missing/unverified references in any grammatical form; scoped no-defect remarks are allowed only with remaining identifying evidence. Exact/essential `нет`, missing label assignments and targeted absent evidence still block. Generic approval names receive no rigging allowance; no production policy or shipped regulatory row was relaxed.

RED **7 / 73.578 s / 40 assertion failures + one expected positive-production gate error**, no fixture errors. Core plus prior sentinel compatibility GREEN **9/9 / 46.374 s**. Author quality-only list/label scope repro RED **1 / 5.994 s / 13 failures**. Physical/public tests cover reviewer strings as unconfirmed preliminary cards, all four advanced status gates with old output/sidecar preservation, and valid exact inspection evidence in confirmed production.

New module: **8/8 / 106.627 s / OK**, exit 0 before the final qualifier extension (`tmp/hardening-r5-green.log`); all nine final methods are included in the fresh focused/full suites. Focused: **94/94 / 858.666 s / OK**, exit 0 (`tmp/hardening-r5-focused-clause-final.log`). Full: **487/487 / 1109.583 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r5-full-clause-final.log`). Checks: **exit 0**, compileall plus staged/unstaged diff checks after the final clause-scope edit.
Evidence: **50 pages / 50 fresh PNGs / six inspected contact sheets**, no new clipping/overlap; literal page map and canonical image identities retained. `tmp/task11-evidence/full-pprk.pdf`, **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, byte-identical to the previous inspected artifact. Minimum ink `0.008339601257019215`.
Portable: `tmp/pprk-r5-clause-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,676,697 bytes**, SHA-256 `67c1ecfc9e66b50d8587b22f22d9200feeaaa616d27dc8b1c3a5225de7f61328`. Own runtime with `-B`: **8364 files / six assets / 50 public-GUI pages**, exit 0; CRC, archive/disk inventory, offline-library and source/cache/secret exclusions passed (`tmp/hardening-r5-portable-clause-final-smoke.log`). All **44 Python modules + README + guide + registry (47 files)** match current source bytes. Temporary 19-file library input moved to `tmp/hardening-r5-clause-final-library-input` after containment checks; original library/source unchanged; earlier round-5 builds superseded.

Report includes literal corpora, negation-scope self-review, status matrix and exact commands. No persisted schema change, fabricated evidence, subagents, merge, push or publication. Parent owns independent integration re-review.

Round-5 author qualifier self-review: `Пока нет`, `Паспорт: ещё нет`, `Схемы пока нет` and quality-only `Вообще нет замечаний` still counted filler words as identity. Added a ninth method before the next source edit: **1 test / 6.697 s / 24 assertion failures** (`tmp/hardening-r5-qualifier-red.log`), then **4/4 / 20.029 s / OK** including positive/mixed/list scopes (`tmp/hardening-r5-qualifier-green.log`). Bounded absence qualifiers now participate in targeted absence and cannot themselves identify a field; qualified no-defect subjects remain eligible with real evidence. The earlier focused/full runs were interrupted, not counted as final, and source/PDF/build verification restarted after this edit.

The first portable-smoke invocation omitted bytecode suppression: Python generated 462 `.pyc` files in the extracted folder, so the strict archive/disk inventory failed as intended. After retaining that folder/log and extracting the unchanged ZIP afresh, the own runtime with `-B` passed the unchanged 8364-file inventory and GUI smoke. That initial ZIP was subsequently superseded by the final qualifier source edit; the final build/smoke uses `-B` from its first invocation. No archive check was weakened.

Retained real public-GUI card evidence: `tmp/round5-card-evidence/{positive,missing,unverified}-card.png`, all page 42, generated after the qualifier edit and before the final clause-boundary change (`tmp/hardening-r5-cards-evidence.log`). The production card retains exact passport/inspection text, `ПОДТВЕРЖДЕНО` and no missing marker; both reviewer draft cards show `НЕ ПОДТВЕРЖДЕНО`/pending data. All three rendered cards inspected without clipping/overlap. Final 50-page evidence regeneration remains byte-identical to the inspected six contact sheets.

Clause-scope self-review found that a quality phrase could cross punctuation after an actual missing passport. RED **1 / 4.862 s / nine failures** (`tmp/hardening-r5-clause-red.log`) covers comma/colon/dash after `Паспорт №123 отсутствует`; comma-separated quality-only lists additionally gave RED **1 / 8.226 s / six failures** (`tmp/hardening-r5-comma-list-red.log`). Leading quality predicates now govern their subject directly without crossing punctuation; suffix `Дефектов — нет` and explicit quality noun lists remain supported. GREEN **4/4 / 24.587 s / OK**, including qualifier and positive scopes (`tmp/hardening-r5-clause-green.log`). Prior qualified focused/full runs and build were superseded; final focused/full, evidence and own-runtime build restarted after this last source edit.

## Final integration hardening — round 6

Base `417324f`; two Important findings, nine new methods. Role-specific positive identity replaces generic residual-text acceptance. Type requires concrete equipment/material or known sling family; sling requires an actual mark/number clause; named document evidence requires number/date/code. Shared clauses block target noun + absence despite intervening identifiers, preserving decimal/date punctuation and label binding. Semantic word-number splitting leaves displayed/project marks intact. Existing fields/flags are reevaluated fail closed; no persisted schema/migration or invented identity.

Initial RED **6 / 154.571 s / 63 failures**; extended role RED **1 / 6.034 s / 25 failures**; core GREEN **5/5 / 19.280 s**. Label/clause RED **1 / 3.445 s / five failures**, then joint compatibility GREEN **20/20 / 315.566 s**. Paraphrase/word-number RED **1 / 5.915 s / five failures**, interim core/grammar/overflow GREEN **9/9 / 47.309 s**. First final suites/artifacts began after that edit and were superseded by the subsequent shared-scope self-review. Old cross-role positive fixtures now use their proper fields; the overflow fixture has a real passport number, preserving its original layout assertion. No production/normative check weakened.

Public/physical matrix: five invalid cases pending in preliminary and atomically blocked in all four advanced statuses; three positive production controls retain exact decimal/serial and uppercase mark/document text. Verified normative fixture changes only an isolated data path, no shipped row or gate.

Focused: **103/103 / 1103.973 s / OK**, exit 0 (`tmp/hardening-r6-focused-quality-final.log`). Full: **496/496 / 1358.717 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r6-full-quality-final.log`). Checks: **exit 0**, final-source compileall and staged/unstaged diff checks.
Evidence: **50 pages / 50 fresh PNGs / six inspected contact sheets**, no new clipping/overlap; physical page map and canonical assets retained. `tmp/task11-evidence/full-pprk.pdf`, **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`; quality-final regeneration is byte-identical to the inspected artifact, minimum ink `0.008339601257019215` (`tmp/hardening-r6-evidence-quality-final.log`).
Portable: `tmp/pprk-r6-quality-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,679,047 bytes**, SHA-256 `c20a5d6121a2fb0fb444c2e945f41665c48e4a629941a9bdd07f4d9f4ef41c2d`. Own-runtime `-B` smoke passed, **8364 files / six assets / 50 public-GUI pages**, exit 0; CRC/inventory/offline-library/source/cache/secret exclusions passed (`tmp/hardening-r6-portable-quality-final-smoke.log`). All **44 production Python modules + README + guide + registry (47 files)** match current bytes. Temporary 19-file library input moved to `tmp/hardening-r6-quality-final-library-input` after containment checks. Original library/source unchanged; earlier round-6 ZIPs superseded.

Report includes literal corpora, exact commands, status matrix and paraphrase/negation self-review. No subagents, merge, push or publication; parent owns independent integration re-review.

Further author self-review reproduced implicit own-role absence (`Траверса нет`, `4СК-5,0нет`) and uppercase-code colon binding: RED **1 / 2.443 s / six failures** (`tmp/hardening-r6-single-scope-red.log`). Positive and negative evaluation now consume one case-preserving clause parse; identity itself can be the implicit subject of an absence predicate. GREEN **10/10 / 49.271 s** (`tmp/hardening-r6-single-scope-green.log`). Equipment-word self-review RED **1 / 6.415 s / two failures** (`Канатныйнет`, construction `Захватка №123`, `tmp/hardening-r6-equipment-word-red.log`) led to positive whole-term grammatical forms rather than arbitrary prefix suffixes; open negative stems remain unchanged. Interim GREEN **10/10 / 50.293 s** (`tmp/hardening-r6-core-final-green.log`). The public matrix adds implicit equipment absence and the positive uppercase production record includes a colon-separated quality remark. Earlier active final suites and ZIP were superseded; fresh focused/full/evidence/build/smoke run after these edits.


The scope-final focused run exposed **three positive compatibility subtest failures** in round-5 `test_quality_scope_does_not_hide_an_independent_missing_reference` (`Дефектов — нет` in all three roles); that run and the active full run were interrupted and are not final verification. Standalone RED **2 tests / 8.686 s / six failures** reproduces the old/new positive cases (`tmp/hardening-r6-quality-dash-red.log`). Quality-word guard RED **1 / 3.287 s / four failures** proves malformed quality words must not erase a missing-equipment/document predicate (`tmp/hardening-r6-quality-word-red.log`). Whole quality terms with proper boundaries are now annotated once, case-preservingly, before clause segmentation; their stored/rendered text remains unchanged. This keeps `Дефектов — нет` bound to its subject and retains unsafe missing predicates. Expanded compatibility GREEN **19/19 / 95.293 s**, including every prior positive/negative core case and overflow (`tmp/hardening-r6-quality-compat-green.log`). The public production matrix includes a third control with dash-quality remarks in all three roles. Scope-final ZIP/evidence/runs are superseded; final quality-final suites/render/build/smoke start after this last source change.

Quality-final retained card evidence: `tmp/round6-card-quality-evidence`, six public-GUI PDFs with full page-42 PNGs and `card-tables-contact.png` (`tmp/hardening-r6-card-quality-evidence.log`). All six tables inspected: three production cards (decimal/serial, uppercase protocol+colon remark, and dash-quality remarks in all three roles) retain exact identifying text and confirmation; absent passport, implicit absent equipment and quality-only sling drafts remain unconfirmed. No clipping/overlap; full PNGs retained. Generated after the last quality-annotation/whole-word source edit.

## Final integration hardening — round 7

Base `e4de994522c8dbbbbb687afbbd61ae5e14073bc6`; one Important finding, five new methods. Documentary identity now requires a heading-bound explicit number/code marker or valid `от`/`дата` calendar date. Defect/remark/page counts, mass/capacity, unlinked inspection dates and numeric text after unknown title/metric words cannot supply identity. Complete first-clause direct document-name + integer legacy format remains; no stored schema/migration or invented evidence. Controlled compound-title test fixtures now link their existing number explicitly with `№`.

Initial RED **5 / 395.373 s / 54 failures**; core GREEN **7/7 / 25.131 s**, compatibility GREEN **22/22 / 114.615 s**, complete new-module GREEN **5/5 / 185.504 s**. Registration-code author self-review RED **1 / 5.107 s / one failure**, then final core/older grammar/overflow GREEN **10/10 / 36.855 s**. Fresh final runs/build start after this last source edit.

Public/physical matrix: exact reviewer count strings plus decimal capacity yield pending drafts; all four advanced statuses preserve old PDF/project/protocol/revision outputs atomically. Four explicit-number/date/code positive controls reach confirmed production with the actual `4СК-5,0`/serial text. Loaded project values/flags remain byte-for-byte unchanged and are reevaluated fail closed. No shipped normative row/gate is patched.

Focused: **108/108 / 2104.564 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r7-focused-final.log`). Full: **501/501 / 2525.920 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r7-full-final.log`). Compileall and staged/unstaged diff checks **exit 0**, after the final source edit (`tmp/hardening-r7-compile-final.log`). No production source changed during final verification.

Evidence: **50 pages / 50 fresh PNGs / six inspected contact sheets**, no new clipping/overlap, canonical assets/page map retained. Main PDF **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, minimum ink `0.008339601257019215`, byte-identical to prior inspected geometry (`tmp/hardening-r7-evidence-final.log`). Seven retained public-GUI page-42 cards in `tmp/round7-card-evidence` and one inspected table contact sheet: three pending numeric-metric drafts and all four confirmed positive production controls; exact texts/no clipping. Auxiliary screenshot expectation corrected to the existing pending-card suppression behavior before rerun; no production change.

Portable: `tmp/pprk-r7-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,680,395 bytes**, SHA-256 `fed05571cf4e6436a9d319b770f24a29c872c43347f1d9ef9fa3a37d62548a36`. Own-runtime `-B` smoke **8364 files / six assets / 50 public-GUI pages**, exit 0; strict CRC/inventory/offline/source/cache/secret checks passed. All **47 payload source/README/guide/registry files** match current bytes. Temporary 19-file library input moved to `tmp/hardening-r7-final-library-input` after containment checks; original library/source unchanged.

Additional manual numeric paraphrase self-review passed **16 negative metrics / four explicit positive controls**, including pressure/volume/thickness/speed/height and metric-specific ID labels (`tmp/hardening-r7-numeric-self-review.log`); no source edit needed.

Report includes literal corpora, header/date/legacy grammar, self-review and status matrix. No subagents, merge, push or publication; parent owns independent integration re-review.

## Final integration hardening — round 8

Base `690628c4e87711ccb7beafc9e2683a091bc29f9f`; two Important findings, six new methods. Linked document dates now require complete format/calendar identity, retaining malformed raw candidate tails through clause splitting; signed date values cannot become label bindings. One terminal sentence period/comma is a delimiter. Explicit references accept natural alphabetic/hyphenated title words, adjectives and conjunctions before the marker, within the same clause; numeric components and punctuation stop the expanded path. The existing narrow known-title colon label remains supported. No persisted schema/migration or invented confirmation; all missing/sentinel/source/approval/normative gates remain.

TDD: original core RED **4 / 12.872 s / 28 failures**, physical/public RED **6 / 334.181 s / 45 failures**; expanded paraphrase RED **2 / 12.616 s / 46 failures**, final pre-edit core RED **4 / 17.778 s / 48 failures**. Interim core **6 / 28.973 s / two trailing-double-dot failures** led to retaining the full malformed match, then GREEN **6/6 / 29.166 s**. New-module interim GREEN **6/6 / 169.628 s**. Extended compatibility **26 / 134.108 s / one old positive label failure** (`Протокол испытаний: №42`); restored its existing narrow label path, then final core/new/legacy/quality GREEN **10/10 / 46.229 s**. All final suites/artifacts start after this last source edit.

Literal self-review corpus: **42 invalid dates / nine valid calendar/punctuation controls / 20 natural explicit titles / 13 clause-or-missing controls**. Public matrix: both reviewer date tails plus a negative prefix produce pending drafts; all four advanced statuses preserve old PDFs/project/protocol/revision atomically. Exact two natural titles and leap-valid date reach confirmed physical production. Verified normative fixture controls only an isolated data path, no shipped row/gate.

Focused before pause: **114/114 / 1454.425 s / OK**, exit 0 on the same frozen source (`tmp/hardening-r8-focused-final.log`). Fresh post-resume full: **507/507 / 2875.072 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r8-full-resumed-final.log`). Post-resume compileall and staged/unstaged diff checks **exit 0** (`tmp/hardening-r8-compile-resumed-final.log`).

User pause checkpoint: `99e961effb9f1a04d1146df295866d7915e607cf`. Resumed after explicit `ГО`; the interrupted pre-pause full log is excluded regardless of its terminal text. Completion is a new commit above the checkpoint, without rewriting it. Only report/ledger/checkpoint records change after resume; frozen production/test/README/guide payload remains unchanged, so the verified ZIP is retained. Fresh post-commit runtime/hash/payload confirmation is part of the final handoff.

Fresh evidence: **50 pages / 50 PNGs / six inspected contacts**, no new clipping/overlap, canonical assets/page map retained. Main PDF **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, min ink `0.008339601257019215`; six retained/inspected public-GUI cards at `tmp/round8-card-evidence`: three pending invalid-date drafts, two natural-title and one leap-date confirmed production controls, no clipping.

Portable `tmp/pprk-r8-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,681,617 bytes**, SHA-256 `13474b98e77561dcb2cf696772b80dd344262c210c297cad0ad03ad5e45d7a37`. Own-runtime `-B` **8364 files / six assets / 50 GUI pages**, exit 0; strict CRC/inventory/offline/source/cache/secret checks passed. All **47 source/README/guide/registry payload files** match current bytes. Temporary 19-file library input moved after containment checks to `tmp/hardening-r8-final-library-input`; originals unchanged. Additional real save/load self-review passed **six literal cases**, retaining raw text/flags/project bytes/caller while deriving correct confirmation (`tmp/hardening-r8-artifact-verification.log`).

Report includes the two resolutions, complete token/title grammar, interim failures, exact commands and status matrix. No subagents, merge, push or publication; parent owns independent integration re-review.

## Final integration hardening — round 9

Base `5635f19cfd0f43ec344f8be9d09ccec96d0b7833`; one Important finding, six new methods. Explicit identifiers now follow a conservative positive nominal-title grammar: domain noun case forms, technical adjective families/endings and compounds, `и`, and only initial `для`/`о` phrases with a noun head. Unknown words, finite/relational verbs, locatives/references, incomplete phrases and page/test/application marker borrowing fail closed. A bounded adjective/approved-intro prefix prevents owner jumps to another document name inside prose, retaining existing `По паспорту`/`Согласно протоколу` controls. No sentence blacklist, schema/migration or fabricated evidence; short `Акт №42` is the fallback.

Optional colon is explicitly authorized in round 9. The previous round-8 colon negative moves to positive; its dash counterpart remains negative. Label binding preserves actual colon/dash separators so this permission cannot borrow a number across a dash; existing sling/type/quality binding and complete date-token behavior remain covered.

TDD RED **6 / 447.729 s / 60 assertion failures**, core RED **4 / 19.279 s / 45 failures**, owner-hop self-review RED **1 / 6.683 s / 29 failures**, no fixture errors. Core GREEN **10/10 / 57.570 s**, full new-module GREEN **6/6 / 207.542 s**, extended old/new role/date/label/quality/overflow compatibility GREEN **30/30 / 167.426 s**, all OK/exit 0. Final suites and artifacts start after this frozen source; no further scope expansion.

Corpora: **29 relational negatives / 18 malformed-or-punctuation negatives / 16 nominal controls + 21 existing round-8 titles**. Real legacy load retains raw fields/checked flags/project bytes without confirmation. Public matrix: three pending drafts and atomic blocking of all four advanced statuses; four exact nominal/colon production cards confirmed. Only the isolated normative data path is controlled, no shipped row or production gate patched.

Final focused **120/120 / 2382.286 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r9-focused-final.log`). Final full **513/513 / 2665.248 s / OK**, exit 0, no failures/errors/skips (`tmp/hardening-r9-full-final.log`). Final compileall and staged/unstaged diff checks **exit 0** (`tmp/hardening-r9-compile-final.log`). No production edit after freeze; all final runs/artifacts correspond to that source and none were superseded.
Evidence: **50 fresh pages / 50 PNGs / six inspected contacts**, no new clipping/overlap, canonical assets/page map retained. Main PDF **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, minimum ink `0.008339601257019215`. Seven retained/inspected public-GUI cards in `tmp/round9-card-evidence`: three relational-reference drafts pending, four nominal/colon production controls confirmed with exact text, no clipping.

Portable `tmp/pprk-r9-final/CranePlan_Portable_3.0.1_Windows.zip`, **174,642,193 bytes**, SHA-256 `9c75d88d6d83c482e0df04bd84b29d4e4429616e0a00b92af7cf69e2a3a37688`. Own-runtime `-B` **8364 files / six assets / 50 GUI pages**, exit 0; strict CRC/inventory/offline/source/cache/secret checks passed. All **47 payload source/README/guide/registry files** match current bytes. Temporary 19-file library input moved after containment checks to `tmp/hardening-r9-final-library-input`; originals unchanged. Seven real legacy save/load controls retain raw fields/checked flags/JSON bytes/caller while deriving expected confirmation (`tmp/hardening-r9-artifact-verification.log`).

Report records the identity grammar, self-review, exact commands and status matrix. No spawn/merge/push/publication; parent owns independent integration re-review.

## Final integration hardening — round 10

Base `b9b42dfce20fd7a9af1daa1aee88a1823b748ed8`; one Important finding, six new methods. The same existing owner/prefix guard now runs before both number and date reference branches. A nested document inside relational prose, colon or dash cannot contribute its date to false confirmation. No title vocabulary, date-token/calendar rule, project schema/persistence, trust flag or other gate changes; supported direct/natural date headings and exact approved `По акту приёма-передачи оснастки №42` remain valid.

TDD core RED **4 methods / 12.490 s / 15 assertion failures**, no fixture errors. The public physical baseline also confirmed an invalid nested-date draft and incorrectly permitted advanced saves; it was deliberately interrupted after the expected failures, not counted as a completed suite. Full new-module GREEN **6/6 / 272.015 s / OK**, exit 0. Corpus: 12 nested-date negatives, 12 direct-date/natural-header positives, six boundaries and one approved number control. Two legacy-load regressions and seven manual round trips retain raw text/checked flags/JSON bytes/caller without false confirmation.

Public/physical matrix: three pending nested-date drafts, all four advanced statuses blocked atomically while retaining prior PDF/project/protocol/revision bytes; four direct-date/approved-number production cards confirmed with exact evidence. Seven cards retained and their table contact visually inspected. The isolated verified normative fixture controls only data location, with no production gate or shipped registry patched.

Fresh evidence: **50 pages / 50 PNGs / six inspected contacts**, no new clipping/overlap; PDF **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, minimum ink `0.008339601257019215`. Portable **174,642,468 bytes**, SHA-256 `328294d40940c5f97a2065a35450aa79a9a5a83fb223d20966b83c84c1999a7c`, at `tmp/pprk-r10-final/CranePlan_Portable_3.0.1_Windows.zip`. Builder/own-runtime exit 0: **8364 files / six assets / 50 GUI pages**, strict checks pass; **47 payload files** byte-match. Temporary 19-file library copy retained after containment checks at `tmp/hardening-r10-final-library-input`, originals unchanged.

Final targeted focused **23/23 / 884.477 s / OK**, exit 0 (`tmp/hardening-r10-focused-final.log`). Entirely fresh full **519/519 / 2332.027 s / OK**, exit 0 (`tmp/hardening-r10-full-final.log`), no failures/errors/skips. Compileall and unstaged/staged diff checks exit 0 (`tmp/hardening-r10-compile-final.log`). All final suites/artifacts use the frozen minimal source; none was interrupted or superseded. Self-review confirms exact reviewer/public/legacy paths, no false confirmation or persistence changes and no further scope expansion.

Report records the shared owner guard, exact reviewer reproductions, status matrix, TDD and commands. No spawn/merge/push/publication; parent owns independent integration re-review.

## Final integration hardening — round 11

Base `55e86fc82ebe398fb4461f6afb0f4e79c0154c07`; one Important root cause, six new methods. Clause segmentation now receives the same typed positive predicate selected for the concrete role. A colon/dash begins a new clause only after actual role identity; otherwise the complete owner context and original separator remain attached. The generic label/any-concrete-token heuristic is removed, including its non-label fallback. No phrase blacklist, title/date grammar expansion, schema/persistence, trust flag or other gate change.

TDD core RED **4 methods / 20.558 s / 41 assertion failures**, no fixture errors; physical baseline reproduces the exact falsely confirmed draft and incorrect advanced save, then is deliberately interrupted after expected failures and not counted as a completed suite. Core GREEN **6/6 / 25.025 s / OK**, exit 0, covers four new semantic/legacy methods plus two existing R6 label/absence-scope methods. Corpus: 33 numeric-owner document negatives, eight cross-role negatives and 19 positive role controls. Additional self-review: **120 arbitrary-number/header/separator combinations**, all rejected; two legacy regressions and seven extra real round trips retain raw text/checked flags/JSON bytes/caller without false confirmation.

Public/physical matrix: exact two reviewer negatives plus a page-count example produce three pending drafts; all four advanced statuses block atomically and retain old PDF/project/protocol/revision bytes. Four own-number/direct-date/approved-nominal production controls confirm with exact evidence. Seven cards/table contact visually inspected without false confirmation, missing-field contradiction or clipping. Only an isolated normative data path is controlled; no production gate or shipped registry is patched.

Fresh evidence **50 pages / 50 PNGs / six inspected contacts**, no new clipping/overlap; PDF **15,191,640 bytes**, SHA-256 `5033ae3735cb15a4aa9ab1ad529acec4dde96c7a6d4eb59b69093610d0444c99`, minimum ink `0.008339601257019215`. Portable **174,642,723 bytes**, SHA-256 `0f72aacc380f7cf0ba759f7c46c1f89b885ffa59abe79b7fa2b0c854253a0da6`, at `tmp/pprk-r11-final/CranePlan_Portable_3.0.1_Windows.zip`. Builder/own-runtime exit 0: **8364 files / six assets / 50 GUI pages**, strict checks pass; **47 payload files** byte-match. Temporary 19-file library copy retained after containment checks at `tmp/hardening-r11-final-library-input`, originals unchanged.

The coordinator explicitly stopped only the redundant focused R6–R11 process for acceleration after all six R11 methods passed; that incomplete focused run is not counted as a completed suite and is not restarted. The fresh full process was untouched and proceeds alone; targeted core **6/6** plus fresh full are the final verification basis.

Final verification: targeted core **6/6 / 25.025 s / OK**, exit 0; entirely fresh full **525/525 / 2494.732 s / OK**, exit 0 (`tmp/hardening-r11-full-final.log`), no failures/errors/skips. Full was never interrupted/restarted/superseded and ran alone after the explicit focused stop; all six R11 methods pass inside full. The partial focused is not a completed suite. Final compileall and unstaged/staged diff checks exit 0 (`tmp/hardening-r11-compile-final.log`). All final artifacts/checks use the frozen production source; no further behavior/grammar expansion.

Report records root cause, shared role predicate, class-based self-review, exact commands and status matrix. No spawn/merge/push/publication; parent owns independent integration re-review.
