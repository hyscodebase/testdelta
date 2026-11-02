# TestDelta

**Your tests still pass. Do they still catch the same bugs?**

[![CI](https://github.com/hyscodebase/testdelta/actions/workflows/ci.yml/badge.svg)](https://github.com/hyscodebase/testdelta/actions/workflows/ci.yml)

TestDelta is a GitHub Action and CLI for reviewing **test-only pytest changes**. It runs old and new tests against unchanged production code and identical selected mutations, then shows a concrete fault the old tests catch and the new tests miss.

Use it when refactoring tests, reviewing changed assertions, or checking tests edited by a coding agent. **No LLM, API key, or hosted account required.**

[Live demo](https://hyscodebase.github.io/testdelta/) · [Press kit](https://hyscodebase.github.io/testdelta/downloads/testdelta-press-kit.zip)

[한국어](README.ko.md) · [Action reference](docs/action.md) · [Quality status](docs/quality-status.md) · [Compatibility](docs/compatibility.md) · [Contributing](CONTRIBUTING.md)

**Alpha:** explicit Python source and test files; Ubuntu/macOS; Python 3.11–3.13. It reports evidence about a finite comparison, not whether a PR is correct or safe.

## Add it to a test-only PR

First commit `.testdelta.toml` **before** the test change, using your project's tracked file paths:

```toml
source_modules = ["src/pricing.py"]
test_paths = ["tests/test_pricing.py"]
```

Add this workflow before opening the test-only PR. This example installs pytest for a project with no other test dependencies; replace that step with your project's locked test-environment setup when needed.

```yaml
name: TestDelta
on:
  pull_request:
    paths: ["tests/**"]
permissions:
  contents: read
jobs:
  compare:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1
        with:
          python-version: "3.13"
      - run: python -m pip install "pytest==8.4.2"
      - name: Compare test revisions
        id: testdelta
        uses: hyscodebase/testdelta@2add31061b995a50a62fbf15b1a28942214f9fce
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          python: python
          max-mutants: "10"
          budget-seconds: "120"
```

The Action installs TestDelta into a separate tool environment and uses your prepared Python for project tests. It writes an allowlisted GitHub job summary and local HTML/JSON reports. It creates no PR comments or artifact uploads. [All inputs and outputs →](docs/action.md)

Already have a PR? Pass `config: path/to/reviewed-policy.toml` to use an **external manifest** without rewriting its history. Treat this file as trusted comparison policy: keep it in a reviewed workflow or obtain it from a trusted base revision, rather than accepting an unreviewed PR's choice of scope. Its exact bytes and hash are recorded for replay. An external manifest does not expand the supported change types.

Only selected test files may change. Production source, helpers, `conftest.py`, dependencies, configuration, and the in-repo manifest must stay unchanged. The workflow path filter does not override this rule. Automatic third-party pytest plugin loading is disabled; start with a small compatible suite.

Tests retain the runner user's filesystem and network access. Temporary workspaces are **not a sandbox**. Use the same trust policy as your ordinary test job and avoid privileged `pull_request_target` execution of untrusted PR code. [Security details →](SECURITY.md)

## Try the demo locally

With Git, Python 3.11–3.13, and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/hyscodebase/testdelta.git
cd testdelta
git checkout 2add31061b995a50a62fbf15b1a28942214f9fce
uv sync
uv run testdelta demo --scenario lost
```

Open `.testdelta/demo/report.html`. The synthetic pricing example changes exact assertions such as `total(1000, 3) == 3500` into `total(1000, 3) >= 0`. Both versions pass on the original code; selected faults expose what the weaker tests miss. The report includes the actual mutation, changed-test diff, repeated executions, and source/test hashes.

Two more executed scenarios show a behavior-preserving refactor and an invalid baseline:

```bash
uv run testdelta demo --scenario refactor --output .testdelta/demo-refactor
uv run testdelta demo --scenario inconclusive --output .testdelta/demo-inconclusive
```

`demo` exits `0` when its expected scenario is observed, including the intentionally inconclusive case. Read the report's verdict and completion flag. These synthetic examples are not real-project benchmarks.

## Compare an existing change locally

From the TestDelta checkout, point to your project's committed revisions:

```bash
uv run testdelta init --source src/pricing.py --tests tests/test_pricing.py \
  --output .testdelta/project.toml
uv run testdelta plan --repo ../your-project --base main --head HEAD \
  --config .testdelta/project.toml
uv run testdelta compare --repo ../your-project --base main --head HEAD \
  --config .testdelta/project.toml --python ../your-project/.venv/bin/python \
  --output .testdelta/review --budget-seconds 120 --max-mutants 10
```

Replace the source/test paths and prepare the project interpreter with pytest and its dependencies. `plan` reads committed Git snapshots without executing tests; `compare` executes them. The default comparison uses the revisions' merge-base; `--direct-base` selects the exact base commit. Uncommitted changes are excluded. External config paths are relative to your current directory, independently of `--repo`.

## Read the result

| Verdict | Meaning | Exit |
| --- | --- | ---: |
| `no_loss_observed` | Selected comparison completed with no confirmed lost detection | `0` |
| `loss_observed` | Selected comparison completed with confirmed lost detection | `1` |
| `incomplete_with_witnesses` | Some confirmed evidence exists, but work is incomplete | `2` |
| `inconclusive` / `unsupported_change` | A valid comparison could not be completed | `2` |
| Input or operational error | The operation could not be prepared or completed | `3` |

`advisory: "true"` in the Action, or CLI `--advisory`, allows only a **complete** observed loss to exit `0`. Incomplete work still fails.

For a confirmed loss, both test revisions first pass twice on original code. On the same mutation, the old tests fail an assertion while reaching the changed line and the new tests pass. This old/new outcome must repeat for three pairs, followed by passing original-code controls. Collection, fixture, runtime, import, and timeout errors do not count as kills. Skip/xfail executions remain incomplete.

[Cosmic Ray](https://github.com/sixty-north/cosmic-ray) supplies a bounded subset of mutation operators. The deterministic cap is not an exhaustive or representative sample of all bugs. Removing a guarantee can also be intentional: use a witness to review the change, not to infer intent.

## Keep and share evidence

Each run writes `report.html`, `report.md`, `report.json`, and a replay bundle. Reports show attempted pairs separately from valid evidence. Replay requires the recorded commits and matching recorded runtime; it is not a self-contained environment image.

```bash
uv run testdelta export .testdelta/review --output .testdelta/share.json
```

The export and automatic job summary omit raw logs, source/config text, and absolute runtime paths. Relative paths, revisions, and outcomes remain, so review them before sharing. Raw reports and bundles may contain source code or captured output. [Report format and replay →](docs/report-format.md)

## What has been checked

| Evidence | What it establishes |
| --- | --- |
| [194 local tests at the a3 snapshot](STUDY.MD) | That recorded implementation test run passed; see [CI for the commit you use](https://github.com/hyscodebase/testdelta/actions) |
| [50 frozen fixtures](corpus/README.md) | All 30 development and 20 validation expectations matched using hand-authored controls; not general accuracy or automatic mutation-quality measurement |
| [20 local runtime repetitions](docs/performance.md) | One synthetic pricing fixture, 10 mutations each: p95 **27.697 s** on one macOS host; setup excluded, host load uncontrolled |
| [Two pinned Boltons PR checks](docs/compatibility.md) | Both **inconclusive**, with execution errors retained; no qualified witness or clean result |

There is no measured claim about AI-generated test detection, external adoption, or arbitrary-project speed. Mixed source/test changes, Windows, plugin-dependent suites, arbitrary monorepos, and network-isolated execution are outside this alpha's supported scope. [Detailed status →](docs/quality-status.md)

## Related work and contributing

Same-mutation before/after comparison already exists: [testtruth](https://github.com/T4LEL/testtruth) covers JS/TS, and [Assertiva](https://github.com/Soturine/Assertiva) includes Python baseline/candidate evidence. [TestSeal](https://github.com/satwiksps/testseal) checks test-weakening signals statically. TestDelta focuses on an explicit pytest workflow and reviewable individual evidence; no algorithmic novelty or comparative accuracy is claimed.

Bug reproductions, small compatibility fixtures, and documentation improvements are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), the Korean [STUDY.MD](STUDY.MD), and the optional [coding-agent review workflow](docs/agent-workflow.md).

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run python -m build --wheel
```

MIT © 2026 Hong Yuseok. [License](LICENSE).
