"""Bounded paired executions with controls and repeatable lost-fault evidence."""

from __future__ import annotations

import difflib
import hashlib
import importlib.metadata
import json
import math
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from testdelta.adapters.bounded import generate_bounded
from testdelta.git_inputs import digest, materialize, test_overlay
from testdelta.runner.supervisor import run_pytest


def environment() -> dict:
    versions = {}
    for name in ("testdelta", "pytest", "cosmic-ray"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unknown"
    return {"python": platform.python_version(), "platform": platform.platform(), "versions": versions}


def target_runtime(python_executable: str | None = None) -> dict:
    """Observe the interpreter actually selected for project tests."""
    result = subprocess.run(
        [python_executable or sys.executable, "-I", "-c",
         "import json,platform,sys,pytest; "
         "print(json.dumps(dict(python_version=platform.python_version(),"
         "python_executable=sys.executable,pytest_version=pytest.__version__)))"],
        capture_output=True, text=True, timeout=10, check=True,
    )
    return json.loads(result.stdout)


def unified_diff(old: bytes, new: bytes, path: str, limit: int = 20000) -> dict:
    """Bound display text while retaining a digest of the complete UTF-8 diff."""
    lines = difflib.unified_diff(
        old.decode("utf-8", "replace").splitlines(keepends=True),
        new.decode("utf-8", "replace").splitlines(keepends=True),
        fromfile=f"old/{path}", tofile=f"new/{path}",
    )
    value = "".join(line if line.endswith("\n") else
                    line + "\n\\ No newline at end of file\n" for line in lines)
    return {"path": path, "diff": value[:limit], "sha256": digest(value.encode()),
            "truncated": len(value) > limit}


def compare(
    plan: dict, before: dict[str, bytes], after: dict[str, bytes], *,
    budget_seconds: float = 120, max_mutants: int = 10, timeout_seconds: float = 15,
    python_executable: str | None = None,
    mutations_override: list[dict] | None = None,
) -> tuple[dict, dict]:
    started = time.monotonic()
    if not all(math.isfinite(v) and v > 0 for v in (budget_seconds, timeout_seconds)):
        raise ValueError("Time budgets must be finite and positive")
    if not 1 <= max_mutants <= 100:
        raise ValueError("max_mutants must be between 1 and 100")
    old_files = test_overlay(after, before, plan["test_files"])
    manifest = plan["manifest"]
    env = environment()
    runtime = {}
    report = {
        "schema_version": "0.1", "evidence_kind": "actual_pytest_execution",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan": {k: v for k, v in plan.items() if k != "repo"},
        "environment": env, "environment_role": "supervisor",
        "environment_hash": digest(json.dumps(env, sort_keys=True).encode()),
        "target_runtime": runtime,
        "verdict": "inconclusive", "complete": False, "witnesses": [], "mutants": [],
        "baseline": [], "controls": [], "mutants_planned": 0, "mutants_completed": 0,
        "limits": {"budget_seconds": budget_seconds, "max_mutants": max_mutants,
                   "timeout_seconds": timeout_seconds, "suite_calls_max": 6 + 6 * max_mutants},
        "test_diffs": [unified_diff(before.get(p, b""), after.get(p, b""), p)
                       for p in plan["test_files"] if before.get(p) != after.get(p)],
        "limitations": ["finite_mutation_scope", "trusted_local_code_not_a_sandbox",
                        "test_only_comparison", "gains_are_single_run_provisional"],
    }
    bundle = {"schema_version": "0.1", "plan": report["plan"], "mutations": [],
              "source_hashes": plan["source_hashes"], "environment": env,
              "target_runtime": runtime,
              "runtime_executable": str(Path(python_executable or sys.executable).absolute())}
    if not plan["supported"]:
        report.update(verdict="unsupported_change", reason=plan["unsupported_changes"])
        return report, bundle
    runtime = target_runtime(python_executable)
    report["target_runtime"] = runtime
    bundle["target_runtime"] = runtime

    def remaining() -> float:
        return budget_seconds - (time.monotonic() - started)

    def run(side: str, mutant: dict | None = None, reserve: float = 0) -> dict:
        available = remaining() - reserve
        if available < 0.1:
            return {"status": "not_completed", "reason": "total_budget_exhausted"}
        files = dict(old_files if side == "old" else after)
        hashes = dict(plan["source_hashes"])
        if mutant:
            files[mutant["path"]] = mutant["mutated_source"].encode("utf-8")
            hashes[mutant["path"]] = digest(files[mutant["path"]])
        with tempfile.TemporaryDirectory(prefix="testdelta-run-") as temporary:
            workspace = Path(temporary)
            materialize(files, workspace)
            result = run_pytest(
                workspace, manifest["test_paths"], min(timeout_seconds, available),
                hashes, python_executable=python_executable,
            )
        result["side"] = side
        observed = result.get("runtime")
        if observed and observed != runtime:
            result["status"] = "invalid_evidence"
            result["reason"] = "target_runtime_changed"
        return result

    for _ in range(2):
        for side in ("old", "new"):
            result = run(side)
            report["baseline"].append(result)
            if result["status"] != "pass":
                report["reason"] = "baseline_not_valid"
                report["duration_seconds"] = round(time.monotonic() - started, 3)
                return report, bundle

    # Reserve time for final normal-source controls even when mutations exhaust the budget.
    max_baseline = max(r.get("duration_seconds", 0.5) for r in report["baseline"])
    reserve = 2 * max_baseline + 0.5
    with tempfile.TemporaryDirectory(prefix="testdelta-plan-") as temporary:
        workspace = Path(temporary)
        materialize(after, workspace)
        try:
            if remaining() <= reserve + 0.1:
                raise subprocess.TimeoutExpired("mutation generation", 0)
            mutations = mutations_override if mutations_override is not None else generate_bounded(
                workspace, manifest["source_modules"], max_mutants, remaining() - reserve
            )
        except subprocess.TimeoutExpired:
            report["reason"] = "mutation_generation_budget_exhausted"
            report["controls"] = [run("old"), run("new")]
            report["duration_seconds"] = round(time.monotonic() - started, 3)
            return report, bundle
    report["mutants_planned"] = len(mutations)
    bundle["mutations"] = mutations
    if not mutations:
        report["reason"] = "no_supported_mutations"
        return report, bundle

    all_valid = True
    for mutant in mutations:
        if remaining() < reserve + 2 * max_baseline:
            report["reason"] = "total_budget_exhausted"
            break
        patch = unified_diff(after[mutant["path"]], mutant["mutated_source"].encode(), mutant["path"])
        item = {"id": mutant["id"], "path": mutant["path"], "line": mutant["line"],
                "operator": mutant["operator"], "mutated_sha256": mutant["mutated_sha256"],
                "diff": patch["diff"], "diff_sha256": patch["sha256"],
                "diff_truncated": patch["truncated"],
                "old": [run("old", mutant, reserve)], "new": [run("new", mutant, reserve)]}

        def outcome(result: dict) -> str:
            if result["status"] == "pass":
                return "survived"
            reached = result.get("reached_lines", {}).get(mutant["path"], [])
            if result["status"] == "assertion_failure" and mutant["line"] in reached:
                return "killed"
            return "inconclusive"

        old_status, new_status = outcome(item["old"][0]), outcome(item["new"][0])
        if (old_status, new_status) == ("killed", "survived"):
            for _ in range(2):
                item["old"].append(run("old", mutant, reserve))
                item["new"].append(run("new", mutant, reserve))
            if all(outcome(r) == "killed" for r in item["old"]) and all(
                outcome(r) == "survived" for r in item["new"]
            ):
                item["outcome"] = "lost_kill"
                report["witnesses"].append({
                    **{k: item[k] for k in ("id", "path", "line", "operator")},
                    "confirmation": "pending_final_controls",
                    "old_outcomes": [outcome(r) for r in item["old"]],
                    "new_outcomes": [outcome(r) for r in item["new"]],
                    "mutated_sha256": mutant["mutated_sha256"],
                    "original_sha256": mutant["original_sha256"],
                    "replacement_description": mutant["replacement_description"],
                    "old_failure_nodes": item["old"][0].get("assertion_failure_nodes", []),
                })
            else:
                item["outcome"] = "unstable_or_incomplete"
                all_valid = False
        elif "inconclusive" in (old_status, new_status):
            item["outcome"] = "inconclusive"
            all_valid = False
        else:
            item["outcome"] = {("killed", "killed"): "retained_kill",
                               ("survived", "killed"): "gained_kill_provisional",
                               ("survived", "survived"): "survived_both"}[(old_status, new_status)]
        report["mutants"].append(item)
        report["mutants_completed"] += 1

    report["controls"] = [run("old"), run("new")]
    controls_valid = all(r["status"] == "pass" for r in report["controls"])
    completed = report["mutants_completed"] == len(mutations)
    report["complete"] = completed and all_valid and controls_valid
    if controls_valid:
        for witness in report["witnesses"]:
            witness["confirmation"] = "three_pairs_and_final_controls"
        if report["complete"]:
            report["verdict"] = "loss_observed" if report["witnesses"] else "no_loss_observed"
        elif report["witnesses"]:
            report["verdict"] = "incomplete_with_witnesses"
    else:
        for witness in report["witnesses"]:
            witness["confirmation"] = "unconfirmed_control"
        report["reason"] = "final_controls_not_valid"
    if not report["complete"] and not report.get("reason"):
        report["reason"] = "mutant_execution_inconclusive"
    report["duration_seconds"] = round(time.monotonic() - started, 3)
    return report, bundle


def write_bundle(bundle: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    content = json.dumps(bundle, indent=2) + "\n"
    (output / "bundle.json").write_text(content, encoding="utf-8")
    (output / "bundle.sha256").write_text(hashlib.sha256(content.encode()).hexdigest() + "\n")
