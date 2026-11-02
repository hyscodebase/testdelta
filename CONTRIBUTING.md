# Contributing to TestDelta

TestDelta is an early alpha. Small, reproducible examples are more useful than broad feature requests. The initial scope is Python/pytest test changes against unchanged production code.

## Set up a checkout

Use Python 3.11–3.13 and Git. With [uv](https://docs.astral.sh/uv/) installed:

```bash
git clone https://github.com/hyscodebase/testdelta.git
cd testdelta
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run testdelta demo
```

The checked-in CI workflow targets Ubuntu on Python 3.11, 3.12, and 3.13, plus macOS on Python 3.13. A configured matrix is not itself proof of compatibility; inspect the actual workflow results for the commit you use. Windows is outside the first supported scope.

## A useful contribution

- A minimal fixture where the old tests catch a mutation and the new tests miss it.
- A normal test refactor that should not be called a regression.
- An environment, collection, timeout, or incomplete-run case that must stay inconclusive.
- A clearer report, error message, or verified setup instruction.

Include a test for behavior that could break: status classification, path boundaries, unchanged source checks, mutant identity, or a reproducible false finding. Documentation-only fixes do not require artificial tests. Do not weaken assertions to make CI pass or count collection/import errors as successful mutation detection.

Keep examples small and free of credentials or private code. For third-party fixtures, include their source, license, and any required attribution. A fabricated fixture is welcome when clearly labeled synthetic; it is not evidence about the real-world accuracy of the tool.

## Pull requests

Describe the concrete problem, the resulting behavior, and what you verified. Run the relevant tests and `uv run ruff check .`. For packaging changes, also run `uv run python -m build --wheel` and install the wheel in a fresh virtual environment.

For changes to result semantics, explain how partial runs, unknown outcomes, flaky tests, and unsupported comparisons behave. A report must preserve those states rather than turn them into a clean result.

Open a discussion issue before a large new runner, language, or hosted service. We prefer fixing the existing pytest flow before expanding support. Comparisons with other tools should describe their current capabilities fairly and link to the source you checked.

## Communication and credit

Be constructive, discuss behavior rather than people, and credit contributors and upstream work. The maintainer aims to acknowledge reproducible issues within two working days, but this is a personal project without a service-level guarantee.

Contributions are accepted under the repository's MIT license. You must have the right to contribute the code or material. For security-sensitive reports, follow [SECURITY.md](SECURITY.md) instead of posting sensitive details in an ordinary issue.
