"""Share summaries retain finite outcomes without copying private evidence."""

import copy
import json

import pytest

from testdelta.export import build_summary, export_summary


@pytest.fixture
def private_report():
    run = {
        "status": "assertion_failure", "side": "old", "ran": ["PRIVATE_NODE_ID"],
        "collected": ["PRIVATE_NODE_ID"], "assertion_failure_nodes": ["PRIVATE_NODE_ID"],
        "stdout": "PRIVATE_STDOUT", "stderr": "PRIVATE_STDERR",
        "runtime_errors": [{"detail": "PRIVATE_TRACEBACK"}],
        "runtime": {"python_executable": "/home/private/python"},
        "observed_source_origin": {"calc.py": "/home/private/calc.py"},
    }
    mutation = {
        "id": "cr-0123456789abcdef", "path": "src/calc.py", "line": 2,
        "original_sha256": "a" * 64, "mutated_sha256": "b" * 64,
        "diff": "PRIVATE_MUTANT_DIFF", "diff_sha256": "c" * 64, "diff_truncated": True,
        "original_source": "PRIVATE_ORIGINAL_SOURCE", "mutated_source": "PRIVATE_MUTATED_SOURCE",
        "replacement_description": "PRIVATE_REPLACEMENT", "outcome": "lost_kill",
        "old": [run] * 3, "new": [{"status": "pass", "stdout": "PRIVATE_NEW_STDOUT"}] * 3,
        "confirmation": "three_pairs_and_final_controls",
        "old_outcomes": ["killed"] * 3, "new_outcomes": ["survived"] * 3,
        "old_failure_nodes": ["PRIVATE_NODE_ID"],
    }
    return {
        "schema_version": "0.1", "verdict": "loss_observed", "complete": True,
        "mutants_planned": 1, "mutants_completed": 1,
        "plan": {
            "repo": "/home/private/repo", "base_sha": "1" * 40, "head_sha": "2" * 40,
            "requested_base_sha": "3" * 40, "manifest_hash": "4" * 64,
            "manifest_origin": "external", "manifest_snapshot": {"text": "PRIVATE_CONFIG"},
            "manifest": {"source_modules": ["PRIVATE_CONFIG_SELECTION"]},
            "source_hashes": {"src/calc.py": "a" * 64, "src/deleted.py": None},
            "test_hashes": {"tests/test_calc.py": {"old": "5" * 64, "new": "6" * 64}},
            "unknown_future_field": {"secret": "PRIVATE_PLAN_EXTRA"},
        },
        "environment_hash": "7" * 64,
        "environment": {"platform": "PRIVATE_PLATFORM"},
        "target_runtime": {"python_executable": "/home/private/python"},
        "baseline": [dict(run, status="pass")], "controls": [dict(run, status="pass")],
        "mutants": [mutation], "witnesses": [mutation],
        "test_diffs": [{"path": "tests/test_calc.py", "diff": "PRIVATE_TEST_DIFF",
                        "sha256": "8" * 64, "truncated": False}],
        "reason": "PRIVATE_FREE_REASON", "limitations": ["PRIVATE_FREE_LIMITATION"],
        "limits": {"budget_seconds": 120, "max_mutants": 1, "timeout_seconds": 15,
                   "secret": "PRIVATE_LIMIT_EXTRA"},
        "unknown_future_field": {"stdout": "PRIVATE_UNKNOWN"},
    }


def test_local_export_uses_allowlist_without_modifying_canonical_evidence(tmp_path, private_report):
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    raw = json.dumps(private_report).encode()
    (report_dir / "report.json").write_bytes(raw)
    (report_dir / "bundle.json").write_text("PRIVATE_BUNDLE_NOT_NEEDED")
    output = tmp_path / "share.json"

    summary = export_summary(report_dir, output)

    assert json.loads(output.read_text()) == summary
    assert (report_dir / "report.json").read_bytes() == raw
    assert "PRIVATE_" not in output.read_text()
    assert "/home/private" not in output.read_text()
    assert summary["export_kind"] == "sanitized_summary"
    assert summary["verdict"] == "loss_observed" and summary["complete"]
    assert summary["plan"]["base_sha"] == "1" * 40
    assert summary["plan"]["source_hashes"] == {"src/calc.py": "a" * 64, "src/deleted.py": None}
    assert summary["plan"]["test_hashes"]["tests/test_calc.py"]["new"] == "6" * 64
    assert summary["mutants"][0]["old"] == [{
        "status": "assertion_failure", "side": "old", "ran_count": 1, "collected_count": 1,
        "assertion_failure_nodes_count": 1,
    }] * 3
    assert summary["witnesses"][0]["confirmation"] == "three_pairs_and_final_controls"
    assert summary["test_diffs"] == [{
        "path": "tests/test_calc.py", "sha256": "8" * 64, "truncated": False,
    }]
    assert "diff" not in summary["mutants"][0]
    assert "diff_sha256" in summary["mutants"][0]
    assert any("no proof of test equivalence" in value for value in summary["limitations"])


