# GitHub Marketplace release status

Marketplace publication is pending. On 2026-11-02 the repository's release form
required the owner to accept the GitHub Marketplace Developer Agreement before
enabling publication. The owner must review and accept that agreement directly;
no acceptance is recorded by this project or its automation. A release page or
usable commit-pinned Action does not establish that a Marketplace listing is live.

The launch candidate uses Action display name **TestDelta Test Quality**, with
**Testing** as the intended primary category and **Code quality** as the intended
secondary category. These categories exist in the
[GitHub Marketplace category browser](https://github.com/marketplace?type=actions).
The release form must validate the final name and categories before publication.

The prior display name `TestDelta` conflicts with the existing
[`TestDelta` GitHub organization](https://github.com/TestDelta). GitHub disallows
an Action name matching another account unless its owner publishes that Action.
GitHub also requires a public repository, one root `action.yml` or `action.yaml`,
and a unique non-reserved Action name. See the official
[publication requirements](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace).

The candidate version is deliberately alpha:

| Identifier | Meaning |
| --- | --- |
| `v0.1.0-alpha.4` | Proposed GitHub Action release tag |
| `0.1.0a4` | Python CLI/tool version installed from that candidate checkout |
| `dae67c6d6b44bc4d3ceda51b4188c6ad8801efee` | Previously reviewed Action commit used by the current examples; installs `0.1.0a3` |

The Python version and GitHub tag use different prerelease syntax. The candidate
does not assert a stable release or PyPI publication. Examples will move to the
new reviewed full commit after that commit's CI is verified. See the
[complete native Action workflow](action.md) and [CLI workflow](ci.md).

The repository owner publishes through GitHub's release interface:

1. Open the root `action.yml` on GitHub and choose **Draft a release**.
2. Complete the owner agreement requirement if GitHub presents it, then enable
   **Publish this Action to the GitHub Marketplace**.
3. Resolve metadata validation messages, select the categories, and choose the
   reviewed alpha tag, target commit, title, and release notes.
4. Publish the release, completing GitHub's two-factor authentication if requested.
5. Open the resulting Marketplace URL and confirm its name, version, repository,
   installation snippet, and README before recording publication as complete.

This follows GitHub's
[official publishing flow](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace).
If GitHub rejects the prerelease choice or still disables publication, preserve
the alpha labeling and resolve the displayed requirement before claiming a listing.

The release candidate retains read-only consumer workflow permissions, local
reports, no automatic artifact upload, and no PR comment publisher. Test execution
is limited to trusted Python/pytest repositories under the documented alpha
scope. Marketplace publication does not expand that execution boundary.

The `0.1.0a4` bootstrap isolates initial Python imports and ignores caller pip
installation settings when installing its separate tool environment. This keeps
caller modules and `PIP_TARGET` from redirecting setup. Project dependencies still
come from the caller's selected Python. Pip documents the environment/configuration
behavior in its [configuration reference](https://pip.pypa.io/en/stable/topics/configuration/#pip-config-file).
