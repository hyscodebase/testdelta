# Report format 0.1

The report is an alpha contract. Its JSON Schema is
[`schemas/report.v0.1.json`](../schemas/report.v0.1.json).

`plan` identifies the committed test revisions, selected source files and their
SHA-256 hashes. `environment` describes the supervisor process and is explicitly
labeled with `environment_role`. `target_runtime` and each run's `runtime` record
the actual Python executable, Python version, and pytest version used for tests.
This is provenance, not a complete fingerprint of all installed dependencies or
external state. Replay requires the same recorded supervisor and target metadata
and the original Git revisions; it does not provision or reproduce an environment.

`mutants_completed` counts mutation pairs attempted, including pairs whose
outcomes were inconclusive. Always read `complete`, the verdict, and each outcome
together. `complete=true` means the entire selected plan and controls yielded
valid evidence. It does not mean all possible mutations were selected.

A `lost_kill` is confirmed with three pairs and final controls. A gain is labeled
`gained_kill_provisional` because it has only a single paired observation. Partial
confirmed findings may remain visible in `incomplete_with_witnesses`. Failed or
missing final controls downgrade all findings to `unconfirmed_control` and the
overall verdict to `inconclusive`.

Reports and bundles contain source snippets, test failures, runtime paths, and
captured output. Review them before sharing. A bundle checksum detects accidental
corruption; it does not authenticate its creator. Bundles are trusted local inputs,
not portable safe executables or self-contained environment archives.

External configuration records `manifest_origin=external`, exact UTF-8 text in
`manifest_snapshot.text`, and its raw-byte SHA-256. Replay checks that snapshot
against both its digest and `manifest_hash`; the original external file is not
needed. A base-committed manifest retains the default policy.

`test_diffs` records changed-test unified diffs, full generated-diff SHA-256 and
`truncated`. Each attempted mutant has `diff`, `diff_sha256`, and
`diff_truncated`. Display text is bounded to 20,000 characters per diff; the hash
identifies the complete generated diff. Unterminated lines have standard newline
markers. These diffs are local evidence and can contain source text.

Actual pytest runs record `started_at_utc`, `finished_at_utc`, and monotonic
`duration_seconds`. A `not_completed` placeholder represents an execution that
never started, so it has no artificial execution timestamps. `limits.suite_calls_max`
is the conservative bound `6 + 6 × max_mutants`, not a measured runtime estimate.

`testdelta export REPORT_DIRECTORY --output NEW_FILE` writes a separate
allowlisted summary. It omits raw diagnostics, source/config/diff text, absolute
paths, free-text reasons and arbitrary future fields; relative locations and
hashes remain. The automatic GitHub job summary is more compact and also omits
those raw fields. Full local reports and replay bundles are unchanged. An export
is not a replay bundle, an anonymizer, or an independent attestation of its input.