def test_export_refuses_to_overwrite_existing_output(tmp_path, private_report):
    (tmp_path / "report.json").write_text(json.dumps(private_report))
    output = tmp_path / "share.json"
    output.write_text("keep existing content")
    with pytest.raises(FileExistsError):
        export_summary(tmp_path, output)
    assert output.read_text() == "keep existing content"


def test_allowlist_rejects_absolute_paths_traversal_and_injected_value_fields(private_report):
    report = copy.deepcopy(private_report)
    paths = ["/home/PRIVATE/path.py", "C:/PRIVATE/path.py", r"C:\PRIVATE\path.py",
             "../PRIVATE/path.py", "safe/../../PRIVATE/path.py", "PRIVATE\nsource.py"]
    report["plan"]["source_hashes"].update({path: "a" * 64 for path in paths})
    report["plan"]["test_hashes"].update({path: {"old": "a" * 64} for path in paths})
    report["mutants"][0].update(path=paths[0], id="PRIVATE_ID", outcome="PRIVATE_OUTCOME")
    report["mutants"][0]["old"][0]["status"] = "PRIVATE_STATUS"
    report["plan"]["manifest_hash"] = "PRIVATE_HASH"
    report["plan"]["head_sha"] = "/home/PRIVATE/revision"
    report["test_diffs"] += [{"path": path, "sha256": "a" * 64} for path in paths]
    report["reason"] = paths

    summary = build_summary(report)

    assert "PRIVATE" not in json.dumps(summary)
    assert "path" not in summary["mutants"][0]
    assert summary["mutants"][0]["id"] == "unrecorded"
    assert summary["mutants"][0]["outcome"] == "unknown"
    assert summary["mutants"][0]["old"][0]["status"] == "unknown"
    assert "manifest_hash" not in summary["plan"]
    assert "head_sha" not in summary["plan"]
    assert "reason" not in summary


def test_export_preserves_incomplete_and_provisional_qualification(private_report):
    private_report.update(complete=False, verdict="incomplete_with_witnesses",
                          reason="final_controls_not_valid")
    private_report["witnesses"][0]["confirmation"] = "unconfirmed_control"
    private_report["controls"][0]["status"] = "timeout"
    private_report["mutants"][0]["outcome"] = "gained_kill_provisional"
    summary = build_summary(private_report)
    assert not summary["complete"]
    assert summary["verdict"] == "incomplete_with_witnesses"
    assert summary["reason"] == "final_controls_not_valid"
    assert summary["witnesses"][0]["confirmation"] == "unconfirmed_control"
    assert summary["controls"][0]["status"] == "timeout"
    assert summary["mutants"][0]["outcome"] == "gained_kill_provisional"


@pytest.mark.parametrize("report", [[], None, "PRIVATE"])
def test_export_rejects_non_object_reports_without_creating_output(tmp_path, report):
    (tmp_path / "report.json").write_text(json.dumps(report))
    output = tmp_path / "share.json"
    with pytest.raises(ValueError, match="Report root must be a JSON object"):
        export_summary(tmp_path, output)
    assert not output.exists()


def test_unrecognized_types_do_not_escape_projection():
    summary = build_summary({
        "verdict": ["PRIVATE"], "complete": "PRIVATE", "reason": ["PRIVATE"],
        "plan": {"source_hashes": "PRIVATE", "test_hashes": ["PRIVATE"]},
        "mutants": "PRIVATE", "witnesses": ["PRIVATE"], "baseline": None,
        "test_diffs": [None], "controls": [{"status": {"PRIVATE": True}}],
        "limits": {"timeout_seconds": float("nan"), "max_mutants": True},
    })
    assert "PRIVATE" not in json.dumps(summary, allow_nan=False)
    assert summary["verdict"] == "inconclusive"
    assert not summary["complete"]
    assert summary["limits"] == {}
