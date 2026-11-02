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
