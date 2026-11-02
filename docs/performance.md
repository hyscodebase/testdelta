# Finite runtime acceptance measurement

This measurement covers one synthetic four-test pricing fixture on one local
macOS host. It does not establish runtime for other repositories or machines.
The complete record is
[synthetic-pricing-20-2026-11-02.json](../evidence/performance/synthetic-pricing-20-2026-11-02.json).

The fixed target was met on 2026-11-02: all 20 attempts were eligible, each
completed the same 10 mutants, and nearest-rank p95 was **27.697 seconds** against
the 120-second target. There were no errors, exclusions, or replacement runs.

| Observed metric | Result |
| --- | --- |
| Repetitions / mutants completed | 20 / 200 |
| Wall-time minimum / maximum | 25.340 / 27.963 seconds |
| Slowest original-source baseline suite | 0.446 seconds |
| Fixture setup and wheel verification | 0.136 seconds |

The installed environment was TestDelta 0.1.0a3, Python 3.13.5, pytest 9.2.0,
and Cosmic Ray 8.7.0 on macOS arm64. All 10 witnesses in each repetition passed
the engine's repeated-pair and final-control requirements. The installed engine
hashes remained unchanged throughout execution.

The fixture preserves the original `testdelta demo` pricing source and strong
tests, then changes only its four equality assertions to `>= 0`. The record
includes source/test/config hashes and the two local Git commit hashes. The
fixture bytes are defined in the harness. No upstream repository is involved.

The protocol fixes 20 sequential repetitions, 10 selected Cosmic Ray mutants,
a 120-second comparison budget, and a 15-second per-pytest timeout. There is no
warm-up exclusion, retry, replacement run, or threshold tuning. Each measured
interval starts before reading the Git plan and ends after the comparison
returns. It includes target-runtime observation, all four original-source
baseline suites, actual Cosmic Ray mutation generation, required repeated
old/new executions, and final original-source controls.

Wheel building, dependency installation, Git fixture creation, and JSON evidence
serialization are outside the measured comparison interval. Supervisor process
startup and module imports also precede the timed calls; target pytest process
startup is included in each suite execution. Fixture preparation and wheel
verification have a separate `setup_seconds` measurement. Installed Python file hashes must
match the supplied wheel before the run starts, and the script checks that the
installed implementation stays unchanged after every repetition.

A repetition is eligible only if all four original-source baselines pass and
each takes at most two seconds, exactly 10 mutants are selected and completed,
and the comparison completes with observed loss. A provider returning fewer
than 10 mutants is a missed scope requirement. Every exception, incomplete
comparison, or eligibility exclusion stays in the JSON record.

The nearest-rank p95 is sorted duration number `ceil(0.95 × n)`, counting from
one. For 20 repetitions this is the 19th duration. The target is met only when
all 20 attempts are eligible and their p95 is at most 120 seconds. The record
also reports p95 across all attempts and across eligible attempts, with the
complete list of exclusions; a smaller surviving subset cannot pass acceptance.

The public record retains every attempt, allowlisted comparison outcomes,
source and mutation hashes, per-suite durations, controls, exclusions, and
version numbers. Raw reports, stdout/stderr, source/config text, diffs, and
absolute paths stay in ignored local evidence under `.testdelta/performance/`.
Other local test and corpus work ran
concurrently, so host load was uncontrolled; load averages are recorded before
and after each comparison. CPU affinity, thermal state, and filesystem caches
were not controlled.

To reproduce the fixed protocol, build and install a wheel into a separate
environment, then run the harness with that interpreter and a new output file:

```bash
python -m build --wheel
python -m venv .testdelta/runtime-python
.testdelta/runtime-python/bin/python -m pip install dist/testdelta-0.1.0a3-py3-none-any.whl
.testdelta/runtime-python/bin/python -I scripts/benchmark_runtime.py \
  --wheel dist/testdelta-0.1.0a3-py3-none-any.whl \
  --output .testdelta/performance/runtime-new-raw.json \
  --public-output .testdelta/runtime-new-summary.json
```

The harness refuses to overwrite an existing measurement. It checkpoints the
record after each attempt and exits nonzero when the fixed acceptance target
is missed. This benchmark is run explicitly and is not added to every CI run.
