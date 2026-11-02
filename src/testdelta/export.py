"""An explicit, local-only projection of execution evidence for sharing.

Raw reports and replay bundles can contain private output, paths, and source.
This projection retains only recognized outcomes, counts, relative locations,
committed revisions, and hashes. It is not a replay record or an anonymizer:
relative filenames and hashes may still identify a project.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path, PureWindowsPath

from testdelta.git_inputs import InputError, safe_path

_VERDICTS = {
    "inconclusive", "unsupported_change", "no_loss_observed", "loss_observed",
    "incomplete_with_witnesses",
}
_STATUSES = {
    "pass", "assertion_failure", "collection_error", "fixture_error", "runtime_error",
    "not_executed", "timeout", "not_completed", "invalid_evidence",
}
_OUTCOMES = {
    "lost_kill", "retained_kill", "gained_kill_provisional", "survived_both",
    "unstable_or_incomplete", "inconclusive",
}
_CONFIRMATIONS = {
    "three_pairs_and_final_controls", "pending_final_controls", "unconfirmed_control",
}
_REASONS = {
    "baseline_not_valid", "final_controls_not_valid", "total_budget_exhausted",
    "mutation_generation_budget_exhausted", "mutant_execution_inconclusive",
    "no_supported_mutations",
}


def _enum(value, allowed: set[str], fallback: str = "unknown") -> str:
    return value if isinstance(value, str) and value in allowed else fallback


def _hash(value, *, revision: bool = False) -> str | None:
    pattern = r"(?:[0-9a-f]{40}|[0-9a-f]{64})" if revision else r"[0-9a-f]{64}"
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else None


def _path(value) -> str | None:
    if not isinstance(value, str) or PureWindowsPath(value).drive:
        return None
    if any(ord(char) < 32 for char in value):
        return None
    try:
        return safe_path(value)
    except InputError:
        return None


def _count(value) -> int:
    return value if type(value) is int and value >= 0 else 0


def _records(value) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _run(run: dict) -> dict:
    result = {"status": _enum(run.get("status"), _STATUSES)}
    if run.get("side") in ("old", "new"):
        result["side"] = run["side"]
    for key in ("ran", "collected", "skipped", "missing_test_ids", "assertion_failure_nodes"):
        if isinstance(run.get(key), list):
            result[f"{key}_count"] = len(run[key])
    return result


def _mutation(item: dict, *, witness: bool = False) -> dict:
    identity = item.get("id")
    result = {
        "id": identity if isinstance(identity, str) and re.fullmatch(
            r"(?:cr-[0-9a-f]{16}|m[0-9]+)", identity
        ) else "unrecorded",
    }
    path = _path(item.get("path"))
    if path:
        result["path"] = path
    if type(item.get("line")) is int and item["line"] > 0:
        result["line"] = item["line"]
    for key in ("original_sha256", "mutated_sha256", "diff_sha256"):
        if value := _hash(item.get(key)):
            result[key] = value
    if type(item.get("diff_truncated")) is bool:
        result["diff_truncated"] = item["diff_truncated"]
    if witness:
        result["confirmation"] = _enum(item.get("confirmation"), _CONFIRMATIONS)
        for side in ("old", "new"):
            values = item.get(f"{side}_outcomes", [])
            result[f"{side}_outcomes"] = [
                _enum(value, {"killed", "survived", "inconclusive"}) for value in values
            ] if isinstance(values, list) else []
    else:
        result["outcome"] = _enum(item.get("outcome"), _OUTCOMES)
        for side in ("old", "new"):
            result[side] = [_run(run) for run in _records(item.get(side))]
    return result


def build_summary(report: dict) -> dict:
    """Build an allowlisted summary without copying arbitrary nested fields."""
    if not isinstance(report, dict):
        raise ValueError("Report root must be a JSON object")
    plan = report.get("plan", {})
    plan = plan if isinstance(plan, dict) else {}
    selected = {}
    for key in ("base_sha", "requested_base_sha", "head_sha"):
        if value := _hash(plan.get(key), revision=True):
            selected[key] = value
    if value := _hash(plan.get("manifest_hash")):
        selected["manifest_hash"] = value
    selected["manifest_origin"] = _enum(plan.get("manifest_origin"), {"base_commit", "external"})
    selected["source_hashes"] = {}
    hashes = plan.get("source_hashes", {})
    for path, value in (hashes.items() if isinstance(hashes, dict) else []):
        if (relative := _path(path)) and (value is None or _hash(value)):
            selected["source_hashes"][relative] = value
    selected["test_hashes"] = {}
    hashes = plan.get("test_hashes", {})
    for path, values in (hashes.items() if isinstance(hashes, dict) else []):
        if (relative := _path(path)) and isinstance(values, dict):
            selected["test_hashes"][relative] = {
                side: value for side in ("old", "new")
                if (value := values.get(side)) is None or _hash(value)
            }
    summary = {
        "schema_version": "0.1", "export_kind": "sanitized_summary",
        "verdict": _enum(report.get("verdict"), _VERDICTS, "inconclusive"),
        "complete": report.get("complete") is True,
        "mutants_planned": _count(report.get("mutants_planned")),
        "mutants_completed": _count(report.get("mutants_completed")),
        "plan": selected,
        "baseline": [_run(run) for run in _records(report.get("baseline"))],
        "controls": [_run(run) for run in _records(report.get("controls"))],
        "mutants": [_mutation(item) for item in _records(report.get("mutants"))],
        "witnesses": [
            _mutation(item, witness=True) for item in _records(report.get("witnesses"))
        ],
        "limitations": [
            "Finite selected mutation scope only; no proof of test equivalence or correctness.",
            "Incomplete work and provisional observations are not clean conclusions.",
            "Raw diagnostics, source/config text, diffs, and absolute paths are omitted.",
            "Relative filenames and hashes remain; this summary is not a replay record.",
        ],
    }
    reason = report.get("reason")
    if isinstance(reason, str) and reason in _REASONS:
        summary["reason"] = reason
    if value := _hash(report.get("environment_hash")):
        summary["environment_hash"] = value
    limits = report.get("limits", {})
    if isinstance(limits, dict):
        summary["limits"] = {
            key: value for key in ("budget_seconds", "max_mutants", "timeout_seconds")
            if type(value := limits.get(key)) in (int, float) and value > 0
            and (type(value) is int or math.isfinite(value))
        }
    summary["test_diffs"] = []
    for item in _records(report.get("test_diffs")):
        if (path := _path(item.get("path"))) and (value := _hash(item.get("sha256"))):
            summary["test_diffs"].append({
                "path": path, "sha256": value, "truncated": item.get("truncated") is True,
            })
    return summary


def export_summary(report_dir: Path, output: Path) -> dict:
    """Write a local sanitized JSON file, refusing to overwrite any existing file."""
    report = json.loads((Path(report_dir) / "report.json").read_text(encoding="utf-8"))
    summary = build_summary(report)
    with Path(output).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return summary
