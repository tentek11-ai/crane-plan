# Final integration hardening — whole-branch review findings

Base: `dff1c0444ae43f5388f05dca9ecf16ddb4bc90f7`.

Fix all nine independently reproduced Important findings before integration. Use TDD: each finding needs a meaningful failing regression before production changes. Do not weaken stale, scenario, protocol, status, atomic-write or rollback guards.

1. **Joint-work vertical geometry:** section arrows/axes must use the verified `jib_level_m` values for each crane, not accepted crane height. The stated clearance equation must use the actual vertical separation and all required components; never print `10 = 2 + 1`. Cross-check section sheet against the joint-work schedule.
2. **Required external documents:** advanced/final release must fail closed when mandatory registered documents are absent/unverified. At minimum enforce the crane passport, foundation project and crane erection/dismantling project; enforce conditional tie/screen projects when those measures are used. Preliminary output may list pending documents explicitly.
3. **Protective-screen evidence:** carry the verified mitigation type through context/composer; when `PROTECTIVE_SCREEN` is what makes `DANGER_ZONE_PROTECTED` acceptable, require/include the protective-screen standard sheet and its external project evidence. No advanced status without both.
4. **Regulation registry:** preserve registry metadata, titles, status and validity dates in the release model/output. Advanced release must reject expired-at-issue-date and unverified regulations. Render the actual required regulation names/identifiers rather than an unresolved register placeholder.
5. **Forbidden reference leakage:** validate release inputs and scan generated PDF text/metadata before atomic replacement for the configured forbidden reference identifiers/source paths. A reference code such as `27.06-23` must not reach even a preliminary/final physical PDF. Preserve the old output on failure.
6. **Rigging completeness:** a production load card must not say both confirmed and `НЕ ЗАПОЛНЕНО`. Require auditable rigging type/branch count/sling identification/capacity evidence for advanced release, while preliminary output may show pending data. Use explicit typed/defaulted project data supported by the product; do not fabricate a confirmation solely in rendering.
7. **Selected variant identity:** all calculated sheets must show the selected canonical scenario number (`scenario_index + 1`) and protocol identity. Do not print a constant `ВАРИАНТ 1` or substitute sheet IDs for scenario numbers.
8. **Single release requisites:** every page/title/stamp/SOZR sheet in one release must use the release-card project code, organization, author and related requisites. Build an immutable effective rendering snapshot; do not leave old `ProjectInput` values on internal pages.
9. **Contents pagination without external PDFs:** contents/page-map finalization must always run, including an empty external registry. Large internal bundles must paginate or fail during preparation with the exact blocker; `require_saveable_release` must not approve a package that later crashes. Cover 38+ active loads and multiple contents continuation pages.

Verification:

- focused regressions for all nine findings, including physical PDF extraction and page geometry where applicable;
- full `unittest discover` with worktree-local TEMP/TMP;
- compileall and diff checks;
- regenerate the 49-page (or correctly changed count) evidence, render every page and inspect contact sheets;
- rebuild portable ZIP from final code/docs and smoke-test with its own runtime;
- update user documentation/report/ledger and record artifact SHA-256;
- one implementation commit; no merge/push/publish.
