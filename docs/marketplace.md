# GitHub Marketplace release record

[TestDelta Test Quality](https://github.com/marketplace/actions/testdelta-test-quality)
was published on GitHub Marketplace on **2026-11-03**. The public listing identifies
`hyscodebase` as the publisher, links to this repository, and displays
`v0.1.0-alpha.4` as its latest prerelease. Its listed categories are **Testing**
and **Code quality**.

| Release field | Published value |
| --- | --- |
| GitHub release | [`v0.1.0-alpha.4`](https://github.com/hyscodebase/testdelta/releases/tag/v0.1.0-alpha.4), published prerelease |
| Publication time | `2026-11-03T02:17:52Z` (UTC) |
| Release API record | [`432194720`](https://api.github.com/repos/hyscodebase/testdelta/releases/432194720), `draft: false` |
| Exact target commit | [`55d64056c14834eab99cf49ca86c4786a14804bd`](https://github.com/hyscodebase/testdelta/commit/55d64056c14834eab99cf49ca86c4786a14804bd) |
| Python CLI/tool version | `0.1.0a4` |
| Repository | [`hyscodebase/testdelta`](https://github.com/hyscodebase/testdelta) |

Publication completed after owner authorization. The earlier agreement and
authentication requirements are resolved; the listing and release are public.
The Python version and GitHub tag use different prerelease syntax. This is an
alpha release, with no stable-release or PyPI-publication claim.

The [native Action workflow](action.md) and [CLI workflow](ci.md) pin the exact
released commit above. The Action installs its tool environment from that
checkout and uses the caller's prepared Python for project tests. The `0.1.0a4`
bootstrap and mutation worker isolate supervisor imports, and caller pip options
cannot redirect the separate tool installation.

The release commit's recorded checks passed: 195 source tests per supported
matrix job, the frozen 50-case conformance corpus, Ubuntu/macOS native Action
isolation traps, installed-wheel comparison/replay, and Pages deployment. Check
the [workflow runs](https://github.com/hyscodebase/testdelta/actions) for a specific
commit or subsequent rerun. The linked a3 runtime, corpus, and Boltons
compatibility artifacts retain their recorded versions and scope; publication
does not turn them into new a4 measurements. See [quality status](quality-status.md).

Consumer workflows retain `contents: read`, local reports, no automatic artifact
upload, and no PR comment publisher. Supported inputs remain committed test-only
Python/pytest changes with unchanged source, helpers, dependencies, and
configuration. Tests retain the host runner's filesystem and network access;
temporary workspaces are not a sandbox. Marketplace publication does not expand
the alpha's execution boundary.

Future listing updates use GitHub's
[official publishing flow](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace).
Verify the new release's target, CI, installation pin, and public Marketplace
page before updating this record.
