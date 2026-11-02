"""Reproduce a pinned upstream test-only change in a local derived repository.

Network is used only to clone/fetch the named public repository. No upstream
changes, messages, issues, or pull requests are made. The selected upstream tests
execute locally with the caller's permissions; this is not a sandbox.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from testdelta.compare import compare, write_bundle
from testdelta.git_inputs import make_plan
from testdelta.report import write_report

CASES = {
    "pr564": {
        "url": "https://github.com/mahmoud/boltons/pull/564",
        "base": "4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d",
        "head": "7ea6c0bade3e1057593afd67bb6bc6bd7097f098",
        "source": "boltons/queueutils.py", "tests": "tests/test_queueutils.py",
        "context": "Closed unmerged test-strengthening proposal; not evidence of adoption.",
    },
    "pr408": {
        "url": "https://github.com/mahmoud/boltons/pull/408",
        "base": "3970a80f63807392e512340c25dc2db473bcba70",
        "head": "b14382f0710333d11fb56b73e2218771e537c1e9",
        "source": "boltons/listutils.py", "tests": "tests/test_listutils.py",
        "context": "Merged cleanup removing a module-import test invocation.",
    },
}


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments], check=True,
        capture_output=True, text=True, timeout=180,
    )
    return result.stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", ".testdelta.toml", "tests")
    env = dict(os.environ)
    # Fixed metadata identifies derived setup commits reproducibly, not the PR's authors.
    env.update(GIT_AUTHOR_DATE="2026-11-02T00:00:00+00:00",
               GIT_COMMITTER_DATE="2026-11-02T00:00:00+00:00")
    subprocess.run([
        "git", "-C", str(repo), "-c", "user.name=TestDelta Compatibility Fixture",
        "-c", "user.email=testdelta-fixture@example.invalid", "-c", "commit.gpgsign=false",
        "-c", "core.hooksPath=/dev/null", "commit", "-qm", message,
    ], check=True, capture_output=True, env=env, timeout=30)
    return git(repo, "rev-parse", "HEAD")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, default="pr564")
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--max-mutants", type=int, default=10)
    parser.add_argument("--budget-seconds", type=float, default=180)
    args = parser.parse_args()
    case = CASES[args.case]
    root = args.workdir or Path(tempfile.mkdtemp(prefix=f"testdelta-{args.case}-"))
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repository"
    if repo.exists():
        raise ValueError("Use an empty work directory; existing repositories are never overwritten")
    subprocess.run(["git", "clone", "--no-checkout", "https://github.com/mahmoud/boltons.git", str(repo)],
                   check=True, timeout=180)
    git(repo, "fetch", "origin", f"pull/{args.case[2:]}/head")
    changed = git(repo, "diff", "--name-only", case["base"], case["head"]).splitlines()
    if changed != [case["tests"]]:
        raise ValueError(f"Pinned upstream change differs from the selected test-only scope: {changed}")
    git(repo, "checkout", "--detach", case["base"])
    (repo / ".testdelta.toml").write_text(
        f'source_modules = ["{case["source"]}"]\ntest_paths = ["{case["tests"]}"]\n',
        encoding="utf-8",
    )
    derived_base = commit(repo, "Add identical TestDelta compatibility manifest")
    git(repo, "restore", "--source", case["head"], "--", case["tests"])
    derived_head = commit(repo, "Apply only the pinned upstream test change")
    plan, before, after = make_plan(repo, derived_base, derived_head, direct_base=True)
    report, bundle = compare(
        plan, before, after, max_mutants=args.max_mutants,
        budget_seconds=args.budget_seconds, timeout_seconds=15,
    )
    provenance = {**case, "derived_base": derived_base, "derived_head": derived_head,
                  "setup": "Only an identical manifest was added; upstream test/source bytes preserved.",
                  "expected_source_unchanged": before[case["source"]] == after[case["source"]],
                  "project": "boltons", "license": "BSD-3-Clause",
                  "license_url": f'https://github.com/mahmoud/boltons/blob/{case["head"]}/LICENSE'}
    report["upstream_case"] = provenance
    write_report(report, root / "report")
    write_bundle(bundle, root / "report")
    summary = {"case": args.case, "provenance": provenance,
               "verdict": report["verdict"], "complete": report["complete"],
               "mutants_planned": report["mutants_planned"],
               "mutants_completed": report["mutants_completed"],
               "outcomes": [m["outcome"] for m in report["mutants"]],
               "baseline_statuses": [r["status"] for r in report["baseline"]],
               "control_statuses": [r["status"] for r in report["controls"]],
               "reason": report.get("reason"), "duration_seconds": report.get("duration_seconds"),
               "environment": report["environment"],
               "report_directory": str((root / "report").resolve())}
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
