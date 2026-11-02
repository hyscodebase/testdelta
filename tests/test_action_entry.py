"""Action adapter behavior and one real committed-fixture comparison."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from testdelta import action_entry


def inputs(tmp_path: Path, **changes: str) -> dict[str, str]:
    environment = {
        "TESTDELTA_INPUT_BASE": "HEAD~1",
        "TESTDELTA_INPUT_OUTPUT": str(tmp_path / "report"),
        "TESTDELTA_TARGET_PYTHON": sys.executable,
        "GITHUB_OUTPUT": str(tmp_path / "github-output"),
    }
    environment.update({"TESTDELTA_INPUT_" + key: value for key, value in changes.items()})
    return environment


def read_outputs(path: Path) -> dict[str, str]:
    result = {}
    lines = path.read_text(encoding="utf-8").split("\n")
    index = 0
    while index < len(lines) and lines[index]:
        name, delimiter = lines[index].split("<<", 1)
        index += 1
        start = index
        while lines[index] != delimiter:
            index += 1
        result[name] = "\n".join(lines[start:index])
        index += 1
    return result


def fake_compare(monkeypatch, environment, report, code):
    def compare(argv):
        directory = Path(next(item.removeprefix("--output=") for item in argv
                              if item.startswith("--output=")))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return code

    monkeypatch.setattr(action_entry, "cli_main", compare)
    return action_entry.main(environment)


def test_inputs_remain_individual_argv_values_and_never_execute_shell(tmp_path, monkeypatch):
    marker = tmp_path / "injected"
    attack = f"$(touch {marker}); `touch {marker}`\n--advisory"
    environment = inputs(tmp_path, REPO=attack, BASE="--help", HEAD=attack, CONFIG=attack)
    captured = []

    def compare(argv):
        captured.extend(argv)
        return 3

    monkeypatch.setattr(action_entry, "cli_main", compare)
    assert action_entry.main(environment) == 3
    assert "--repo=" + attack in captured
    assert "--base=--help" in captured
    assert "--head=" + attack in captured
    assert "--config=" + attack in captured
    assert "--advisory" not in captured
    assert not marker.exists()


def test_selected_python_preserves_virtual_environment_symlink(tmp_path):
    executable = tmp_path / "venv" / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.symlink_to(sys.executable)
    assert action_entry.resolve_python(str(executable)) == str(executable)
    assert action_entry.resolve_python(str(executable)) != str(executable.resolve())


@pytest.mark.parametrize(
    ("verdict", "complete", "advisory", "cli_code"),
    [
        ("no_loss_observed", True, "false", 0),
        ("loss_observed", True, "false", 1),
        ("loss_observed", True, "true", 0),
        ("loss_observed", False, "true", 2),
        ("inconclusive", False, "true", 2),
        ("unsupported_change", False, "true", 2),
    ],
)
def test_verdict_and_exit_code_are_preserved(
    tmp_path, monkeypatch, verdict, complete, advisory, cli_code,
):
    environment = inputs(tmp_path, ADVISORY=advisory)
    assert fake_compare(monkeypatch, environment, {
        "verdict": verdict, "complete": complete,
    }, cli_code) == cli_code
    assert read_outputs(Path(environment["GITHUB_OUTPUT"])) == {
        "verdict": verdict,
        "complete": str(complete).lower(),
        "report-path": str(tmp_path / "report" / "report.json"),
    }


@pytest.mark.parametrize("cli_code", [0, 2, 3])
def test_missing_report_is_never_clean_and_preserves_cli_failure(tmp_path, monkeypatch, cli_code):
    environment = inputs(tmp_path, ADVISORY="true")
    monkeypatch.setattr(action_entry, "cli_main", lambda argv: cli_code)
    assert action_entry.main(environment) == (cli_code or 3)
    assert read_outputs(Path(environment["GITHUB_OUTPUT"])) == {
        "verdict": "error", "complete": "false", "report-path": "",
    }


def test_existing_report_cannot_hide_an_invalid_comparison(tmp_path, monkeypatch):
    environment = inputs(tmp_path)
    output = tmp_path / "report"
    output.mkdir()
    (output / "report.json").write_text(
        json.dumps({"verdict": "no_loss_observed", "complete": True}), encoding="utf-8",
    )
    monkeypatch.setattr(action_entry, "cli_main", lambda argv: 0)
    assert action_entry.main(environment) == 3
    assert read_outputs(Path(environment["GITHUB_OUTPUT"]))["verdict"] == "error"


@pytest.mark.parametrize("report", [
    [], {"verdict": "no_loss_observed", "complete": "true"},
    {"verdict": "no_loss_observed\ncomplete=true", "complete": True},
])
def test_invalid_report_does_not_produce_clean_outputs(tmp_path, monkeypatch, report):
    environment = inputs(tmp_path)
    assert fake_compare(monkeypatch, environment, report, 0) == 3
    assert read_outputs(Path(environment["GITHUB_OUTPUT"]))["complete"] == "false"


def test_malformed_json_report_is_an_error(tmp_path, monkeypatch):
    environment = inputs(tmp_path)

    def compare(argv):
        report = tmp_path / "report" / "report.json"
        report.parent.mkdir()
        report.write_text("{invalid json", encoding="utf-8")
        return 0

    monkeypatch.setattr(action_entry, "cli_main", compare)
    assert action_entry.main(environment) == 3
    assert read_outputs(Path(environment["GITHUB_OUTPUT"]))["verdict"] == "error"


def test_argparse_exit_is_preserved_with_error_outputs(tmp_path, monkeypatch):
    environment = inputs(tmp_path, ADVISORY="true")

    def compare(argv):
        raise SystemExit(2)

    monkeypatch.setattr(action_entry, "cli_main", compare)
    assert action_entry.main(environment) == 2
    assert read_outputs(Path(environment["GITHUB_OUTPUT"]))["complete"] == "false"


@pytest.mark.parametrize(("report", "cli_code", "expected"), [
    ({"verdict": "no_loss_observed", "complete": True}, 3, 3),
    ({"verdict": "inconclusive", "complete": False}, 0, 2),
])
def test_exit_report_mismatch_cannot_become_success(tmp_path, monkeypatch, report, cli_code, expected):
    environment = inputs(tmp_path, ADVISORY="true")
    assert fake_compare(monkeypatch, environment, report, cli_code) == expected
    assert read_outputs(Path(environment["GITHUB_OUTPUT"]))["verdict"] == "error"


def test_output_path_newlines_cannot_add_outputs(tmp_path, monkeypatch):
    collision = "testdelta_collision"
    path = tmp_path / f"report\n{collision}\ncomplete=true\nverdict=forged"
    environment = inputs(tmp_path, OUTPUT=str(path))
    values = iter(["safe-verdict", "safe-complete", "collision", "safe-path"])
    monkeypatch.setattr(action_entry.uuid, "uuid4", lambda: SimpleNamespace(hex=next(values)))
    assert fake_compare(monkeypatch, environment, {
        "verdict": "no_loss_observed", "complete": True,
    }, 0) == 0
    assert read_outputs(Path(environment["GITHUB_OUTPUT"])) == {
        "verdict": "no_loss_observed", "complete": "true", "report-path": str(path / "report.json"),
    }


@pytest.mark.parametrize("advisory", ["yes", "true\nverdict=clean", "$(true)"])
def test_invalid_advisory_never_runs_the_cli(tmp_path, monkeypatch, advisory):
    def unexpected(argv):
        pytest.fail("Invalid action input reached the CLI")

    monkeypatch.setattr(action_entry, "cli_main", unexpected)
    assert action_entry.main(inputs(tmp_path, ADVISORY=advisory)) == 3


def test_native_wrapper_executes_real_fixture_and_keeps_incomplete_nonzero(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*arguments):
        return subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=TestDelta Action Test", "-c",
             "user.email=testdelta@example.invalid", "-c", "commit.gpgsign=false", "-c",
             "core.hooksPath=/dev/null", *arguments],
            check=True, capture_output=True, text=True, timeout=15,
        ).stdout.strip()

    git("init", "-q", "-b", "main")
    (repo / ".testdelta.toml").write_text(
        'source_modules = ["calc.py"]\ntest_paths = ["test_calc.py"]\n', encoding="utf-8",
    )
    (repo / "calc.py").write_text("def calculate(value):\n    return value + 1\n", encoding="utf-8")
    tests = repo / "test_calc.py"
    tests.write_text(
        "from calc import calculate\ndef test_value():\n    assert calculate(1) == 2\n",
        encoding="utf-8",
    )
    git("add", ".")
    git("commit", "-qm", "Passing original tests")
    base = git("rev-parse", "HEAD")
    tests.write_text("def test_invalid_baseline():\n    assert False\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "Invalid candidate test")
    environment = inputs(tmp_path, REPO=str(repo), BASE=base, ADVISORY="true", MAX_MUTANTS="1")
    # Keep an unrelated user process environment from appending test output to a job summary.
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert action_entry.main(environment) == 2
    report = json.loads((tmp_path / "report" / "report.json").read_text(encoding="utf-8"))
    assert report["reason"] == "baseline_not_valid"
    assert report["baseline"][-1]["status"] == "assertion_failure"
    assert report["target_runtime"]["python_executable"] == sys.executable
    assert read_outputs(Path(environment["GITHUB_OUTPUT"]))["complete"] == "false"
    assert git("status", "--porcelain") == ""


def test_composite_bootstrap_does_not_interpolate_inputs_into_shell():
    action = (Path(__file__).parents[1] / "action.yml").read_text(encoding="utf-8")
    script = action.split("      run: |\n", 1)[1]
    assert "${{" not in script
    assert "TESTDELTA_TARGET_PYTHON=target" in script
    assert '"-m", "venv"' in script
    assert 'tool_python, "-I", "-m", "pip"' in script
    assert 'tool_python, "-I", "-m", "testdelta.action_entry"' in script
    assert not any(key in script for key in ("GITHUB_TOKEN", "secrets.", "pull_request_target"))
