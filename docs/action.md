# Native GitHub Action

The repository provides a composite Action for committed, test-only pytest changes.
It uses an isolated environment for TestDelta and the Python environment you prepare
for project tests. Supported runners are Ubuntu and macOS with Python 3.11–3.13 on
`PATH`; Windows is not supported by this Action.

Pin the Action to a reviewed full commit SHA. The placeholder below is intentional;
replace it before using the workflow. Fetch both revisions and install your own
project's locked test dependencies before the comparison.

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
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: '3.13'
      # Replace this with your project's locked test-environment setup.
      - run: python -m pip install -r requirements-test.txt
      - name: Compare test revisions
        id: testdelta
        uses: hyscodebase/testdelta@FULL_TESTDELTA_COMMIT_SHA
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          python: python
          budget-seconds: '120'
          max-mutants: '10'
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

An allowlisted summary without raw logs, diffs, config text, or absolute runtime paths is appended to the job summary. JSON, HTML, and replay bundles
stay in the requested local output directory. This Action creates no PR comments,
uploads no artifacts, and requests no repository write permission. Inspect captured
test output and source before publishing artifacts yourself.

Use the same code-execution trust policy as your ordinary project test job.
Temporary comparison workspaces are not a sandbox: tests retain the runner user's
OS privileges, can access its filesystem and network, and can execute imports and
fixtures. Environment filtering does not isolate secrets already present in files
or other host state. Avoid elevated `pull_request_target` jobs that execute
untrusted pull-request code. See [SECURITY.md](../SECURITY.md).

This alpha does not provide or verify network-blocked execution. Dependency preparation and test execution use the host runner; tests retain its network and filesystem access. A network-restricted container profile remains future work.
