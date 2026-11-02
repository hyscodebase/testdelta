# Solo development roadmap

TestDelta is a small, early-alpha project maintained by one person with implementation assistance. The roadmap is a sequence of work, not a promise that a feature is already available or will ship on a particular date. Implementation, validation, documentation, and release preparation are owned by the project; users are not required to recruit interviewees, assemble a team, or perform setup work on the maintainer's behalf.

## Initial alpha

The first release focuses on one question: for unchanged Python source and explicit pytest test paths, did a test change stop detecting any of the same selected mutations?

| Work | Acceptance evidence |
|---|---|
| Explicit configuration and comparison planning | Relevant changes are classified before execution; unsupported helper/configuration changes are reported |
| Cosmic Ray mutation provider | Stable mutation identities and source fingerprints; valid generated Python; a bounded operator subset |
| Paired pytest execution | Both unmutated baselines pass; old/new test revisions see identical mutations |
| Result classification | Timeout, collection failure, incomplete work, and incompatible runs stay distinct from a clean comparison |
| Evidence and replay | Reports retain commands and individual mutation outcomes; selected evidence can be rerun |
| Packaging and CI | Source tests, lint, wheel build, and installed-wheel demo checked on the declared matrix |

Python 3.11–3.13 on Linux and macOS are the CI targets. The status of each platform must be read from actual CI results. Windows, external services, browser tests, arbitrary monorepos, and source-plus-test migrations are outside the initial scope.

Version `0.1.0a3` adds external configuration, native GitHub Action integration with separated project Python, actual test/mutant diffs, run timestamps, a sanitized share export, and a frozen 30/20 conformance corpus. See [quality status](quality-status.md) for observed results and deferred original-plan targets.

## Next iterations

1. **Make the current path dependable.** Fix installation failures, false classifications, stale fingerprints, timeout cleanup, and report ambiguities before adding runners.
2. **Make evidence easy to review.** Improve the smallest useful report, mutation diffs, replay instructions, and explanations of unsupported comparisons.
3. **Reduce wasted work.** Measure setup and execution time on clearly described fixtures; add optimizations only when they preserve the comparison's identity and completeness.
4. **Improve integration.** Refine CI artifact usage and compatibility with existing mutation tooling. A report-only or upstream integration may be better than a separate engine.

## Why this is a narrow project

The central comparison is established work. [testtruth](https://github.com/T4LEL/testtruth) compares old/new tests using the same mutations in JS/TS. [Assertiva](https://github.com/Soturine/Assertiva) includes Python and baseline/candidate mutation evidence. [Cosmic Ray](https://github.com/sixty-north/cosmic-ray) supplies Python mutation operators. TestDelta's hypothesis is that a small pytest-specific review workflow can be useful; this is not a novelty or superiority claim.

Optional maintainer feedback is welcome when a report helps or fails to help a real review. It does not block implementation. Useful feedback includes a minimal test-only diff, a normal refactor that should remain acceptable, or a result the report cannot explain. Do not send private source or secrets.

## Release conditions

- Commands in the README have been run from the relevant checkout or installed wheel.
- The supported CI matrix has completed, with any limitations recorded.
- Synthetic examples are labeled; unsupported and partial results are visible.
- No generated report is presented as proof that all bugs or all test weaknesses were found.
- The release notes state what changed and what remains unsupported.

Future scope will follow actual defects and repeated use. Stars, downloads, and repeat use are different signals; none of them substitutes for execution evidence.
