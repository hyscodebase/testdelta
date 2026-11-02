"""Evidence invariants exercised independently of subprocess and provider speed.

The fake runner observes materialized bytes, chooses results by test revision
and source content, and advances an explicit clock. It never supplies verdicts.
"""

from collections import defaultdict
from subprocess import TimeoutExpired
from types import SimpleNamespace

import pytest

import testdelta.compare as engine
from testdelta.git_inputs import digest

SOURCE = b"def calculate(value):\n    return value + 1\n"
OLD_TEST = b"# old tests\n"
NEW_TEST = b"# new tests\n"
RUNTIME = {"python_version": "3.test", "python_executable": "/test/python", "pytest_version": "test"}


def test_diff_preserves_missing_final_newline_boundaries_and_hash():
    patch = engine.unified_diff(b"assert value == 2", b"assert True", "tests/test_calc.py")
    assert "-assert value == 2\n\\ No newline at end of file\n+assert True\n" in patch["diff"]
    assert patch["sha256"] == digest(patch["diff"].encode())
    limited = engine.unified_diff(b"assert value == 2", b"assert True", "tests/test_calc.py", 10)
    assert limited["truncated"] is True
    assert limited["sha256"] == patch["sha256"]


class Scenario:
    """Select execution evidence using actual workspace contents, not call order."""

    def __init__(self, monkeypatch, mutant_count=1, duration=0.1):
        self.now = 0.0
        self.duration = duration
        self.runs = []
        self.counts = defaultdict(int)
        self.generation_calls = []
        self.before = {
            "calc.py": SOURCE, "tests/test_changed.py": OLD_TEST,
            "tests/test_deleted.py": b"# existed at base\n", "helper.py": b"VALUE = 1\n",
        }
        self.after = {
            "calc.py": SOURCE, "tests/test_changed.py": NEW_TEST,
            "tests/test_added.py": b"# added at head\n", "helper.py": b"VALUE = 1\n",
        }
        self.plan = {
            "supported": True, "unsupported_changes": [],
            "test_files": ["tests/test_changed.py", "tests/test_deleted.py", "tests/test_added.py"],
            "manifest": {"source_modules": ["calc.py"], "test_paths": ["tests"]},
            "source_hashes": {"calc.py": digest(SOURCE)},
        }
        self.mutants = []
        for index in range(mutant_count):
            mutated = f"def calculate(value):\n    return value + {index + 2}\n"
            self.mutants.append({
                "id": f"m{index}", "path": "calc.py", "line": 2,
                "operator": "test/add", "mutated_source": mutated,
                "mutated_sha256": digest(mutated.encode()), "original_sha256": digest(SOURCE),
                "replacement_description": "Replace one constant",
            })
        self.decide = lambda side, mutation, attempt: "assertion_failure" if mutation and side == "old" else "pass"
        self.reaches = lambda side, mutation, attempt: [2]
        monkeypatch.setattr(engine, "time", SimpleNamespace(monotonic=lambda: self.now))
        monkeypatch.setattr(engine, "environment", lambda: {"test_environment": True})
        monkeypatch.setattr(engine, "target_runtime", lambda executable=None: dict(RUNTIME))
        monkeypatch.setattr(engine, "generate_bounded", self.generate)
        monkeypatch.setattr(engine, "run_pytest", self.execute)

    def generate(self, workspace, source_modules, max_mutants, timeout_seconds):
        self.generation_calls.append((source_modules, max_mutants, timeout_seconds))
        assert (workspace / "calc.py").read_bytes() == SOURCE
        return self.mutants[:max_mutants]

    def execute(self, workspace, test_paths, timeout_seconds, expected_source_hashes, python_executable=None):
        files = {p.relative_to(workspace).as_posix(): p.read_bytes() for p in workspace.rglob("*") if p.is_file()}
        side = "old" if files["tests/test_changed.py"] == OLD_TEST else "new"
        mutation = next((m["id"] for m in self.mutants if files["calc.py"] == m["mutated_source"].encode()), None)
        self.counts[(side, mutation)] += 1
        attempt = self.counts[(side, mutation)]
        assert expected_source_hashes == {"calc.py": digest(files["calc.py"])}
        assert timeout_seconds > 0
        assert test_paths == ["tests"]
        self.runs.append({"side": side, "mutation": mutation, "attempt": attempt, "files": files,
                          "hashes": dict(expected_source_hashes), "timeout": timeout_seconds})
        self.now += self.duration
        status = self.decide(side, mutation, attempt)
        return {
            "status": status, "duration_seconds": self.duration, "runtime": dict(RUNTIME),
            "reached_lines": {"calc.py": self.reaches(side, mutation, attempt)},
            "assertion_failure_nodes": ["tests/test_changed.py::test_value"] if status == "assertion_failure" else [],
        }

    def compare(self, **kwargs):
        return engine.compare(self.plan, self.before, self.after, **kwargs)


