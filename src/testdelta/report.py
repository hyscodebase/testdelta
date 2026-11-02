"""One canonical report, local artifacts, and escaped human-readable evidence."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path


def markdown(report: dict) -> str:
    plan = report.get("plan", {})
    lines = ["# TestDelta", "", f"**{report['verdict']}**", "",
             f"Completed: {report['complete']}",
             f"Mutants: {report.get('mutants_completed', 0)}/{report.get('mutants_planned', 0)}", "",
             f"Base tests: `{plan.get('base_sha', 'unknown')}`",
             f"Head tests: `{plan.get('head_sha', 'unknown')}`", "",
             "This is evidence about the completed finite mutation scope. A finding needs review.", ""]
    for witness in report.get("witnesses", []):
        lines += [f"## Lost detection: {witness['id']}", "",
                  f"`{witness['path']}:{witness['line']}` — {witness['operator']}", "",
                  "Old tests caught this fault. New tests passed with the same fault.", "",
                  f"Confirmation: {witness.get('confirmation', 'unconfirmed')}", "",
                  "```text", witness.get("replacement_description", ""), "```", "",
                  "Old failing test(s): " + ", ".join(witness.get("old_failure_nodes", [])), "",
                  f"Replay: `testdelta replay <this-report-directory> --witness {witness['id']}`", ""]
    if report.get("reason"):
        lines += ["## Scope / incomplete reason", "", str(report["reason"]), ""]
    lines += ["## Limits", "", "Trusted local tests only; temporary copies are not a sandbox.",
              "No observed loss is not proof of test equivalence or software correctness.", ""]
    return "\n".join(lines)


def write_report(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    text = markdown(report)
    (output / "report.md").write_text(text, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(text + "\n")
    (output / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>TestDelta</title>'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>body{max-width:900px;margin:3rem auto;padding:0 1rem;font:16px/1.6 system-ui;'
        'color:#13243a;background:#f5f7fb}pre{white-space:pre-wrap;overflow-wrap:anywhere;'
        'background:white;padding:2rem;border:1px solid #cdd8e8;border-radius:12px}</style>'
        f'<pre>{html.escape(text)}</pre></html>', encoding="utf-8"
    )


def exit_code(report: dict, advisory: bool = False) -> int:
    if report["verdict"] == "no_loss_observed":
        return 0
    if report["verdict"] == "loss_observed":
        return 0 if advisory else 1
    return 2
