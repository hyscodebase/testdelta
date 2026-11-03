# Alpha quality status

The alpha release [`v0.1.0-alpha.4`](https://github.com/hyscodebase/testdelta/releases/tag/v0.1.0-alpha.4)
was published on 2026-11-03 as
[TestDelta Test Quality on GitHub Marketplace](https://github.com/marketplace/actions/testdelta-test-quality).
Its target commit, `55d64056c14834eab99cf49ca86c4786a14804bd`, passed 195 source
tests on the supported matrix, the frozen-corpus job, native Action/wheel
integration, and Pages deployment. The [public demo](https://hyscodebase.github.io/testdelta/)
is live. See the [release record](marketplace.md) for exact publication details.
The linked a3 corpus, runtime, and compatibility artifacts retain their historical,
scoped meaning; the a4 release does not turn them into new measurements.

CLI/tool version `0.1.0a4` packages the executable solo MVP and its launch updates.
It remains alpha. The original eight-week research and growth plan is not
represented as completed. Routine implementation, checks, documentation and
release work are handled in the repository; maintainer interviews or team
recruitment are not user prerequisites.

| Area | Evidence and boundary |
| --- | --- |
| Same-fault comparison | Real committed test-only inputs, unchanged source hashes, one mutation materialized identically, repeated losses and final controls |
| Existing PR setup | External manifest bytes/hash recorded; replay works after removing the original config file |
| Target environment | Native Action uses an isolated tool venv and prepared project interpreter; pytest 9.2.0 vs 8.4.2 was exercised without changing project packages |
| Finite classification corpus | [Recorded a3 artifact: 50/50 matched](../evidence/corpus/summary.json): 17 loss,17 no-loss,16 invalid baseline. Frozen 30 development +20 validation; hand-authored controls, separate from automatic mutation quality. The release CI separately re-exercises this corpus |
| Runtime | [Fixed 20-repetition measurement](performance.md), with exact workload, setup exclusions, errors and acceptance result retained |
| Package rehearsal | Installed-wheel committed comparison and replay; CI also tests the wheel demo |
| CI | Four Python/OS test jobs, one frozen-corpus job, two native Action jobs and one clean-wheel compare/replay job; check the [actual runs](https://github.com/hyscodebase/testdelta/actions) for the commit in use |
| Shared evidence | Local raw reports remain detailed; automatic job summary and explicit export use an allowlist without raw logs/source/config text or absolute runtime paths |
| Real repositories | [Two pinned Boltons PR checks](compatibility.md), both inconclusive. No qualified witness, clean result, adoption or general accuracy claim |

The following original-plan targets remain unestablished or deferred in this alpha: a network-blocked Linux execution profile; complete dependency/OS-image replay attestation; a classified 20-public-PR corpus across at least three repositories; independent human relevance labels and report-preference studies; external repeat use and growth outcomes. The local runtime measurement does not establish a cross-platform or arbitrary-project bound.

Tests execute trusted local code with host filesystem/network permissions. Windows, third-party pytest plugin-dependent suites, mixed source/test changes and arbitrary monorepos are outside the supported initial scope. Inconclusive executions remain visible. The finite corpus is conformance evidence, not a scientific estimate of real-world accuracy.

Stars, downloads and continued use are separate outcomes. No 1,000-star guarantee, comparative superiority, or algorithmic novelty is claimed. No external maintainer was contacted as part of this development handoff.
