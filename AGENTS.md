# Working on TestDelta

Use Python 3.11–3.13. `uv sync --extra dev` installs the development environment.
Run `uv run pytest`, `uv run ruff check .`, and a built-wheel demo before release.

Core invariants:

- Only compare committed test-only changes with unchanged source/config/dependencies.
- Treat external config as explicit trusted policy; record its exact bytes/hash for replay.
- Generate a mutation once and materialize identical bytes for both test revisions.
- Require passing original-source controls. Collection, setup, runtime errors,
  skips, missing tests, timeouts, and unfinished work are never clean evidence.
- A lost fault needs three consistent old/new pairs and valid final controls.
- Check source hashes and imported origins; never edit the user's checkout.
- Record target interpreter provenance separately from supervisor provenance.
- Temporary workspaces execute trusted local code; they are not a sandbox.
- Keep README commands and alpha limitations consistent with actual behavior.

The maintainer works alone with agent assistance. Own implementation, debugging,
documentation, CI, and routine repository work; do not turn planned team roles or
optional user research into prerequisite chores for the maintainer.
