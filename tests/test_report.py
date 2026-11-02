"""Report behavior is shared across readable HTML and Markdown evidence views."""

import copy
import json
import re
from html.parser import HTMLParser

import pytest

from testdelta.report import exit_code, html_document, markdown, write_report


@pytest.fixture
def report():
    old = {
        "status": "assertion_failure",
        "ran": ["test_calc"],
        "collected": ["test_calc"],
        "assertion_failure_nodes": ["test_calc"],
    }
    new = {"status": "pass", "ran": ["test_calc"], "collected": ["test_calc"]}
    return {
        "verdict": "loss_observed",
        "complete": True,
        "mutants_completed": 1,
        "mutants_planned": 1,
        "plan": {
            "base_sha": "base123",
            "head_sha": "head456",
            "manifest_hash": "manifest789",
            "source_hashes": {"calc.py": "source111"},
            "test_hashes": {"test_calc.py": {"old": "old222", "new": "new333"}},
            "manifest": {"source_modules": ["calc.py"], "test_paths": ["test_calc.py"]},
        },
        "environment_hash": "environment444",
        "limits": {"max_mutants": 1},
        "limitations": ["Only selected pure Python sources were evaluated."],
        "witnesses": [
            {
                "id": "m1",
                "path": "calc.py",
                "line": 2,
                "operator": "CosmicRay",
                "original_sha256": "source111",
                "mutated_sha256": "mutant555",
                "confirmation": "three_pairs_and_final_controls",
                "old_outcomes": ["killed"] * 3,
                "new_outcomes": ["survived"] * 3,
                "old_failure_nodes": ["test_calc"],
                "replacement_description": "return value + 1\n→ return value - 1",
            }
        ],
        "mutants": [
            {
                "id": "m1",
                "path": "calc.py",
                "line": 2,
                "outcome": "lost_kill",
                "old": [copy.deepcopy(old) for _ in range(3)],
                "new": [copy.deepcopy(new) for _ in range(3)],
            }
        ],
        "baseline": [dict(new, side="old"), dict(new, side="new")],
        "controls": [dict(new, side="old"), dict(new, side="new")],
    }


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)


def test_html_is_structured_and_untrusted_evidence_cannot_inject_markup(report):
    attack = '</pre><script>alert(1)</script><img src=x onerror="alert(2)">'
    report["witnesses"][0]["id"] = attack
    report["witnesses"][0]["replacement_description"] = attack
    report["mutants"][0]["old"][0]["stdout"] = attack
    report["plan"]["source_hashes"][attack] = attack
    output = html_document(report)
    parsed = Tags()
    parsed.feed(output)

    assert {"article", "table", "thead", "tbody", "details", "summary"} <= set(parsed.tags)
    assert not {"script", "img", "iframe", "link"} & set(parsed.tags)
    assert not any(
        name in {"src", "href"} or name.startswith("on") for name, _ in parsed.attributes
    )
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in output
    assert "base123" in output and "source111" in output and "old222" in output
    assert "Original-code baselines and final controls" in output
    assert "All attempted mutants" in output


@pytest.mark.parametrize("render", [html_document, markdown])
def test_failed_final_control_keeps_observation_provisional(report, render):
    report["complete"] = False
    report["verdict"] = "incomplete_with_witnesses"
    report["reason"] = "final_controls_not_valid"
    report["witnesses"][0]["confirmation"] = "unconfirmed_control"
    report["controls"][1].update(status="timeout", stderr="control exceeded timeout")
    output = render(report)

    assert "Incomplete comparison" in output
    assert "Provisional observation" in output
    assert "Final controls have not confirmed this finding" in output
    assert "Old tests caught this fault" not in output
    assert "control exceeded timeout" in output
    assert exit_code(report, advisory=True) == 2


@pytest.mark.parametrize("render", [html_document, markdown])
def test_incomplete_record_cannot_present_a_clean_no_loss_headline(report, render):
    report.update(complete=False, verdict="no_loss_observed", witnesses=[], mutants_completed=0)
    output = render(report)
    assert "Incomplete comparison" in output
    assert "No loss observed in selected scope" not in output
    assert "No clean conclusion" in output
    assert exit_code(report) == 2


def test_markdown_untrusted_fences_and_inline_markup_stay_data(report):
    snippet = "```\n## forged heading\n````\n<script>alert(1)</script>"
    report["witnesses"][0]["replacement_description"] = snippet
    report["witnesses"][0]["id"] = "<img src=x> | [click](javascript:alert(1))\n# forged"
    output = markdown(report)
    assert f"`````text\n{snippet}\n`````" in output
    outside_fences = re.sub(r"(?ms)^(`{3,})[^\n]*\n.*?^\1[ \t]*$", "", output)
    assert "<img src=x>" not in outside_fences
    assert "&lt;img src=x&gt;" in output
    assert "\\| \\[click\\]\\(javascript:alert\\(1\\)\\)" in output
    assert "\n# forged" not in outside_fences


@pytest.mark.parametrize("render", [html_document, markdown])
def test_inconclusive_diagnostics_and_scope_are_visible(report, render):
    report.update(complete=False, verdict="inconclusive", reason="baseline_not_valid", witnesses=[])
    report["baseline"][0].update(
        status="collection_error", collection_errors=["missing dependency"]
    )
    report["mutants"][0].update(
        outcome="inconclusive", new=[{"status": "timeout", "stderr": "execution expired"}]
    )
    output = render(report)
    assert "baseline did not complete" in output
    assert "missing dependency" in output
    assert "execution expired" in output
    assert "inconclusive" in output
    assert "Finite selected mutation scope only" in output
    assert "not the same as valid evidence" in output
    assert "Only selected pure Python sources were evaluated" in output
    assert output.index("All attempted mutants") < output.index("Execution issues")
    assert output.index("baselines and final controls") < output.index("Execution issues")
    assert "<details open" not in output


@pytest.mark.parametrize("render", [html_document, markdown])
def test_complete_no_loss_is_explicitly_finite(report, render):
    report.update(verdict="no_loss_observed", witnesses=[])
    report["mutants"][0]["outcome"] = "retained_kill"
    output = render(report)
    assert "No loss observed in selected scope" in output
    assert "not proof of test equivalence" in output
    assert "does not cover every possible mutant or input" in output
    assert exit_code(report) == 0


def test_write_report_preserves_canonical_data_and_github_summary(report, tmp_path, monkeypatch):
    original = copy.deepcopy(report)
    summary = tmp_path / "summary.md"
    summary.write_text("Previous step\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    output = tmp_path / "evidence"
    write_report(report, output)
    assert report == original
    assert json.loads((output / "report.json").read_text()) == original
    assert (output / "report.md").read_text() == markdown(report)
    assert (output / "report.html").read_text() == html_document(report)
    assert summary.read_text() == "Previous step\n" + markdown(report) + "\n"
    assert exit_code(report) == 1
    assert exit_code(report, advisory=True) == 0
