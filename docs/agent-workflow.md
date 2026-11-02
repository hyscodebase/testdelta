# Reviewing TestDelta results with a coding agent

The repository ships [`skills/testdelta-review/SKILL.md`](../skills/testdelta-review/SKILL.md)
for agents that support the Agent Skills format. Install or reference that folder
using your agent's documented mechanism. TestDelta does not change your global
agent configuration or invoke a model itself.

A useful request is:

> Review this local TestDelta report for my test-only change. Explain confirmed
> losses and inconclusive work. If the intended behavior is clear and test changes
> are authorized, propose a test-only repair and verify it against the same fault.

The agent reads the canonical JSON and the selected test diff. It can explain
the concrete difference between old and new assertions and propose a repair.
The deterministic execution evidence remains the source of the verdict.

Replay is tied to the old and new commits saved in its bundle. Replaying the
bundle after editing a working tree simply rechecks those saved commits. To
evaluate a repair, commit it under the task's Git authorization, compare the
original base against the repaired head, and confirm the selected mutation ID
and source hashes are unchanged. A repair that changes production source or
test configuration is outside this alpha's comparison contract.

This skill's frontmatter and references are validated structurally. No measured
claim about model success rate, repair quality, or token savings is made.
