# Real-repository compatibility checks

Observed on 2026-11-02 with TestDelta `0.1.0a2`, Python `3.13.5`, pytest `9.2.0`, and Cosmic Ray `8.7.0` on macOS ARM64.

**Both comparisons below are inconclusive.** They exercised real public test changes, but neither established a qualified lost-detection witness or a clean comparison. These are bounded local compatibility checks, not evidence of maintainer adoption, upstream bugs, or general accuracy. No maintainer was contacted and no upstream change was submitted.

## Scope and provenance

Each upstream change modifies exactly one selected test file. Production source, dependencies, helpers, and configuration are unchanged between the selected revisions. The upstream repositories did not contain a TestDelta manifest. The validation script therefore created local derived commits with the same manifest on both sides while preserving upstream source/test bytes. Derived commits are validation setup, not upstream contributions.

| Case | Upstream intent and state | Source / tests |
|---|---|---|
| [Boltons #564](https://github.com/mahmoud/boltons/pull/564) | Add priority-queue coverage; closed, unmerged proposal | `boltons/queueutils.py` / `tests/test_queueutils.py` |
| [Boltons #408](https://github.com/mahmoud/boltons/pull/408) | Remove duplicate module-import test invocation; merged cleanup | `boltons/listutils.py` / `tests/test_listutils.py` |

The full source and tests remain subject to the upstream [BSD-3-Clause license](https://github.com/mahmoud/boltons/blob/7ea6c0bade3e1057593afd67bb6bc6bd7097f098/LICENSE). This document links to upstream material; it does not publish the captured source bundles.

### Fixed upstream revisions

| Case | Base / merge-base | Head |
|---|---|---|
| #564 | `4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d` | `7ea6c0bade3e1057593afd67bb6bc6bd7097f098` |
| #408 | `3970a80f63807392e512340c25dc2db473bcba70` | `b14382f0710333d11fb56b73e2218771e537c1e9` |

For #408, the PR API's base was `979fa9b613fa8c0a455ae16ea6f2ec91c11ecafe`, but it had diverged from the PR branch. The selected base above is the actual merge-base, preserving the intended test-only diff.

### Derived revisions used for these observations

| Case | Derived base | Derived head |
|---|---|---|
| #564 | `a9441b319987f7a9dc2f205622d7ef5f7d50072e` | `7b60cfa519c6f7d29088334ad6e5d7905148e504` |
| #408 | `51ff340e61605fe3f4e381a9efa1115328a8719e` | `6f3de0099e5e14c5ee975c762217705b0b89d0e4` |

These hashes identify local setup commits. They are not expected to resolve as upstream GitHub commits. The script records the mapping and verifies that the pinned upstream diff contains only the intended test path.

## Observed a2 results

| Case | Original baselines / final controls | Mutation pairs attempted | Outcomes | Verdict |
|---|---|---:|---|---|
| #564 | 4 passed / 2 passed | 10 of 10 planned | 7 inconclusive pairs with runtime errors on both sides; 3 `survived_both` | `inconclusive`, `complete: false` |
| #408 | 4 passed / 2 passed | 3 of 3 planned | 2 `survived_both`; 1 pair with old collection error and new runtime error | `inconclusive`, `complete: false` |

Attempting every planned pair is not the same as completing a valid comparison. Runtime and collection errors are not counted as successful mutation kills. Both cases have zero qualified lost-detection witnesses, which does **not** mean the tests are equivalent or that the proposed changes are safe.

The observed durations were 11.841 seconds for #564 and 8.339 seconds for #408. They describe these limited runs and environments only. Ten or three selected mutations do not represent all behaviors the changes were intended to cover.

Reviewed machine-readable summaries are available for [#564](../evidence/compatibility/boltons-pr564.json)
and [#408](../evidence/compatibility/boltons-pr408.json). They retain revision and
source/test fingerprints, mutation identities, outcomes, and execution durations;
raw stdout, runtime executable paths, and source bundles are excluded.

## What the listutils case changed in TestDelta

Before the tracing optimization, #408 stopped during its first baseline at the existing 15-second test-run limit. An untraced head test run was observed at approximately 0.179 seconds. This prompted investigation of TestDelta's tracing cost rather than assuming the repository required a larger timeout.

The runner now caches source-origin resolution and avoids repeating path checks on every traced target line. With the same 15-second bound, the observed original-code baseline durations became:

| Test revision | First run | Second run |
|---|---:|---:|
| Old | 0.821 s | 0.808 s |
| New | 0.595 s | 0.594 s |

These figures compare a particular before/after investigation, not a general speedup benchmark. Tracing still has overhead. The remaining error pair correctly leaves the final result inconclusive.

The runner also received import-origin handling fixes for package and module layouts, including avoiding misleading standard-library basename collisions while retaining checks for imports from outside the measured snapshot. Those behaviors are covered by focused runner regressions; the two Boltons cases alone do not validate every layout.

## Reproduce the checks

These are commands to run yourself, not a guarantee of identical timings or outcomes on another environment. They clone public code and execute its tests locally. Read the [execution boundary](../SECURITY.md) first. No model API key is needed.

From a TestDelta checkout with development dependencies installed, use two **new, empty** work directories:

```bash
uv run python scripts/validate_boltons.py --case pr564 \
  --workdir .testdelta/compatibility-reproduction/pr564 \
  --max-mutants 10 --budget-seconds 180

uv run python scripts/validate_boltons.py --case pr408 \
  --workdir .testdelta/compatibility-reproduction/pr408 \
  --max-mutants 3 --budget-seconds 180
```

The script refuses to overwrite an existing repository directory. It fetches the pinned PR, verifies the changed-file scope, preserves source/test bytes, adds identical manifests, and records original/derived revisions in `summary.json`. The complete local report and replay bundle are under each work directory's `report/` folder.

The script's exit `0` means it produced the observation; it does not imply a clean TestDelta verdict. Read `verdict`, `complete`, `reason`, individual outcomes, and baseline/control statuses. Preserve incomplete results instead of changing the threshold to obtain green output.

Raw reports may contain local paths, stdout, and source code. They remain local by default and are not copied into the public repository as source bundles. Use reviewed, sanitized summaries for publication. The underlying command and fixed upstream revisions remain available so readers can produce their own evidence.
