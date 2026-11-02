# Finite comparison conformance corpus

These 50 original MIT-licensed fixtures exercise the core comparison contract
with real pytest subprocesses: 30 development cases and 20 separately authored
validation cases. Each record supplies complete `subject.py` source, old and new
`tests/test_subject.py` bytes, a declared hand-authored control or `null`, an
expected verdict/completion, and a short rationale.

The fixture source and test bytes were frozen by SHA-256 in `manifest.json`
before execution. The validation records omitted the optional detailed failure
status; six explicit status supplements were declared in the manifest before
execution. Neither corpus is adjusted to remove observed disagreements.

| Split | Loss expected | No loss expected | Invalid new baseline expected |
| --- | ---: | ---: | ---: |
| Development | 10 | 10 | 10 |
| Validation | 7 | 7 | 6 |

The recorded runs matched all 30 development and all 20 validation expectations,
with zero disagreements. Both runs retained the frozen corpus hashes and
unchanged comparison/runner hashes. Public evidence is in
[`development.json`](../evidence/corpus/development.json),
[`validation.json`](../evidence/corpus/validation.json), and their
[`aggregate summary`](../evidence/corpus/summary.json). This is agreement on
these finite declared cases, not an estimate of accuracy on other inputs.

The 17 no-loss cases include retained kills, equivalent controls, and controls
that both test revisions miss. A no-loss result therefore remains scoped to its
declared control. Baseline-invalid cases require `baseline_not_valid` and the
specific expected failure status; an empty mutation list cannot satisfy them.

Run either split, or omit `--split` for all 50:

```sh
uv run python scripts/validate_corpus.py --split development --output .testdelta/corpus/development.json --public-output evidence/corpus/development.json
uv run python scripts/validate_corpus.py --split validation --output .testdelta/corpus/validation.json --public-output evidence/corpus/validation.json
uv run python scripts/validate_corpus.py
```

The harness calls `testdelta.compare.compare` and the production pytest runner.
Only the mutation provider result is supplied directly through
`mutations_override`; pytest execution, baseline classification, paired runs,
final controls, and verdict calculation are real. The same generic first
differing source line anchors every declared control. Reports identify this
provenance as `fixture_negative_control` and the snapshots as
`controlled_fixture_bytes_not_git`; no Git commits are fabricated.

The raw `--output` (by default `.testdelta/corpus/all.json`, ignored by Git)
includes full comparison reports/bundles and local diagnostic paths. Optional
`--public-output` contains an explicit allowlist: expected and actual outcomes,
checks, disagreements, versions, timestamps, durations, corpus and engine/runner
hashes, and sanitized execution summaries. It omits raw stdout, absolute paths,
source/config text, and replay bundles. Raw outputs are refused under
`evidence/`. A nonzero command exit means a disagreement or engine drift.
The normal test suite checks frozen corpus structure/hashes and one real loss
exemplar. The full corpus is a separate command suitable for a dedicated CI job.

Across the 34 complete valid fixtures whose four normal baselines each took at
most two seconds, observed comparison p95 was 5.111 seconds (nearest-rank;
maximum 5.224 seconds). Each fixture used one declared hand-authored control;
local CPU workload was not isolated. These timings do not establish a
ten-mutant or arbitrary-project runtime bound.

This finite corpus does not establish model accuracy, general accuracy,
automatic Cosmic Ray mutation quality, committed-Git input eligibility, or
behavior on arbitrary projects. Hand-authored controls are separate from the
automatic mutation provider. These trusted local fixtures use deterministic
standard-library subject code and make no source-code I/O or network requests.
See the repository [MIT license](../LICENSE).
