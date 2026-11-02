"""Fixed, sequential 20-run acceptance measurement of the original pricing fixture.

Run with the installed TestDelta environment. Fixture creation and dependency
installation are excluded; every timed repetition reads the Git plan and executes
the complete comparison, including actual Cosmic Ray generation and controls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import testdelta
from testdelta.compare import compare, environment
from testdelta.export import build_summary
from testdelta.git_inputs import make_plan

ROOT = Path(__file__).resolve().parents[1]
REPETITIONS = 20
MAX_MUTANTS = 10
BUDGET_SECONDS = 120
TIMEOUT_SECONDS = 15
BASELINE_LIMIT_SECONDS = 2
SOURCE = (
    "def total(price, quantity=1, member=False):\n"
    "    subtotal = price * quantity\n"
    "    if member:\n        subtotal = subtotal * 9 // 10\n"
    "    shipping = 0 if subtotal >= 5000 else 500\n"
    "    return subtotal + shipping\n"
)
STRONG = (
    "from pricing import total\n\n"
    "def test_quantity():\n    assert total(1000, 3) == 3500\n\n"
    "def test_member():\n    assert total(1000, member=True) == 1400\n\n"
    "def test_shipping_boundary():\n    assert total(5000) == 5000\n\n"
    "def test_shipping_below():\n    assert total(4999) == 5499\n"
)
WEAK = STRONG.replace("== 3500", ">= 0").replace("== 1400", ">= 0").replace(
    "== 5000", ">= 0"
).replace("== 5499", ">= 0")
MANIFEST = 'source_modules = ["src/pricing.py"]\ntest_paths = ["tests/test_pricing.py"]\n'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *arguments: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-11-02T00:00:00+00:00",
               GIT_COMMITTER_DATE="2026-11-02T00:00:00+00:00")
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=TestDelta Runtime Fixture", "-c",
         "user.email=testdelta-benchmark@example.invalid", "-c", "commit.gpgsign=false", "-c",
         "core.hooksPath=/dev/null", *arguments],
        env=env, check=True, capture_output=True, text=True, timeout=30,
    ).stdout.strip()


def fixture(repo: Path) -> dict:
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src/pricing.py").write_text(SOURCE, encoding="utf-8")
    (repo / ".testdelta.toml").write_text(MANIFEST, encoding="utf-8")
    tests = repo / "tests/test_pricing.py"
    tests.write_text(STRONG, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Original strong pricing tests")
    base = git(repo, "rev-parse", "HEAD")
    tests.write_text(WEAK, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Weaken only pricing assertions")
    head = git(repo, "rev-parse", "HEAD")
    assert git(repo, "diff", "--name-only", base, head) == "tests/test_pricing.py"
    return {
        "base_sha": base, "head_sha": head,
        "source": SOURCE, "source_sha256": sha256(SOURCE.encode()),
        "old_tests": STRONG, "old_tests_sha256": sha256(STRONG.encode()),
        "new_tests": WEAK, "new_tests_sha256": sha256(WEAK.encode()),
        "manifest": MANIFEST, "manifest_sha256": sha256(MANIFEST.encode()),
    }


def implementation() -> dict:
    package = Path(testdelta.__file__).parent
    return {str(path.relative_to(package)): sha256(path.read_bytes())
            for path in sorted(package.rglob("*.py"))}


def nearest_rank_p95(values: list[float]) -> float | None:
    return sorted(values)[math.ceil(0.95 * len(values)) - 1] if values else None


def load_average() -> list[float] | None:
    return list(os.getloadavg()) if hasattr(os, "getloadavg") else None


def exclusions(report: dict | None, error: dict | None) -> list[str]:
    if error:
        return ["comparison_error"]
    if report is None:
        return ["missing_report"]
    result = []
    baseline = report["baseline"]
    if len(baseline) != 4 or any(run["status"] != "pass" for run in baseline):
        result.append("invalid_original_source_baselines")
    if not baseline or any(run.get("duration_seconds", math.inf) > BASELINE_LIMIT_SECONDS
                           for run in baseline):
        result.append("baseline_exceeds_2_seconds")
    if report["mutants_planned"] != MAX_MUTANTS:
        result.append("provider_did_not_select_exactly_10_mutants")
    if report["mutants_completed"] != MAX_MUTANTS:
        result.append("did_not_complete_exactly_10_mutants")
    if not report["complete"]:
        result.append("incomplete_comparison")
    if report["verdict"] != "loss_observed":
        result.append("expected_loss_not_observed")
    return result


def summary(runs: list[dict], finished: bool) -> dict:
    eligible = [run for run in runs if run["eligible"]]
    all_durations = [run["wall_seconds"] for run in runs]
    eligible_p95 = nearest_rank_p95([run["wall_seconds"] for run in eligible])
    passed = (finished and len(runs) == REPETITIONS and len(eligible) == REPETITIONS
              and eligible_p95 is not None and eligible_p95 <= BUDGET_SECONDS)
    return {
        "status": "met" if passed else "missed" if finished else "in_progress",
        "attempted_repetitions": len(runs), "eligible_repetitions": len(eligible),
        "excluded_repetitions": [
            {"repetition": run["repetition"], "reasons": run["exclusions"]}
            for run in runs if not run["eligible"]
        ],
        "all_attempts_nearest_rank_p95_seconds": nearest_rank_p95(all_durations),
        "eligible_nearest_rank_p95_seconds": eligible_p95,
        "minimum_wall_seconds": min(all_durations) if all_durations else None,
        "maximum_wall_seconds": max(all_durations) if all_durations else None,
        "acceptance_requires_all_20_eligible": True,
        "errors": sum(run["error"] is not None for run in runs),
    }


def _duration(value) -> float | None:
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def public_artifact(data: dict) -> dict:
    """Keep every attempt while omitting raw source/config/logs and absolute paths."""
    mutation_plans = [
        [(item.get("id"), item.get("mutated_sha256")) for item in run["report"]["mutants"]]
        for run in data["runs"] if run["report"]
    ]
    public = {key: data[key] for key in (
        "schema_version", "evidence_kind", "started_at_utc", "parameters", "wheel", "host",
        "implementation_sha256", "setup_seconds", "summary",
    )}
    if "finished_at_utc" in data:
        public["finished_at_utc"] = data["finished_at_utc"]
    public.update({
        "export_kind": "allowlisted_runtime_summary", "raw_diagnostics_included": False,
        "implementation_unchanged_during_execution": all(
            "supervisor_implementation_changed" not in run["exclusions"] for run in data["runs"]
        ),
        "mutation_plan_identical_across_repetitions": all(
            plan == mutation_plans[0] for plan in mutation_plans
        ) if mutation_plans else None,
        "mutation_provider": "Actual Cosmic Ray generation via generate_bounded; no overrides",
        "load_average_intervals_minutes": [1, 5, 15],
        "fixture_origin": "Original testdelta.cli.demo pricing source and strong tests; "
                          "only its four equality assertions changed to >= 0",
        "host": {**data["host"], "platform": data["environment"]["platform"]},
        "fixture": {key: value for key, value in data["fixture"].items()
                    if key.endswith("_sha256") or key in {"base_sha", "head_sha"}},
        "limitations": [
            "One synthetic four-test fixture on one local host; no general workload claim",
            "Other local tests/corpus work ran concurrently; host load was uncontrolled",
            "No CPU affinity, thermal, filesystem cache, or dependency-download control",
            "No threshold tuning, warm-up exclusions, retries, or replacement repetitions",
            "Raw source/config, diffs, diagnostics, and absolute paths remain in local evidence",
        ],
        "runs": [],
    })
    for run in data["runs"]:
        record = {key: run[key] for key in (
            "repetition", "wall_seconds", "load_average_before", "load_average_after",
            "eligible", "exclusions", "baseline_max_seconds",
        )}
        error = run["error"]
        record["error"] = {
            "type": error["type"] if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", error["type"])
            else "unknown",
            "message_sha256": sha256(error.get("message", "").encode()),
            "traceback_sha256": sha256(error.get("traceback", "").encode()),
        } if error else None
        report = run["report"]
        if report:
            record["execution_summary"] = build_summary(report)
            record["comparison_duration_seconds"] = _duration(report.get("duration_seconds"))
            record["suite_timings_seconds"] = {
                section: [_duration(item.get("duration_seconds")) for item in report[section]]
                for section in ("baseline", "controls")
            }
            record["suite_timings_seconds"]["mutants"] = [
                {side: [_duration(item.get("duration_seconds")) for item in mutant[side]]
                 for side in ("old", "new")}
                for mutant in report["mutants"]
            ]
            record["versions"] = {}
            environment = report.get("environment", {})
            target = report.get("target_runtime", {})
            for name, value in {
                "supervisor_python": environment.get("python"),
                "target_python": target.get("python_version"),
                "target_pytest": target.get("pytest_version"),
                **environment.get("versions", {}),
            }.items():
                if name in {"supervisor_python", "target_python", "target_pytest", "testdelta",
                            "pytest", "cosmic-ray"} and isinstance(value, str) and re.fullmatch(
                                r"[A-Za-z0-9][A-Za-z0-9.+_-]*", value,
                            ):
                    record["versions"][name] = value
        public["runs"].append(record)
    return public


def write_artifact(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".testdelta/performance/raw.json")
    parser.add_argument("--public-output", type=Path)
    parser.add_argument("--wheel", type=Path, required=True, help="Installed wheel provenance")
    args = parser.parse_args()
    if args.output.resolve().is_relative_to((ROOT / "evidence").resolve()):
        parser.error("Raw reports belong outside evidence/; use --public-output for public summaries")
    if args.public_output and args.public_output.resolve() == args.output.resolve():
        parser.error("Raw and public output paths must be different")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("Choose a new output file; existing measurements are never overwritten")
    if args.public_output and args.public_output.exists():
        raise ValueError("Choose a new public output file; existing measurements are never overwritten")
    setup_started = time.monotonic()
    installed = implementation()
    with zipfile.ZipFile(args.wheel) as archive:
        packaged = {
            name.removeprefix("testdelta/"): sha256(archive.read(name))
            for name in archive.namelist() if name.startswith("testdelta/") and name.endswith(".py")
        }
    if installed != packaged:
        raise ValueError("The installed implementation does not match the supplied wheel")
    with tempfile.TemporaryDirectory(prefix="testdelta-runtime-") as temporary:
        root = Path(temporary)
        repo = root / "repo"
        data = {
            "schema_version": 1,
            "evidence_kind": "fixed_20_repetition_synthetic_runtime_measurement",
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "parameters": {
                "repetitions": REPETITIONS, "max_mutants": MAX_MUTANTS,
                "budget_seconds": BUDGET_SECONDS, "timeout_seconds": TIMEOUT_SECONDS,
                "baseline_limit_seconds": BASELINE_LIMIT_SECONDS,
                "percentile_method": "nearest rank: sorted durations[ceil(0.95*n)-1]",
                "ordering": "sequential; no warm-up or retries; all 20 attempts retained",
                "acceptance": "All 20 must have four passing baselines <=2s, exactly 10 planned "
                              "and completed mutants, complete observed loss, and p95 <=120s",
                "timed_scope": "make_plan plus compare, including Git reads, target provenance, "
                               "four baseline suites, actual Cosmic Ray generation, repeat pairs, "
                               "and final original-source controls",
                "excluded_setup": "dependency installation, Git fixture creation, wheel build, "
                                  "and evidence serialization",
            },
            "wheel": {"filename": args.wheel.name, "sha256": sha256(args.wheel.read_bytes())},
            "environment": environment(),
            "host": {"machine": platform.machine(), "processor": platform.processor(),
                     "logical_cpus": os.cpu_count()},
            "implementation_sha256": installed,
            "fixture": fixture(repo),
            "limitations": [
                "One synthetic four-test fixture on one local host; no general workload claim",
                "Other local tests/corpus work ran concurrently; host load was uncontrolled",
                "No CPU affinity, thermal, filesystem cache, or dependency-download control",
                "No threshold tuning, warm-up exclusions, retries, or replacement repetitions",
                "Raw local diagnostics retained; publication uses an allowlisted projection",
            ],
            "runs": [],
        }
        data["setup_seconds"] = time.monotonic() - setup_started
        def checkpoint(finished=False):
            data["summary"] = summary(data["runs"], finished)
            if finished:
                data["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            write_artifact(args.output, data)
            if args.public_output:
                write_artifact(args.public_output, public_artifact(data))

        checkpoint()
        for number in range(1, REPETITIONS + 1):
            before_load = load_average()
            started = time.monotonic()
            report, error = None, None
            try:
                plan, before, after = make_plan(repo, data["fixture"]["base_sha"],
                                                data["fixture"]["head_sha"])
                report, _ = compare(
                    plan, before, after, budget_seconds=BUDGET_SECONDS,
                    max_mutants=MAX_MUTANTS, timeout_seconds=TIMEOUT_SECONDS,
                    python_executable=sys.executable,
                )
            except Exception as exc:
                error = {"type": type(exc).__name__, "message": str(exc),
                         "traceback": traceback.format_exc()}
            duration = time.monotonic() - started
            excluded = exclusions(report, error)
            if implementation() != data["implementation_sha256"]:
                excluded.append("supervisor_implementation_changed")
            run = {
                "repetition": number, "wall_seconds": duration,
                "load_average_before": before_load, "load_average_after": load_average(),
                "eligible": not excluded, "exclusions": excluded,
                "baseline_max_seconds": max(
                    (r.get("duration_seconds", 0) for r in report["baseline"]), default=None,
                ) if report else None,
                "report": report, "error": error,
            }
            data["runs"].append(run)
            checkpoint()
            print(json.dumps({"repetition": number, "wall_seconds": round(duration, 3),
                              "eligible": run["eligible"], "exclusions": excluded}), flush=True)
        assert git(repo, "status", "--porcelain") == ""
        checkpoint(finished=True)
        print(json.dumps(data["summary"], indent=2), flush=True)
    return 0 if data["summary"]["status"] == "met" else 1


if __name__ == "__main__":
    raise SystemExit(main())
