"""Execute the frozen finite comparison corpus using declared manual controls.

This is core-comparison conformance evidence, not a model benchmark, Git-input
eligibility test, or measurement of automatically generated mutation quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any

from testdelta.compare import compare as run_comparison
from testdelta.export import build_summary

ROOT = Path(__file__).resolve().parents[1]
VERDICTS = ("loss_observed", "no_loss_observed", "inconclusive")
BASELINE_FAILURES = {
    "assertion_failure", "collection_error", "not_executed", "fixture_error", "runtime_error",
}
ENGINE_FILES = (
    "src/testdelta/compare.py", "src/testdelta/git_inputs.py",
    "src/testdelta/runner/supervisor.py", "src/testdelta/runner/plugin.py",
)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def file_hashes(root: Path, paths: tuple[str, ...]) -> dict[str, str]:
    return {path: sha256((root / path).read_bytes()) for path in paths}


def expected_for(case: dict, manifest: dict) -> dict:
    """Use only the authored oracle and the pre-execution declared supplement."""
    supplement = manifest.get("supplemental_oracles", {}).get(case["id"], {})
    overlap = set(case["expected"]) & set(supplement)
    if any(case["expected"][key] != supplement[key] for key in overlap):
        raise ValueError(f"Conflicting oracle supplement for {case['id']}")
    return {**case["expected"], **supplement}


def load_corpora(root: Path = ROOT, split: str = "all") -> tuple[dict, list[dict]]:
    """Verify both frozen byte hashes before returning any executable fixture."""
    manifest = json.loads((root / "corpus/manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("frozen_before_execution"):
        raise ValueError("Corpus must be frozen before execution")
    if manifest.get("snapshot_kind") != "controlled_fixture_bytes_not_git":
        raise ValueError("Corpus snapshots must not be described as Git commits")
    if manifest.get("mutation_origin") != "fixture_negative_control":
        raise ValueError("Manual controls must have explicit fixture provenance")
    if set(manifest["corpora"]) != {"development", "validation"}:
        raise ValueError("Expected the development and validation splits")
    if split not in {"all", *manifest["corpora"]}:
        raise ValueError(f"Unknown corpus split: {split}")

    cases = []
    all_ids = set()
    for name, frozen in manifest["corpora"].items():
        if frozen["path"] != f"corpus/{name}.json":
            raise ValueError(f"Unexpected corpus path for {name}")
        content = (root / frozen["path"]).read_bytes()
        if sha256(content) != frozen["sha256"]:
            raise ValueError(f"Frozen corpus SHA-256 mismatch: {frozen['path']}")
        records = json.loads(content)
        if not isinstance(records, list) or len(records) != frozen["count"]:
            raise ValueError(f"Frozen corpus count mismatch: {name}")
        prefix = "dev" if name == "development" else "val"
        for index, case in enumerate(records, 1):
            if case.get("id") != f"{prefix}-{index:03}" or case.get("split") != name:
                raise ValueError(f"Unexpected case identity in {name} at position {index}")
            if case["id"] in all_ids:
                raise ValueError(f"Duplicate case: {case['id']}")
            all_ids.add(case["id"])
            for key in ("category", "source", "old_tests", "new_tests", "rationale"):
                if not isinstance(case.get(key), str) or not case[key].strip():
                    raise ValueError(f"Missing nonempty {key} in {case['id']}")
            if case.get("mutant") is not None and not isinstance(case["mutant"], str):
                raise ValueError(f"Invalid mutant source in {case['id']}")
            expected = expected_for(case, manifest)
            if expected.get("verdict") not in VERDICTS:
                raise ValueError(f"Invalid expected verdict in {case['id']}")
            if not isinstance(expected.get("complete"), bool):
                raise ValueError(f"Invalid expected completion in {case['id']}")
            if case["mutant"] is None:
                if expected != {
                    "verdict": "inconclusive", "complete": False,
                    "baseline_failure_status": expected.get("baseline_failure_status"),
                } or expected.get("baseline_failure_status") not in BASELINE_FAILURES:
                    raise ValueError(f"Invalid baseline oracle in {case['id']}")
            elif not expected["complete"] or expected["verdict"] == "inconclusive":
                raise ValueError(f"Unexpected valid-case oracle in {case['id']}")
            elif case["mutant"] == case["source"]:
                raise ValueError(f"Control has identical bytes in {case['id']}")
            if split in ("all", name):
                cases.append(case)
    if set(manifest.get("supplemental_oracles", {})) - all_ids:
        raise ValueError("Oracle supplement names an unknown fixture")
    return manifest, cases


def fixture_inputs(case: dict) -> tuple[dict, dict[str, bytes], dict[str, bytes], list[dict]]:
    """Build actual materializable snapshots without inventing Git provenance."""
    source = case["source"].encode("utf-8")
    old_tests = case["old_tests"].encode("utf-8")
    new_tests = case["new_tests"].encode("utf-8")
    manifest_bytes = b'source_modules = ["subject.py"]\ntest_paths = ["tests"]\n'
    before = {
        "subject.py": source, "tests/test_subject.py": old_tests,
        ".testdelta.toml": manifest_bytes,
    }
    after = {**before, "tests/test_subject.py": new_tests}
    plan = {
        "schema_version": "0.1", "snapshot_kind": "controlled_fixture_bytes_not_git",
        "fixture_id": case["id"], "fixture_split": case["split"],
        "mutation_origin": "fixture_negative_control",
        "manifest": {"source_modules": ["subject.py"], "test_paths": ["tests"]},
        "manifest_origin": "controlled_fixture_bytes", "manifest_hash": sha256(manifest_bytes),
        "source_hashes": {"subject.py": sha256(source)},
        "test_hashes": {
            "tests/test_subject.py": {"old": sha256(old_tests), "new": sha256(new_tests)},
        },
        "changed_files": ["tests/test_subject.py"], "test_files": ["tests/test_subject.py"],
        "supported": True, "unsupported_changes": [],
        "working_tree": "not_applicable_controlled_fixture_bytes",
    }
    mutations = []
    if case["mutant"] is not None:
        # A common generic rule anchors the first differing line; no case-specific
        # locations or expected outcomes are supplied to the comparison engine.
        line = next(
            index for index, (old, new) in enumerate(
                zip_longest(case["source"].splitlines(), case["mutant"].splitlines()), 1,
            ) if old != new
        )
        mutations.append({
            "id": f"{case['id']}-manual-control", "path": "subject.py", "line": line,
            "operator": "fixture_negative_control/hand_authored",
            "mutation_origin": "fixture_negative_control", "mutated_source": case["mutant"],
            "mutated_sha256": sha256(case["mutant"].encode("utf-8")),
            "original_sha256": sha256(source),
            "replacement_description": "Declared hand-authored fixture negative control",
        })
    return plan, before, after, mutations


def run_case(
    case: dict, manifest: dict, *, budget_seconds: float = 60,
    timeout_seconds: float = 10, python_executable: str | None = None,
) -> dict[str, Any]:
    """Call the production comparison and pytest runner with one manual provider result."""
    expected = expected_for(case, manifest)
    plan, before, after, mutations = fixture_inputs(case)
    started = time.monotonic()
    report, bundle = run_comparison(
        plan, before, after, budget_seconds=budget_seconds, max_mutants=1,
        timeout_seconds=timeout_seconds, python_executable=python_executable,
        mutations_override=mutations,
    )
    baseline = report.get("baseline", [])
    controls = report.get("controls", [])
    checks = {
        "verdict": report["verdict"] == expected["verdict"],
        "complete": report["complete"] == expected["complete"],
        "controlled_fixture_provenance": (
            report["plan"].get("snapshot_kind") == "controlled_fixture_bytes_not_git"
            and "base_sha" not in report["plan"] and "head_sha" not in report["plan"]
        ),
    }
    actual = {
        "verdict": report["verdict"], "complete": report["complete"],
        "reason": report.get("reason"),
        "baseline_statuses": [item["status"] for item in baseline],
        "control_statuses": [item["status"] for item in controls],
        "mutation_outcomes": [item["outcome"] for item in report.get("mutants", [])],
    }
    if case["mutant"] is None:
        actual["baseline_failure_status"] = baseline[-1]["status"] if baseline else None
        checks.update({
            "baseline_not_valid_reason": report.get("reason") == "baseline_not_valid",
            "specific_baseline_failure": (
                actual["baseline_failure_status"] == expected["baseline_failure_status"]
            ),
            "old_baseline_passes_before_new_failure": (
                len(baseline) == 2 and baseline[0].get("side") == "old"
                and baseline[0]["status"] == "pass" and baseline[1].get("side") == "new"
            ),
            "stops_before_mutation_or_final_control": (
                report["mutants_planned"] == report["mutants_completed"] == 0
                and not report["mutants"] and not report["witnesses"]
                and not controls and not bundle["mutations"]
            ),
        })
    else:
        checks.update({
            "four_passing_baselines": (
                len(baseline) == 4 and all(item["status"] == "pass" for item in baseline)
            ),
            "two_passing_final_controls": (
                len(controls) == 2 and all(item["status"] == "pass" for item in controls)
            ),
            "one_declared_control_completed": (
                report["mutants_planned"] == report["mutants_completed"] == 1
                and len(report["mutants"]) == 1 and bundle["mutations"] == mutations
            ),
        })
        if expected["verdict"] == "loss_observed":
            items = report.get("mutants", [])
            witnesses = report.get("witnesses", [])
            checks["three_pairs_and_confirmed_witness"] = (
                len(items) == len(witnesses) == 1
                and items[0]["outcome"] == "lost_kill"
                and len(items[0]["old"]) == len(items[0]["new"]) == 3
                and witnesses[0]["confirmation"] == "three_pairs_and_final_controls"
            )
    return {
        "id": case["id"], "split": case["split"], "category": case["category"],
        "expected": expected, "actual": actual, "checks": checks,
        "matches_expected": all(checks.values()),
        "duration_seconds": round(time.monotonic() - started, 3),
        "report": report, "bundle": bundle,
    }


def summarize(results: list[dict]) -> dict:
    confusion = {expected: {actual: 0 for actual in VERDICTS} for expected in VERDICTS}
    for result in results:
        observed = result["actual"]["verdict"]
        row = confusion[result["expected"]["verdict"]]
        row[observed] = row.get(observed, 0) + 1
    disagreements = [
        {"id": result["id"], "expected": result["expected"], "actual": result["actual"],
         "failed_checks": [key for key, value in result["checks"].items() if not value]}
        for result in results if not result["matches_expected"]
    ]
    eligible = [
        result for result in results
        if result["expected"]["complete"] and result["actual"]["complete"]
        and len(result["report"]["baseline"]) == 4
        and all(item["status"] == "pass" and item["duration_seconds"] <= 2
                for item in result["report"]["baseline"])
    ]
    durations = sorted(result["duration_seconds"] for result in eligible)
    runtime = {
        "workload": "one_declared_hand_authored_control_per_complete_valid_fixture",
        "eligibility": "all_four_normal_baselines_pass_and_each_takes_at_most_2_seconds",
        "eligible_cases": len(eligible), "excluded_executed_cases": len(results) - len(eligible),
        "percentile_method": "nearest_rank",
        "comparison_p50_seconds": durations[math.ceil(len(durations) * 0.50) - 1]
        if durations else None,
        "comparison_p95_seconds": durations[math.ceil(len(durations) * 0.95) - 1]
        if durations else None,
        "comparison_max_seconds": max(durations, default=None),
        "scope": "Observed local runtime only; not a ten-mutant or arbitrary-project bound.",
    }
    return {
        "cases_executed": len(results),
        "matched_expectations": sum(result["matches_expected"] for result in results),
        "disagreements": disagreements,
        "expected_counts": dict(Counter(result["expected"]["verdict"] for result in results)),
        "observed_counts": dict(Counter(result["actual"]["verdict"] for result in results)),
        "confusion_matrix_expected_rows": confusion,
        "runtime_observations": runtime,
    }


def write_artifact(artifact: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")


def public_artifact(artifact: dict) -> dict:
    """Project explicit public fields; raw diagnostics and bundles stay local."""
    public = {
        key: artifact[key] for key in (
            "schema_version", "evidence_kind", "generated_at_utc", "snapshot_kind",
            "mutation_origin", "comparison_entrypoint", "runner_evidence",
            "automatic_mutation_generation_exercised", "git_snapshot_eligibility_exercised",
            "scope", "split", "planned_cases", "frozen_corpora", "manifest_sha256",
            "engine_sha256_before", "limits_per_case", "execution_complete",
        )
    }
    for key in ("engine_sha256_after", "engine_unchanged_during_execution", "finished_at_utc"):
        if key in artifact:
            public[key] = artifact[key]
    public.update({
        "export_kind": "allowlisted_corpus_summary",
        "raw_diagnostics_included": False,
        "runtime_context": "Local CPU workload was not isolated; concurrent tests may run.",
        "results": [],
    })
    for result in artifact["results"]:
        report_summary = build_summary(result["report"])
        record = {
            key: result[key] for key in (
                "id", "split", "category", "expected", "actual", "checks",
                "matches_expected", "duration_seconds",
            )
        }
        record["execution_summary"] = report_summary
        record["versions"] = {}
        environment = result["report"].get("environment", {})
        target = result["report"].get("target_runtime", {})
        for name, value in {
            "supervisor_python": environment.get("python"),
            "target_python": target.get("python_version"),
            "target_pytest": target.get("pytest_version"),
            **environment.get("versions", {}),
        }.items():
            if name in {
                "supervisor_python", "target_python", "target_pytest",
                "testdelta", "pytest", "cosmic-ray",
            } and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]*", value):
                record["versions"][name] = value
        public["results"].append(record)
    # This summary is produced by this harness from only verdicts, counts,
    # checks, IDs and durations; it never consumes stdout/config/source text.
    public["summary"] = artifact["summary"]
    return public


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("all", "development", "validation"), default="all")
    parser.add_argument("--output", type=Path, default=ROOT / ".testdelta/corpus/all.json")
    parser.add_argument("--public-output", type=Path)
    parser.add_argument("--budget-seconds", type=float, default=60)
    parser.add_argument("--timeout-seconds", type=float, default=10)
    parser.add_argument("--python", dest="python_executable")
    parser.add_argument("--runtime-context", default="Uncontrolled local workload; CPU is not isolated.")
    args = parser.parse_args(argv)
    if args.output.resolve().is_relative_to((ROOT / "evidence").resolve()):
        parser.error("Raw reports belong outside evidence/; use --public-output for public summaries")
    if not all(math.isfinite(value) and value > 0 for value in (
        args.budget_seconds, args.timeout_seconds,
    )):
        parser.error("Time limits must be finite and positive")

    manifest, cases = load_corpora(split=args.split)
    frozen_engine = file_hashes(ROOT, ENGINE_FILES)
    artifact = {
        "schema_version": "1.0", "evidence_kind": "finite_core_comparison_conformance",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_kind": "controlled_fixture_bytes_not_git",
        "mutation_origin": "fixture_negative_control",
        "comparison_entrypoint": "testdelta.compare.compare",
        "runner_evidence": "actual_pytest_subprocesses",
        "automatic_mutation_generation_exercised": False,
        "git_snapshot_eligibility_exercised": False,
        "scope": "Finite conformance fixtures; no model or general-accuracy claim.",
        "runtime_context": args.runtime_context,
        "split": args.split, "planned_cases": len(cases),
        "frozen_corpora": manifest["corpora"],
        "manifest_sha256": sha256((ROOT / "corpus/manifest.json").read_bytes()),
        "engine_sha256_before": frozen_engine,
        "limits_per_case": {
            "budget_seconds": args.budget_seconds, "timeout_seconds": args.timeout_seconds,
            "max_mutants": 1,
        },
        "execution_complete": False, "results": [], "summary": summarize([]),
    }
    write_artifact(artifact, args.output)
    if args.public_output:
        write_artifact(public_artifact(artifact), args.public_output)
    for case in cases:
        result = run_case(
            case, manifest, budget_seconds=args.budget_seconds,
            timeout_seconds=args.timeout_seconds, python_executable=args.python_executable,
        )
        artifact["results"].append(result)
        artifact["summary"] = summarize(artifact["results"])
        write_artifact(artifact, args.output)
        if args.public_output:
            write_artifact(public_artifact(artifact), args.public_output)
        status = "MATCH" if result["matches_expected"] else "DISAGREEMENT"
        print(f"{case['id']} {status}: {result['actual']['verdict']}", flush=True)

    # Detect input or engine changes during execution instead of presenting a
    # mixed-version run as one frozen evaluation.
    load_corpora(split=args.split)
    artifact["engine_sha256_after"] = file_hashes(ROOT, ENGINE_FILES)
    artifact["engine_unchanged_during_execution"] = (
        artifact["engine_sha256_after"] == artifact["engine_sha256_before"]
    )
    artifact["execution_complete"] = len(artifact["results"]) == len(cases)
    artifact["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_artifact(artifact, args.output)
    if args.public_output:
        write_artifact(public_artifact(artifact), args.public_output)
    print(json.dumps(artifact["summary"], indent=2))
    return int(bool(artifact["summary"]["disagreements"])
               or not artifact["engine_unchanged_during_execution"])


if __name__ == "__main__":
    sys.exit(main())