@pytest.mark.parametrize("status", ["assertion_failure", "collection_error", "fixture_error", "runtime_error", "timeout", "not_executed", "invalid_evidence"])
@pytest.mark.parametrize("failed_side,failed_attempt", [("old", 1), ("new", 1), ("old", 2), ("new", 2)])
def test_any_invalid_baseline_stops_before_mutations(monkeypatch, status, failed_side, failed_attempt):
    scenario = Scenario(monkeypatch)
    scenario.decide = lambda side, mutation, attempt: status if (side, attempt) == (failed_side, failed_attempt) else "pass"
    report, bundle = scenario.compare()
    assert report["verdict"] == "inconclusive"
    assert report["complete"] is False
    assert report["baseline"][-1]["status"] == status
    assert report["witnesses"] == report["mutants"] == report["controls"] == []
    assert scenario.generation_calls == []
    assert bundle["mutations"] == []


@pytest.mark.parametrize("side", ["old", "new"])
@pytest.mark.parametrize("failure", ["assertion_failure", "timeout", "invalid_evidence"])
def test_failed_final_control_never_confirms_a_repeated_witness(monkeypatch, side, failure):
    scenario = Scenario(monkeypatch)
    normal = scenario.decide
    scenario.decide = lambda actual_side, mutation, attempt: failure if actual_side == side and mutation is None and attempt == 3 else normal(actual_side, mutation, attempt)
    report, _ = scenario.compare()
    assert report["complete"] is False
    assert report["verdict"] == "inconclusive"
    assert report["reason"] == "final_controls_not_valid"
    assert len(report["witnesses"]) == 1
    assert report["witnesses"][0]["confirmation"] == "unconfirmed_control"


@pytest.mark.parametrize("later_status", ["timeout", "fixture_error", "not_executed", "invalid_evidence"])
def test_later_incomplete_mutant_preserves_only_separate_controlled_witness(monkeypatch, later_status):
    scenario = Scenario(monkeypatch, mutant_count=2)
    normal = scenario.decide
    scenario.decide = lambda side, mutation, attempt: later_status if mutation == "m1" else normal(side, mutation, attempt)
    report, _ = scenario.compare()
    assert report["complete"] is False
    assert report["verdict"] == "incomplete_with_witnesses"
    assert [w["id"] for w in report["witnesses"]] == ["m0"]
    assert report["witnesses"][0]["confirmation"] == "three_pairs_and_final_controls"
    assert all(result["status"] == "pass" for result in report["controls"])


@pytest.mark.parametrize("failure", ["timeout", "runtime_error", "not_executed"])
def test_incomplete_scope_without_a_prior_witness_is_never_clean(monkeypatch, failure):
    scenario = Scenario(monkeypatch)
    scenario.decide = lambda side, mutation, attempt: failure if mutation and side == "old" else "pass"
    report, _ = scenario.compare()
    assert report["complete"] is False
    assert report["verdict"] == "inconclusive"
    assert report["witnesses"] == []
    assert all(result["status"] == "pass" for result in report["controls"])


