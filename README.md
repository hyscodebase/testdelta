# TestDelta

**Your tests still pass. Do they still catch the same bugs?**

[![CI](https://github.com/hyscodebase/testdelta/actions/workflows/ci.yml/badge.svg)](https://github.com/hyscodebase/testdelta/actions/workflows/ci.yml)

**Early alpha — `0.1.0a2`.** TestDelta compares two test revisions against unchanged production code and the same selected mutations. It records a concrete example when the old tests catch a deliberate fault and the new tests miss it.

[한국어](README.ko.md) · [Real-repository compatibility](docs/compatibility.md) · [Development roadmap](docs/solo-roadmap.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

This is a narrow Python/pytest tool, not a claim that a test change is wrong. Removing an assertion can be intentional. A complete run with no observed loss only describes the finite mutations and tests it executed.

## Try the executed demo

Use Python 3.11–3.13, Git, and [uv](https://docs.astral.sh/uv/). Install from this repository; a PyPI release is not assumed.

```bash
git clone https://github.com/hyscodebase/testdelta.git
cd testdelta
uv sync --extra dev
uv run testdelta demo
```

The demo creates a temporary two-commit repository with original synthetic fixtures. Both test revisions pass on the unmodified pricing function. The second revision weakens exact assertions. TestDelta executes the comparison using Cosmic Ray mutations and actual pytest subprocesses. No model, API key, or LLM judge is involved.

Open `.testdelta/demo/report.html` to read the result. `report.json` contains the detailed evidence. The synthetic Git repository is retained under the output directory; its exact path is recorded in `demo_repository` so it can be used with `replay --repo`. The bundle alone still does not contain a complete repository.

The HTML report shows the comparison verdict, attempted pairs, confirmed findings, execution issues, and source/test provenance in separate sections. An attempted pair is not necessarily valid evidence. Old/new test-file SHA-256 values accompany the source fingerprints.

Three executed synthetic scenarios are available:

```bash
uv run testdelta demo --scenario lost --output .testdelta/demo-lost
uv run testdelta demo --scenario refactor --output .testdelta/demo-refactor
uv run testdelta demo --scenario inconclusive --output .testdelta/demo-inconclusive
```

They illustrate lost detection, a harmless test refactor, and an invalid baseline. `demo` exits `0` when the expected scenario verdict is observed, including the intentionally inconclusive example. Read the report's verdict and completion flag; this demo exit convention is different from `compare`. These examples are not real-project benchmarks.

## Compare a test change

The initial scope requires explicit tracked Python source files and pytest test files. Commit the manifest **before** the test change you want to compare. The following commands run from the TestDelta checkout and point to an example sibling repository:

```bash
uv run testdelta init --repo ../your-project \
  --source src/pricing.py --tests tests/test_pricing.py
```

The generated `.testdelta.toml` is deliberately small:

```toml
source_modules = ["src/pricing.py"]
test_paths = ["tests/test_pricing.py"]
```

Commit that manifest in your project, then commit the test change. With the base branch set to the earlier revision:

```bash
uv run testdelta plan --repo ../your-project --base main --head HEAD
uv run testdelta compare --repo ../your-project --base main --head HEAD \
  --output .testdelta/review --budget-seconds 120 --max-mutants 10
```

`plan` reads committed Git snapshots without running project tests. The default base is the merge-base of the supplied revisions, as in a pull-request comparison. `--direct-base` compares the exact base commit. Uncommitted files are excluded.

`compare` executes project tests. The interpreter running TestDelta must have the project's required dependencies. It does not install project dependencies automatically. The first runner disables automatic third-party pytest plugin loading and restricts inherited environment variables; projects that depend on those features may be incompatible with this alpha.

Changes outside the selected test paths—including production source, the manifest, helpers, `conftest.py`, dependency files, and other configuration—are unsupported. A no-change comparison is unsupported too. This conservative boundary prevents a source or environment change from being mistaken for a difference caused only by tests.

## What counts as evidence

For each mutation, the comparison has four cells:

| | Original production code | Identical mutated production code |
|---|---|---|
| Old tests | Must pass | An assertion failure must reach the mutated line |
| New tests | Must pass | Passing means this selected fault survived |

The original-code baselines run twice per test revision. A potential lost detection is repeated until there are three old/new pairs, then checked against final original-code controls. Repetition reduces some transient noise; it does not prove that a test is never flaky.

An import, collection, fixture, runtime, or timeout error does not count as a successful kill. Source fingerprints are checked before and after each run, and the pytest plugin records imported source origins and reached lines. Each execution uses a fresh bytecode-cache namespace so stale `.pyc` files cannot stand in for the mutated source. In the initial runner, any skip or xfail makes that execution incomplete.

Mutation operators come from the pinned Cosmic Ray library. TestDelta uses a bounded subset; it does not implement a new general mutation engine, enumerate every possible bug, or filter all equivalent mutations.

## Results and exit codes

| Verdict | Meaning | Exit code |
|---|---|---:|
| `no_loss_observed` | Selected comparison completed; no confirmed lost detection found | `0` |
| `loss_observed` | Selected comparison completed with confirmed lost detection | `1` |
| `incomplete_with_witnesses` | Some evidence exists, but the selected comparison is incomplete | `2` |
| `inconclusive` / `unsupported_change` | Valid comparison could not be completed | `2` |
| Input or operational error | The command could not prepare or complete its operation | `3` |

`--advisory` changes a complete `loss_observed` exit from `1` to `0`; the report still says loss was observed. It does **not** turn an incomplete or unsupported comparison into success. `demo` has its own smoke-test exit convention described above.

`--max-mutants` bounds the selected mutation set; completing that set is not exhaustive analysis. `--budget-seconds` bounds comparison work, including the mutation-provider subprocess, and `--timeout-seconds` bounds individual test runs. A budget exhausted before the selected work and controls complete does not produce a clean result.

## Reports and replay

An output directory contains:

- `report.html`, `report.md`, and `report.json`: human-readable results and detailed execution evidence.
- `bundle.json` and `bundle.sha256`: recorded revisions, environment, and selected mutations for replay.

For a comparison on a retained repository, take a witness ID from the report:

```bash
uv run testdelta replay .testdelta/review --witness WITNESS_ID \
  --repo ../your-project --output .testdelta/replay
```

Replay requires the original committed revisions and matching recorded supervisor environment and target Python/pytest runtime. These records are not a full dependency or operating-system image fingerprint. The bundle does not include a complete repository or its dependencies. Checksums detect accidental changes; they are not signatures proving who created a bundle. Replaying untrusted code is unsafe—see [SECURITY.md](SECURITY.md).

Reports stay local unless you share them. When `GITHUB_STEP_SUMMARY` is present, the Markdown report is also appended to the GitHub Actions job summary. Review source and captured output before uploading an artifact. There is no hosted dashboard or automatic PR comment publisher in this alpha. See the [CI integration example](docs/ci.md).

## Real-repository checks

Two pinned Boltons test-only changes have been executed locally. Both remain **inconclusive**: one attempted ten mutation pairs with seven runtime-error pairs, and the other attempted three with one collection/runtime-error pair. Neither produced a qualified lost-detection witness or a clean result. The second case also exposed tracing overhead; caching source-origin lookups brought its baseline runs within the existing timeout without relaxing the evidence rules.

These are bounded compatibility checks, not evidence of maintainer adoption, upstream bugs, or general accuracy. See [the exact revisions, setup, results, and reproduction commands](docs/compatibility.md).

## Scope and alternatives

The same-mutation before/after idea already exists. [testtruth](https://github.com/T4LEL/testtruth) provides this workflow for JS/TS. [Assertiva](https://github.com/Soturine/Assertiva) includes Python and baseline/candidate mutation evidence. [TestSeal](https://github.com/satwiksps/testseal) checks test-weakening signals statically. [Cosmic Ray](https://github.com/sixty-north/cosmic-ray) supplies this project's mutation operators.

TestDelta explores a small pytest-specific workflow with explicit scope and reviewable individual evidence. It does not claim algorithmic novelty, broader support, or better accuracy than those projects. If an existing tool solves your problem, use it; compatibility and upstream contributions remain valid directions for TestDelta.

The first CI matrix targets Ubuntu on Python 3.11, 3.12, and 3.13, plus macOS on Python 3.13. Check the [workflow results](https://github.com/hyscodebase/testdelta/actions/workflows/ci.yml) for the commit you use; the matrix declaration alone is not validation. Windows, source-plus-test migrations, symlink/submodule snapshots, external services, and arbitrary monorepos are outside the initial scope. Snapshots currently have a 5 MB per-file and 25 MB total size limit.

Temporary workspaces are **not a sandbox**. Only run repositories whose tests you trust to execute with your account's permissions.

## Develop

```bash
uv run pytest
uv run ruff check .
uv run python -m build --wheel
```

The Korean [STUDY.MD](STUDY.MD) explains the implementation and distinguishes performed checks from suggested exercises. The optional [agent workflow](docs/agent-workflow.md) and [review skill](skills/testdelta-review/SKILL.md) describe how a coding agent can use the evidence and verify an authorized test repair. Their structural validation is not a measured claim about model performance. Small fixtures, clear bug reports, and documentation improvements are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

MIT © 2026 Hong Yuseok. See [LICENSE](LICENSE).
