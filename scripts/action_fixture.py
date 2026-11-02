"""Trusted local integration fixtures for the composite Action and installed wheel.

This stdlib-only harness does not import TestDelta from the checkout. It creates
new local repositories and never writes or sends anything to GitHub.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

SOURCE = "def calculate(value):\n    return value + 1\n"
STRONG = "from calc import calculate\ndef test_value():\n    assert calculate(1) == 2\n"
WEAK = "from calc import calculate\ndef test_value():\n    assert calculate(1) >= 0\n"
INVALID = "def test_invalid_baseline():\n    assert False\n"


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=TestDelta CI Fixture", "-c",
         "user.email=testdelta-ci@example.invalid", "-c", "commit.gpgsign=false", "-c",
         "core.hooksPath=/dev/null", *arguments],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout.strip()


def repository(root: Path, candidate: str) -> dict[str, str]:
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "calc.py").write_text(SOURCE, encoding="utf-8")
    tests = root / "test_calc.py"
    tests.write_text(STRONG, encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "Passing original tests")
    base = git(root, "rev-parse", "HEAD")
    tests.write_text(candidate, encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "Change only the tests")
    assert git(root, "diff", "--name-only", base, "HEAD") == "test_calc.py"
    return {"repo": str(root), "base": base, "head": git(root, "rev-parse", "HEAD")}


def fingerprint(python: str) -> dict:
    result = subprocess.run(
        [python, "-I", "-c",
         "import importlib.metadata as m,json,sys,pytest; "
         "print(json.dumps(dict(python_executable=sys.executable,"
         "pytest_version=pytest.__version__,packages=sorted("
         "(d.metadata['Name'].lower().replace('_','-'),d.version) "
         "for d in m.distributions()))))"],
        check=True, capture_output=True, text=True, timeout=15,
    )
    return json.loads(result.stdout)


def create(root: Path, config: Path, target_python: str) -> dict:
    root = root.absolute()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "state.json").exists() or (root / "lost").exists():
        raise ValueError("Use a new fixture directory; existing fixtures are never overwritten")
    config.parent.mkdir(parents=True, exist_ok=True)
    if config.exists():
        raise ValueError("The external fixture config already exists")
    config.write_text(
        'source_modules = ["calc.py"]\ntest_paths = ["test_calc.py"]\n', encoding="utf-8",
    )
    target_python = os.path.abspath(target_python)
    state = {
        "lost": repository(root / "lost", WEAK),
        "invalid": repository(root / "invalid", INVALID),
        "config": str(config.absolute()),
        "target": fingerprint(target_python),
    }
    assert not config.absolute().is_relative_to(root / "lost")
    (root / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        values = {
            "lost-repo": state["lost"]["repo"], "lost-base": state["lost"]["base"],
            "invalid-repo": state["invalid"]["repo"], "invalid-base": state["invalid"]["base"],
            "config": str(config), "target-python": target_python,
        }
        with open(output, "a", encoding="utf-8") as stream:
            for key, value in values.items():
                if "\n" in value or "\r" in value:
                    raise ValueError("Fixture output paths must be single-line")
                stream.write(f"{key}={value}\n")
    return state


def load(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def assert_loss(report: dict) -> None:
    assert report["verdict"] == "loss_observed", report
    assert report["complete"] is True, report
    assert report["mutants_completed"] == report["mutants_planned"] > 0
    assert report["witnesses"], report
    assert all(w["confirmation"] == "three_pairs_and_final_controls" for w in report["witnesses"])
    assert all(r["status"] == "pass" for r in report["baseline"] + report["controls"])


def verify_native(root: Path) -> None:
    root = root.absolute()
    state = load(root, "state.json")
    assert os.environ["LOSS_OUTCOME"] == "success"
    assert os.environ["LOSS_VERDICT"] == "loss_observed"
    assert os.environ["LOSS_COMPLETE"] == "true"
    assert os.environ["LOSS_REPORT"] == str(root / "lost-report" / "report.json")
    assert os.environ["INVALID_OUTCOME"] == "failure"
    assert os.environ["INVALID_VERDICT"] == "inconclusive"
    assert os.environ["INVALID_COMPLETE"] == "false"
    assert os.environ["INVALID_REPORT"] == str(root / "invalid-report" / "report.json")
    lost = load(root, "lost-report/report.json")
    invalid = load(root, "invalid-report/report.json")
    assert_loss(lost)
    assert invalid["verdict"] == "inconclusive" and invalid["complete"] is False, invalid
    assert invalid["reason"] == "baseline_not_valid", invalid
    assert invalid["baseline"][-1]["status"] == "assertion_failure", invalid
    before = state["target"]
    assert before["pytest_version"] == "8.4.2"
    assert fingerprint(before["python_executable"]) == before, "Project environment was modified"
    assert not {"testdelta", "cosmic-ray"}.intersection(name for name, _ in before["packages"])
    for report in (lost, invalid):
        assert report["plan"]["manifest_origin"] == "external"
        assert report["target_runtime"]["python_executable"] == before["python_executable"]
        assert report["target_runtime"]["pytest_version"] == "8.4.2"
        assert report["environment"]["versions"]["pytest"] != "8.4.2"
        runs = report["baseline"] + report["controls"]
        for mutant in report["mutants"]:
            runs += mutant["old"] + mutant["new"]
        for run in runs:
            assert run["runtime"]["python_executable"] == before["python_executable"]
            assert run["runtime"]["pytest_version"] == "8.4.2"
    for case in ("lost", "invalid"):
        repo = Path(state[case]["repo"])
        assert not (repo / ".testdelta.toml").exists()
        assert (repo / "calc.py").read_text(encoding="utf-8") == SOURCE
        assert git(repo, "status", "--porcelain") == ""
    print("Native Action outputs, advisory failure, and target interpreter isolation verified")


def verify_wheel(root: Path, tool_python: str) -> None:
    root = root.absolute()
    tool_python = os.path.abspath(tool_python)
    state = create(root, root / "external.toml", tool_python)
    report_directory = root / "report"
    # Run away from the checkout with isolated Python imports to exercise the wheel.
    command = [tool_python, "-I", "-m", "testdelta", "compare", "--repo", state["lost"]["repo"],
               "--base", state["lost"]["base"], "--config", state["config"],
               "--output", str(report_directory), "--max-mutants", "2", "--budget-seconds", "120"]
    result = subprocess.run(command, cwd=root, timeout=180)
    assert result.returncode == 1, result.returncode
    report = load(report_directory, "report.json")
    assert_loss(report)
    witness = report["witnesses"][0]["id"]
    Path(state["config"]).unlink()
    replay = subprocess.run(
        [tool_python, "-I", "-m", "testdelta", "replay", str(report_directory), "--witness", witness,
         "--repo", state["lost"]["repo"], "--output", str(root / "replay")],
        cwd=root, timeout=180,
    )
    assert replay.returncode == 1, replay.returncode
    repeated = load(root, "replay/report.json")
    assert_loss(repeated)
    assert repeated["witnesses"][0]["id"] == witness
    assert repeated["plan"]["source_hashes"] == report["plan"]["source_hashes"]
    assert repeated["plan"]["manifest_hash"] == report["plan"]["manifest_hash"]
    print("Installed wheel comparison and replay with recorded external policy verified")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("create")
    make.add_argument("--root", type=Path, required=True)
    make.add_argument("--config", type=Path, required=True)
    make.add_argument("--target-python", required=True)
    native = commands.add_parser("verify-native")
    native.add_argument("--root", type=Path, required=True)
    wheel = commands.add_parser("verify-wheel")
    wheel.add_argument("--root", type=Path, required=True)
    wheel.add_argument("--tool-python", required=True)
    args = parser.parse_args()
    if args.command == "create":
        create(args.root, args.config, args.target_python)
    elif args.command == "verify-native":
        verify_native(args.root)
    else:
        verify_wheel(args.root, args.tool_python)


if __name__ == "__main__":
    main()