def test_generation_timeout_runs_reserved_controls_but_does_not_claim_clean(monkeypatch):
    scenario = Scenario(monkeypatch)

    def timed_out(*args):
        raise TimeoutExpired("mutation provider", 1)

    monkeypatch.setattr(engine, "generate_bounded", timed_out)
    report, bundle = scenario.compare()
    assert report["complete"] is False
    assert report["verdict"] == "inconclusive"
    assert report["reason"] == "mutation_generation_budget_exhausted"
    assert len(report["controls"]) == 2
    assert all(result["status"] == "pass" for result in report["controls"])
    assert report["mutants"] == report["witnesses"] == bundle["mutations"] == []


def test_budget_exhaustion_after_witness_reserves_controls_without_claiming_full_scope(monkeypatch):
    scenario = Scenario(monkeypatch, mutant_count=2, duration=1)
    report, _ = scenario.compare(budget_seconds=13)
    assert scenario.now == 12
    assert report["complete"] is False
    assert report["verdict"] == "incomplete_with_witnesses"
    assert report["mutants_completed"] == 1 < report["mutants_planned"]
    assert report["reason"] == "total_budget_exhausted"
    assert report["witnesses"][0]["confirmation"] == "three_pairs_and_final_controls"
    assert not any(run["mutation"] == "m1" for run in scenario.runs)


def test_unstable_repetition_is_not_a_witness_or_clean_result(monkeypatch):
    scenario = Scenario(monkeypatch)
    normal = scenario.decide
    scenario.decide = lambda side, mutation, attempt: "pass" if side == "old" and mutation and attempt == 2 else normal(side, mutation, attempt)
    report, _ = scenario.compare()
    assert report["complete"] is False
    assert report["verdict"] == "inconclusive"
    assert report["witnesses"] == []


def test_assertion_without_mutation_line_reach_is_not_a_kill(monkeypatch):
    scenario = Scenario(monkeypatch)
    scenario.reaches = lambda side, mutation, attempt: [1]
    report, _ = scenario.compare()
    assert report["complete"] is False
    assert report["verdict"] == "inconclusive"
    assert report["witnesses"] == []


def test_new_tests_can_lose_all_source_reach_and_still_prove_lost_detection(monkeypatch):
    scenario = Scenario(monkeypatch)
    scenario.reaches = lambda side, mutation, attempt: [2] if side == "old" else []
    report, _ = scenario.compare()
    assert report["verdict"] == "loss_observed"
    assert report["complete"] is True
    assert len(report["witnesses"]) == 1


def test_materialized_pairs_use_identical_production_bytes_and_correct_added_deleted_tests(monkeypatch):
    scenario = Scenario(monkeypatch)
    before_copy, after_copy = dict(scenario.before), dict(scenario.after)
    report, bundle = scenario.compare()
    assert report["complete"] is True
    assert scenario.before == before_copy and scenario.after == after_copy
    for run in scenario.runs:
        files = run["files"]
        assert files["helper.py"] == before_copy["helper.py"] == after_copy["helper.py"]
        if run["side"] == "old":
            assert files["tests/test_changed.py"] == OLD_TEST
            assert "tests/test_deleted.py" in files and "tests/test_added.py" not in files
        else:
            assert files["tests/test_changed.py"] == NEW_TEST
            assert "tests/test_deleted.py" not in files and "tests/test_added.py" in files
        expected = SOURCE if run["mutation"] is None else bundle["mutations"][0]["mutated_source"].encode()
        assert files["calc.py"] == expected
        assert run["hashes"] == {"calc.py": digest(expected)}


def test_no_mutations_produces_inconclusive_not_clean(monkeypatch):
    scenario = Scenario(monkeypatch, mutant_count=0)
    report, _ = scenario.compare()
    assert report["verdict"] == "inconclusive"
    assert report["complete"] is False
    assert report["reason"] == "no_supported_mutations"
