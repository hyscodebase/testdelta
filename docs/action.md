# Native GitHub Action

The repository provides a composite Action for committed, test-only pytest changes.
It uses an isolated environment for TestDelta and the Python environment you prepare
for project tests. Supported runners are Ubuntu and macOS with Python 3.11–3.13 on
`PATH`; Windows is not supported by this Action.

The workflow below pins reviewed commit
[`dae67c6d6b44bc4d3ceda51b4188c6ad8801efee`](https://github.com/hyscodebase/testdelta/commit/dae67c6d6b44bc4d3ceda51b4188c6ad8801efee).
It assumes tracked files `src/pricing.py` and `tests/test_pricing.py` whose tests
need only pytest. Set those two policy paths to your project and prepare any
additional locked test dependencies in the project environment. The policy is
created outside the checkout, so an existing test-only PR needs no setup commit.

```yaml
name: TestDelta evidence
on:
  pull_request:
permissions:
  contents: read
jobs:
  compare:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1
        with:
          python-version: '3.13'
      - name: Prepare project test environment
        run: |
          python -I -m venv "$RUNNER_TEMP/testdelta-project"
          "$RUNNER_TEMP/testdelta-project/bin/python" -I -m pip install 'pytest==8.4.2'
      - name: Write trusted comparison policy
        run: |
          python -I - <<'PY'
          import os
          from pathlib import Path

          policy = Path(os.environ["RUNNER_TEMP"]) / "testdelta-policy.toml"
          policy.write_text(
              'source_modules = ["src/pricing.py"]\n'
              'test_paths = ["tests/test_pricing.py"]\n',
              encoding="utf-8",
          )
          PY
      - name: Compare test revisions
        id: testdelta
        uses: hyscodebase/testdelta@dae67c6d6b44bc4d3ceda51b4188c6ad8801efee
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          config: ${{ runner.temp }}/testdelta-policy.toml
          python: ${{ runner.temp }}/testdelta-project/bin/python
          output: ${{ runner.temp }}/testdelta-report
          budget-seconds: '120'
          max-mutants: '10'
          advisory: 'true'
```

Commit `.testdelta.toml` before the compared test change, or select an external
manifest with `config`. The external manifest is comparison policy: review and
control it as part of your workflow. The supported source, configuration, and
dependency scope still applies; an external manifest does not make source changes
supported. Relative `config` and `output` paths are resolved from the step's working
directory, independently of `repo`. The manifest bytes and hash are recorded for
replay, so replay does not require the original external file. See
[compatibility](compatibility.md) for the supported execution model.

| Input | Default | Meaning |
| --- | --- | --- |
| `base` | Required | Base revision, using the CLI's merge-base comparison semantics |
| `head` | `HEAD` | Candidate revision |
| `repo` | `.` | Checked-out repository directory |
| `config` | Empty | Optional external manifest path passed to `--config` |
| `output` | `.testdelta/report` | Local report and bundle directory |
| `budget-seconds` | `120` | Total comparison budget |
| `timeout-seconds` | `15` | Timeout for each pytest execution |
| `max-mutants` | `10` | Selected mutation limit, from 1 to 100 |
| `python` | `python` | Executable name on `PATH`, or path to your prepared project Python |
| `advisory` | `false` | Allow a complete `loss_observed` comparison to exit successfully |

For a project virtual environment, set `python: .venv/bin/python`. The Action resolves
this executable before preparing its own environment and preserves its virtual
environment symlink. It creates a separate venv under `RUNNER_TEMP`, installs
TestDelta from the selected Action checkout there, and runs the supervisor from
that venv. It never installs TestDelta or project dependencies into the selected
project interpreter. The project interpreter must already have pytest and its
required test dependencies. Automatic third-party pytest plugin loading is disabled;
verify a small fixture before making this check required.

The `0.1.0a4` bootstrap additionally isolates its initial Python imports and ignores
caller `PIP_*` options and pip configuration files when installing the tool. This
prevents project module names or `PIP_TARGET` from redirecting its own setup.
Prepare private-index project dependencies before invoking the Action; its tool
installation uses its own pip settings. The pinned example above currently selects
`0.1.0a3`; use the reviewed release commit for the bootstrap behavior you require.

The Action forwards inputs through environment variables and argument arrays.
It does not evaluate them as shell fragments. The supervisor records its own
environment separately from the selected test interpreter's provenance. Project
pytest subprocesses inherit the runner's existing narrow environment allowlist;
the Action does not add credentials or GitHub secrets to it.

The step exposes these outputs:

| Output | Meaning |
| --- | --- |
| `verdict` | `no_loss_observed`, `loss_observed`, `incomplete_with_witnesses`, `inconclusive`, `unsupported_change`, or adapter `error` |
| `complete` | Literal `true` or `false` |
| `report-path` | Absolute path to the fresh canonical `report.json`; empty on adapter errors |

Exit codes match the CLI: `0` for a complete comparison with no observed loss,
`1` for complete observed loss, `2` for incomplete or unsupported work, and `3`
for invalid input or execution errors. `advisory: 'true'` changes only complete
observed loss from `1` to `0`. Missing, stale, malformed, or inconsistent reports
cannot become clean outputs. Use `if: always()` for later inspection steps when
needed; a failed comparison remains a failed step unless your workflow explicitly
changes that policy.

An allowlisted summary without raw logs, diffs, config text, or absolute runtime
paths is appended to the job summary. JSON, HTML, and replay bundles
stay in the requested local output directory. This Action creates no PR comments,
uploads no artifacts, and requests no repository write permission. Inspect captured
test output and source before publishing artifacts yourself.

Use the same code-execution trust policy as your ordinary project test job.
Temporary comparison workspaces are not a sandbox: tests retain the runner user's
OS privileges, can access its filesystem and network, and can execute imports and
fixtures. Environment filtering does not isolate secrets already present in files
or other host state. Avoid elevated `pull_request_target` jobs that execute
untrusted pull-request code. See [SECURITY.md](../SECURITY.md).

This alpha does not provide or verify network-blocked execution. Dependency
preparation and test execution use the host runner; tests retain its network and
filesystem access. A network-restricted container profile remains future work.

GitHub Marketplace publication is tracked separately in
[Marketplace release status](marketplace.md). Using a commit-pinned Action does
not require a Marketplace listing.
