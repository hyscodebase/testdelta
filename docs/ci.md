# Run TestDelta in a pull-request workflow

Use this only for the supported test-only changes in a repository whose test execution policy you already control. Commit `.testdelta.toml` before the compared change. A source, dependency, helper, or configuration change is currently unsupported and is not silently skipped as a successful comparison.

The example below uses official actions pinned to commit SHAs. Replace `FULL_TESTDELTA_COMMIT_SHA` with the reviewed TestDelta commit you intend to install. The placeholder is intentional: a published package or release tag is not assumed. Pin your project's dependencies using its own lockfile workflow as well.

```yaml
name: Test change evidence
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
      # Install this project's locked test dependencies here.
      - run: python -m pip install 'git+https://github.com/hyscodebase/testdelta.git@FULL_TESTDELTA_COMMIT_SHA'
      - name: Compare test revisions
        env:
          TESTDELTA_BASE: ${{ github.event.pull_request.base.sha }}
          TESTDELTA_HEAD: ${{ github.event.pull_request.head.sha }}
        run: >-
          testdelta compare --base "$TESTDELTA_BASE" --head "$TESTDELTA_HEAD"
          --output .testdelta/report --budget-seconds 120 --max-mutants 10
```

This snippet is a template for your repository, not a declaration that arbitrary projects are compatible. TestDelta disables automatic third-party pytest plugin loading and restricts inherited environment variables. Use a small fixture to verify the runner's behavior before making the job required.

The Markdown report is appended to the Actions job summary through `GITHUB_STEP_SUMMARY`. Local JSON, HTML, and bundle files remain under the requested output directory. Artifact upload is optional; inspect captured output and source before choosing to publish it. This integration does not post a PR comment.

For an initial advisory rollout, add `--advisory`. Only a complete `loss_observed` comparison changes from exit `1` to `0`; its report still records the evidence. Unsupported or incomplete comparisons remain nonzero. Do not hide those states with an unconditional success command.

No model API key or repository write token is needed. Avoid `pull_request_target` workflows that run untrusted PR code with elevated credentials. Temporary copies are not a sandbox; apply the same trust boundary as your ordinary test job. See [SECURITY.md](../SECURITY.md).
