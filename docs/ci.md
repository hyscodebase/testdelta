# Run the CLI in a pull-request workflow

The [native Action](action.md) handles the separate tool environment for you.
This CLI alternative shows the same boundary explicitly: project tests run with
their prepared Python, while TestDelta and Cosmic Ray live in a separate venv.

The complete example assumes tracked `src/pricing.py` and
`tests/test_pricing.py`, with pytest as their only test dependency. Change those
two policy paths and replace the project dependency installation with your own
locked setup. The external policy is written outside the checkout; it does not
require changing the PR's history or committing `.testdelta.toml` first.

```yaml
name: TestDelta CLI evidence
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
      - name: Install the reviewed TestDelta commit in a separate environment
        run: |
          python -I - <<'PY'
          import os
          import subprocess
          import sys
          from pathlib import Path

          tool = Path(os.environ["RUNNER_TEMP"]) / "testdelta-tool"
          subprocess.run([sys.executable, "-I", "-m", "venv", str(tool)], check=True)
          install_env = {key: value for key, value in os.environ.items()
                         if not key.startswith("PIP_")}
          install_env["PIP_CONFIG_FILE"] = os.devnull
          subprocess.run([
              str(tool / "bin/python"), "-I", "-m", "pip", "install",
              "git+https://github.com/hyscodebase/testdelta.git@55d64056c14834eab99cf49ca86c4786a14804bd",
          ], env=install_env, check=True)
          policy = Path(os.environ["RUNNER_TEMP"]) / "testdelta-policy.toml"
          policy.write_text(
              'source_modules = ["src/pricing.py"]\n'
              'test_paths = ["tests/test_pricing.py"]\n',
              encoding="utf-8",
          )
          PY
      - name: Compare test revisions
        env:
          TESTDELTA_BASE: ${{ github.event.pull_request.base.sha }}
          TESTDELTA_HEAD: ${{ github.event.pull_request.head.sha }}
        run: |
          "$RUNNER_TEMP/testdelta-tool/bin/python" -I -m testdelta compare \
            --repo "$GITHUB_WORKSPACE" \
            --base "$TESTDELTA_BASE" --head "$TESTDELTA_HEAD" \
            --config "$RUNNER_TEMP/testdelta-policy.toml" \
            --python "$RUNNER_TEMP/testdelta-project/bin/python" \
            --output "$RUNNER_TEMP/testdelta-report" \
            --budget-seconds 120 --max-mutants 10 --advisory
```

Both revisions must be available locally. Relative `--config` and `--output`
paths use the command's working directory, independently of `--repo`. TestDelta
records the selected policy bytes and hash for replay. Review the policy as part
of the workflow: an external policy does not exempt source, dependency, helper,
or configuration changes from the supported test-only boundary.

The pinned release commit installs CLI/tool version `0.1.0a4` and is the target of
[GitHub prerelease `v0.1.0-alpha.4`](https://github.com/hyscodebase/testdelta/releases/tag/v0.1.0-alpha.4).
The Action is published as
[TestDelta Test Quality on GitHub Marketplace](https://github.com/marketplace/actions/testdelta-test-quality).
Python package and GitHub tag prerelease syntax differ; this release remains alpha.
See the [release record](marketplace.md) for the publication date and exact commit.

TestDelta disables automatic third-party pytest plugin loading and restricts
inherited test environment variables. Verify a small representative fixture
before requiring the check. Unsupported or incomplete work exits nonzero.
`--advisory` changes only a complete `loss_observed` result from exit `1` to `0`;
it preserves exit `2` for unfinished work and exit `3` for invalid input.

An allowlisted job summary excludes raw logs, diffs, policy text, and absolute
runtime paths. JSON, HTML, and replay bundles stay under the requested output
directory. This workflow creates no PR comments, uploads no artifacts, and uses
only `contents: read`. Inspect captured output and source before sharing local
artifacts yourself.

Apply your ordinary test job's code-execution policy. Temporary workspaces are
not a sandbox, and tests retain the runner user's filesystem and network access.
Avoid elevated `pull_request_target` jobs that execute untrusted PR code. No
network-restricted execution profile is provided or verified in this alpha.
See [SECURITY.md](../SECURITY.md).
