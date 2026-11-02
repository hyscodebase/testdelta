"""Real two-revision Git comparisons through the CLI and Cosmic Ray provider."""

import hashlib
import json
import py_compile
import subprocess
from pathlib import Path

import pytest

from testdelta.cli import main
from testdelta.git_inputs import make_plan

SOURCE = "def calculate(value):\n    return value + 1\n"
STRONG = "from calc import calculate\ndef test_answer():\n    assert calculate(1) == 2\n"
WEAK = "from calc import calculate\ndef test_answer():\n    assert calculate(1) >= 0\n"
REFACTORED = (
    "from calc import calculate\n"
    "def test_answer_after_refactor():\n"
    "    expected = 2\n"
    "    actual = calculate(1)\n"
    "    assert actual == expected\n"
)


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "user.name=TestDelta Integration",
            "-c", "user.email=testdelta-integration@example.invalid",
            "-c", "commit.gpgsign=false",
            "-c", "core.hooksPath=/dev/null",
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def repository(root: Path, candidate: str, *, unchecked_cache: bool = False) -> tuple[Path, str, str]:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "tests").mkdir()
    (repo / ".testdelta.toml").write_text(
        'source_modules = ["calc.py"]\ntest_paths = ["tests"]\n', encoding="utf-8"
    )
    (repo / "calc.py").write_text(SOURCE, encoding="utf-8")
    if unchecked_cache:
        # A relative co_filename is valid for ordinary compilation and otherwise
        # appears to originate in each temporary workspace despite stale code.
        py_compile.compile(
            str(repo / "calc.py"),
            dfile="calc.py",
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        )
    tests = repo / "tests" / "test_calc.py"
    tests.write_text(STRONG, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Strong baseline tests")
    base = git(repo, "rev-parse", "HEAD")
    tests.write_text(candidate, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Change only the tests")
    return repo, base, git(repo, "rev-parse", "HEAD")


def compare_cli(repo: Path, base: str, output: Path, *extra: str) -> tuple[int, dict]:
    code = main([
        "compare", "--repo", str(repo), "--base", base,
        "--max-mutants", "3", "--timeout-seconds", "15", "--budget-seconds", "120",
        "--output", str(output), *extra,
    ])
    return code, json.loads((output / "report.json").read_text(encoding="utf-8"))


def test_git_plan_and_cli_find_confirmed_same_byte_loss(tmp_path):
    repo, base, head = repository(tmp_path, WEAK)
    plan, before, after = make_plan(repo, base)
    assert plan["supported"] is True
    assert plan["base_sha"] == base
    assert plan["head_sha"] == head
    assert plan["changed_files"] == ["tests/test_calc.py"]
    assert before["calc.py"] == after["calc.py"] == SOURCE.encode()
    code, report = compare_cli(repo, base, tmp_path / "report")
    assert code == 1, report
    assert report["verdict"] == "loss_observed", report
    assert report["complete"] is True
    assert report["mutants_completed"] == report["mutants_planned"] == 3
    assert len(report["witnesses"]) == 3
    assert all(item["status"] == "pass" for item in report["baseline"] + report["controls"])
    for witness in report["witnesses"]:
        assert witness["confirmation"] == "three_pairs_and_final_controls"
        assert witness["old_outcomes"] == ["killed"] * 3
        assert witness["new_outcomes"] == ["survived"] * 3
    for mutant in report["mutants"]:
        expected = {"calc.py": mutant["mutated_sha256"]}
        for run in mutant["old"] + mutant["new"]:
            assert run["source_hashes_before"] == run["source_hashes_after"] == expected
    assert (repo / "calc.py").read_text() == SOURCE
    assert git(repo, "status", "--porcelain") == ""
    assert report["test_diffs"][0]["path"] == "tests/test_calc.py"
    assert "-    assert calculate(1) == 2" in report["test_diffs"][0]["diff"]
    assert all(m["diff"].startswith("--- old/calc.py") for m in report["mutants"])
    for run in report["baseline"] + report["controls"]:
        assert run["started_at_utc"] <= run["finished_at_utc"]


def test_external_manifest_replay_survives_deleted_original_config(tmp_path, monkeypatch):
    repo, base, head = repository(tmp_path, WEAK)
    # Rebuild the two commits without a tracked manifest, like a pre-existing PR.
    manifest = (repo / ".testdelta.toml").read_bytes().replace(b"\n", b"\r\n")
    git(repo, "checkout", "--orphan", "external")
    git(repo, "rm", "--cached", ".testdelta.toml")
    (repo / ".testdelta.toml").unlink()
    (repo / "tests/test_calc.py").write_text(STRONG)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Baseline without tool config")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "tests/test_calc.py").write_text(WEAK)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Existing test-only change")
    external = tmp_path / "outside.toml"
    external.write_bytes(manifest)
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "external-report"
    code, report = compare_cli(repo, base, output, "--config", "outside.toml")
    assert code == 1, report
    assert report["plan"]["manifest_origin"] == "external"
    assert report["plan"]["manifest_hash"] == hashlib.sha256(manifest).hexdigest()
    external.unlink()
    witness = report["witnesses"][0]["id"]
    assert main(["replay", str(output), "--witness", witness, "--repo", str(repo),
                 "--output", str(tmp_path / "external-replay")]) == 1
    assert git(repo, "status", "--porcelain") == ""


def test_init_external_config_does_not_modify_repo_or_overwrite_symlink(tmp_path):
    repo = tmp_path / "empty-repo"
    repo.mkdir()
    config = tmp_path / "config.toml"
    args = ["init", "--repo", str(repo), "--source", "calc.py", "--tests", "tests",
            "--output", str(config)]
    assert main(args) == 0
    assert list(repo.iterdir()) == []
    assert main(args) == 3
    config.unlink()
    config.symlink_to(tmp_path / "missing")
    assert main(args) == 3


def test_legitimate_test_refactor_retains_all_selected_kills(tmp_path):
    repo, base, _head = repository(tmp_path, REFACTORED)
    code, report = compare_cli(repo, base, tmp_path / "report")
    assert code == 0, report
    assert report["verdict"] == "no_loss_observed"
    assert report["complete"] is True
    assert report["witnesses"] == []
    assert [m["outcome"] for m in report["mutants"]] == ["retained_kill"] * 3


def test_tracked_unchecked_bytecode_cannot_hide_mutations(tmp_path):
    repo, base, _head = repository(tmp_path, WEAK, unchecked_cache=True)
    assert any(name.endswith(".pyc") for name in git(repo, "ls-files").splitlines())
    plan, _before, after = make_plan(repo, base)
    assert plan["supported"] is True
    assert plan["changed_files"] == ["tests/test_calc.py"]
    assert any(name.endswith(".pyc") for name in after)
    code, report = compare_cli(repo, base, tmp_path / "report")
    assert code == 1, report
    assert report["verdict"] == "loss_observed", report
    assert report["complete"] is True
    assert len(report["witnesses"]) == 3
    assert [m["outcome"] for m in report["mutants"]] == ["lost_kill"] * 3


@pytest.mark.parametrize(
    ("candidate", "expected_status"),
    [
        ("from calc import calculate\ndef test_answer():\n    assert calculate(1) == 999\n", "assertion_failure"),
        ("import missing_testdelta_integration_dependency\ndef test_answer():\n    pass\n", "collection_error"),
        ("# This file intentionally contains no tests.\n", "not_executed"),
    ],
    ids=["invalid-baseline", "import-failure", "empty-suite"],
)
def test_invalid_baselines_are_inconclusive_even_with_advisory(tmp_path, candidate, expected_status):
    repo, base, _head = repository(tmp_path, candidate)
    code, report = compare_cli(repo, base, tmp_path / "report", "--advisory")
    assert code == 2, report
    assert report["verdict"] == "inconclusive"
    assert report["complete"] is False
    assert report["reason"] == "baseline_not_valid"
    assert report["baseline"][-1]["status"] == expected_status
    assert report["mutants"] == []
    assert report["witnesses"] == []


def test_advisory_converts_only_completed_loss_and_does_not_mask_input_error(tmp_path, capsys):
    repo, base, _head = repository(tmp_path, WEAK)
    code, report = compare_cli(repo, base, tmp_path / "report", "--advisory")
    assert code == 0
    assert report["verdict"] == "loss_observed"
    assert report["complete"] is True
    assert report["witnesses"]
    capsys.readouterr()
    code = main([
        "compare", "--repo", str(repo), "--base", "missing-revision",
        "--output", str(tmp_path / "error-report"), "--advisory",
    ])
    assert code == 3
    assert "could not complete" in capsys.readouterr().err


def test_replay_uses_retained_commits_and_checks_bundle_integrity_and_environment(tmp_path, capsys):
    repo, base, _head = repository(tmp_path, WEAK)
    output = tmp_path / "report"
    code, report = compare_cli(repo, base, output)
    assert code == 1, report
    witness = report["witnesses"][0]
    capsys.readouterr()
    replay_output = tmp_path / "replay"
    code = main([
        "replay", str(output), "--witness", witness["id"],
        "--repo", str(repo), "--output", str(replay_output),
    ])
    assert code == 1
    replayed = json.loads((replay_output / "report.json").read_text())
    assert replayed["verdict"] == "loss_observed"
    assert replayed["complete"] is True
    assert len(replayed["witnesses"]) == 1
    assert replayed["witnesses"][0]["id"] == witness["id"]
    assert replayed["witnesses"][0]["mutated_sha256"] == witness["mutated_sha256"]
    assert replayed["environment_hash"] == report["environment_hash"]
    assert replayed["plan"]["base_sha"] == report["plan"]["base_sha"]
    assert replayed["plan"]["head_sha"] == report["plan"]["head_sha"]

    # A byte edit without an updated checksum must be rejected before any replay.
    bundle_path = output / "bundle.json"
    original_bytes = bundle_path.read_bytes()
    bundle_path.write_bytes(original_bytes + b" ")
    capsys.readouterr()
    code = main(["replay", str(output), "--witness", witness["id"], "--repo", str(repo)])
    assert code == 3
    assert "checksum mismatch" in capsys.readouterr().err.lower()

    # A self-consistent bundle from a different environment is also unsupported.
    altered = json.loads(original_bytes)
    altered["environment"]["python"] = "0.0.0-different-environment"
    altered_bytes = json.dumps(altered).encode()
    bundle_path.write_bytes(altered_bytes)
    (output / "bundle.sha256").write_text(hashlib.sha256(altered_bytes).hexdigest() + "\n")
    code = main(["replay", str(output), "--witness", witness["id"], "--repo", str(repo)])
    assert code == 3
    assert "environment differs" in capsys.readouterr().err.lower()
