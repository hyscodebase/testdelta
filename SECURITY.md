# Security policy

TestDelta's initial alpha is intended for repositories whose tests you already trust enough to execute locally.

## Execution boundary

Comparisons execute pytest and project code. Disposable workspaces protect the original checkout from routine mutations; they do **not** provide an operating-system sandbox. Project code may read files, access the network, or launch processes with the current user's permissions. Do not run an unknown repository or an evidence bundle from an untrusted author on a machine containing credentials.

Use a disposable environment without secrets when evaluating external code. The bundled synthetic demo is maintained with this repository, but it still executes Python tests. TestDelta does not require an LLM API key, and the core comparison is not an LLM judge.

## Evidence bundles

Reports and bundles may include source code, tests, command output, and environment details. Inspect them before sharing. Do not attach credentials, private source, or unredacted logs to a public issue. Replaying a bundle is code execution, not a passive report viewer.

Incomplete, invalid, unsupported, or failed comparisons are not a clean bill of health. A successful comparison only describes the selected tests, mutations, and environment. It does not prove the application is secure or free of bugs.

## CI guidance

The repository's CI uses read-only GitHub permissions and pinned official actions. It does not need repository secrets. Do not change it to execute untrusted pull-request code using `pull_request_target` with privileged credentials.

For your own repository, run external pull requests in the same restricted environment you would use for their normal test suite. Upload only the artifacts you intend to disclose.

## Reporting a vulnerability

If the repository's GitHub Security page offers **Report a vulnerability**, use that private channel. Otherwise, open an issue asking for a private reporting channel without including exploit details, secrets, or private data. Do not assume that private vulnerability reporting is enabled.

Include the affected commit/version, a minimal reproduction using non-sensitive data, and the impact you observed. We currently maintain only the latest alpha; there is no promised security support window for older builds.
