"""Self-contained HTML and Markdown views of the canonical execution evidence."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path

from testdelta.export import build_summary


def _text(value) -> str:
    return (
        json.dumps(value, ensure_ascii=False, indent=2)
        if isinstance(value, (dict, list, tuple))
        else str(value)
    )


def _h(value) -> str:
    return html.escape(_text(value), quote=True)


def _md(value) -> str:
    text = html.escape(_text(value), quote=False).replace("\\", "\\\\")
    return re.sub(r"([`*_{}\[\]()#+.!|>~-])", r"\\\1", text).replace("\r", "").replace("\n", "<br>")


def _fence(value) -> str:
    text = _text(value)
    width = max((len(m.group()) for m in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, width + 1)
    return f"{fence}text\n{text}\n{fence}"


def _confirmed(witness: dict) -> bool:
    return witness.get("confirmation") == "three_pairs_and_final_controls"


def _summary(report: dict) -> tuple[str, str, str]:
    if report.get("verdict") == "unsupported_change":
        return (
            "Unsupported comparison",
            "The change is outside the supported test-only scope.",
            "warn",
        )
    if not report.get("complete", False):
        return (
            "Incomplete comparison",
            "No clean conclusion can be drawn for the selected scope. Review execution issues and qualified findings below.",
            "warn",
        )
    if report.get("verdict") == "no_loss_observed":
        return (
            "No loss observed in selected scope",
            "The selected mutants showed no loss of detection. This is not proof of test equivalence or software correctness.",
            "neutral",
        )
    witnesses = report.get("witnesses", [])
    if (
        report.get("verdict") == "loss_observed"
        and witnesses
        and all(_confirmed(w) for w in witnesses)
    ):
        return (
            "Detection loss observed",
            "Confirmed findings were repeated and checked against final original-code controls.",
            "loss",
        )
    return (
        "Comparison needs review",
        "Read each finding's confirmation and execution evidence before drawing a conclusion.",
        "warn",
    )


def _reason(report: dict) -> str:
    reason = report.get("reason")
    known = {
        "baseline_not_valid": "An original-code baseline did not complete successfully. No mutation conclusion is available.",
        "final_controls_not_valid": "Final original-code controls failed or did not complete. Detection changes remain provisional.",
        "total_budget_exhausted": "The time budget ended before all selected mutation work completed.",
        "mutation_generation_budget_exhausted": "Mutation generation exceeded its budget before a complete selected plan was available.",
        "mutant_execution_inconclusive": "At least one mutation execution could not support a reliable killed/survived result.",
        "no_supported_mutations": "No supported mutants were selected. An empty scope is not a clean result.",
    }
    return known.get(reason, reason) if isinstance(reason, str) else _text(reason) if reason else ""


def _runs(report: dict) -> list[tuple[str, dict]]:
    rows = []
    for label, key in (("Original baseline", "baseline"), ("Final original control", "controls")):
        rows.extend(
            (f"{label} {i} · {r.get('side', 'unknown')}", r)
            for i, r in enumerate(report.get(key, []), 1)
        )
    for mutant in report.get("mutants", []):
        for side in ("old", "new"):
            rows.extend(
                (f"Mutant {mutant.get('id', '?')} · {side} run {i}", r)
                for i, r in enumerate(mutant.get(side, []), 1)
            )
    return rows


def _details(run: dict) -> str:
    fields = (
        "reason",
        "assertion_failure_nodes",
        "collection_errors",
        "fixture_errors",
        "runtime_errors",
        "origin_mismatches",
        "missing_test_ids",
        "skipped",
        "cleanup_errors",
        "stderr",
        "stdout",
    )
    return "\n\n".join(f"{key}:\n{_text(run[key])}" for key in fields if run.get(key))


def _section(
    title, *, paragraphs=(), headers=(), rows=(), snippets=(), details=(), kind="panel"
) -> dict:
    return dict(
        title=title,
        paragraphs=list(paragraphs),
        headers=list(headers),
        rows=list(rows),
        snippets=list(snippets),
        details=list(details),
        kind=kind,
    )


def _diff_section(title: str, diff: str, sha256, truncated: bool) -> dict:
    paragraphs = [f"Diff SHA-256: {sha256 or 'not recorded'}"]
    if truncated:
        paragraphs.append(
            "Diff display truncated; the recorded SHA-256 identifies the full generated diff."
        )
    return _section(
        title,
        paragraphs=paragraphs,
        snippets=[diff] if diff else ["No textual diff recorded."],
    )


def _sections(report: dict) -> list[dict]:
    plan = report.get("plan", {})
    sections = []
    if _reason(report):
        sections.append(_section("Why this result needs attention", paragraphs=[_reason(report)]))
    for item in report.get("test_diffs", []):
        sections.append(_diff_section(
            f"Changed test diff: {item.get('path', 'unknown')}",
            item.get("diff", ""), item.get("sha256"), bool(item.get("truncated", False)),
        ))
    issues, evidence = [], []
    for label, run in _runs(report):
        detail = _details(run)
        summary = f"{label} · {run.get('status', 'unknown')}"
        invalid = run.get("status") not in {"pass", "assertion_failure"} or (
            not label.startswith("Mutant") and run.get("status") != "pass"
        )
        if invalid:
            issues.append((summary, detail or "No diagnostic output recorded.", False))
        if detail:
            evidence.append((summary, detail, False))
    if not report.get("witnesses"):
        sections.append(
            _section(
                "Findings",
                paragraphs=[
                    "No qualified detection-loss witness is recorded. Read the verdict and scope before interpreting this absence."
                ],
            )
        )
    for witness in report.get("witnesses", []):
        confirmed = _confirmed(witness)
        label = "Confirmed detection loss" if confirmed else "Provisional observation"
        message = (
            "Old tests caught this fault; new tests passed with the same fault."
            if confirmed
            else "The recorded pairs suggest a possible loss. Final controls have not confirmed this finding."
        )
        rows = []
        for side in ("old", "new"):
            outcomes = witness.get(f"{side}_outcomes")
            if outcomes is None:
                mutant = next(
                    (m for m in report.get("mutants", []) if m.get("id") == witness.get("id")), {}
                )
                outcomes = [r.get("status", "unknown") for r in mutant.get(side, [])]
            rows.append((side.title(), ", ".join(map(str, outcomes)) or "not recorded"))
        sections.append(
            _section(
                f"{label}: {witness.get('id', 'unknown')}",
                paragraphs=[
                    message,
                    f"Location: {witness.get('path', '?')}:{witness.get('line', '?')} · {witness.get('operator', '?')}",
                    f"Confirmation: {witness.get('confirmation', 'not recorded')}",
                    "Old failing tests: "
                    + (", ".join(witness.get("old_failure_nodes", [])) or "not recorded"),
                    f"Original SHA-256: {witness.get('original_sha256', 'not recorded')}",
                    f"Mutated SHA-256: {witness.get('mutated_sha256', 'not recorded')}",
                ],
                headers=["Side", "Recorded runs"],
                rows=rows,
                snippets=[
                    witness.get("replacement_description", "Replacement details not recorded.")
                ],
                details=[
                    (
                        "Replay trusted local record",
                        f"testdelta replay <this-report-directory> --witness {witness.get('id', 'unknown')}",
                        False,
                    )
                ],
                kind="confirmed" if confirmed else "provisional",
            )
        )
    mutant_rows = []
    for mutant in report.get("mutants", []):
        row = [
            f"{mutant.get('id', '?')} · {mutant.get('path', '?')}:{mutant.get('line', '?')}",
            mutant.get("outcome", "not recorded"),
        ]
        row.extend(
            ", ".join(str(r.get("status", "unknown")) for r in mutant.get(side, []))
            or "not attempted"
            for side in ("old", "new")
        )
        mutant_rows.append(row)
    sections.append(
        _section(
            "All attempted mutants",
            headers=["ID / location", "Outcome", "Old executions", "New executions"],
            rows=mutant_rows or [("None recorded", "No mutation conclusion", "—", "—")],
        )
    )
    for mutant in report.get("mutants", []):
        if "diff" in mutant:
            sections.append(_diff_section(
                f"Mutant diff: {mutant.get('id', 'unknown')} · {mutant.get('path', '?')}",
                mutant["diff"], mutant.get("diff_sha256"),
                bool(mutant.get("diff_truncated", False)),
            ))
    controls = [
        (
            label,
            run.get("status", "unknown"),
            f"{len(run.get('ran', []))} / {len(run.get('collected', []))}",
        )
        for label, run in _runs(report)
        if not label.startswith("Mutant")
    ]
    sections.append(
        _section(
            "Original-code baselines and final controls",
            headers=["Execution", "Status", "Tests ran / collected"],
            rows=controls or [("None recorded", "Not available", "—")],
        )
    )
    if issues:
        sections.append(_section("Execution issues", details=issues))
    sections.append(
        _section(
            "Execution details",
            details=evidence,
            paragraphs=[] if evidence else ["No additional execution output recorded."],
        )
    )
    provenance = [
        ("Base tests Git commit", plan.get("base_sha", "not recorded")),
        ("Head tests Git commit", plan.get("head_sha", "not recorded")),
        ("Manifest SHA-256", plan.get("manifest_hash", "not recorded")),
        ("Supervisor environment SHA-256", report.get("environment_hash", "not recorded")),
    ]
    provenance.extend(
        (f"Source SHA-256 · {name}", value) for name, value in plan.get("source_hashes", {}).items()
    )
    if plan.get("test_hashes"):
        provenance.extend(
            (f"Test-file SHA-256 · {name}", value) for name, value in plan["test_hashes"].items()
        )
    else:
        provenance.append(
            (
                "Test-file SHA-256",
                "Not recorded; test revisions are identified by the Git commits above.",
            )
        )
    sections.append(_section("Provenance", headers=["Evidence", "Value"], rows=provenance))
    scope = [
        "Finite selected mutation scope only. A complete result does not cover every possible mutant or input.",
        "Attempted pairs include inconclusive executions; attempted is not the same as valid evidence.",
        f"Source selection: {_text(plan.get('manifest', {}).get('source_modules', []))}",
        f"Test selection: {_text(plan.get('manifest', {}).get('test_paths', []))}",
    ]
    if report.get("limits"):
        scope.append(f"Configured limits: {_text(report['limits'])}")
    for key in ("exclusions", "limitations"):
        if report.get(key):
            scope.append(f"{key}: {_text(report[key])}")
    if plan.get("unsupported_changes"):
        scope.append(f"Unsupported changes: {_text(plan['unsupported_changes'])}")
    sections.append(_section("Scope and exclusions", paragraphs=scope))
    return sections


def markdown(report: dict) -> str:
    title, explanation, _tone = _summary(report)
    lines = [
        "# TestDelta",
        "",
        f"## {title}",
        "",
        explanation,
        "",
        f"Recorded verdict: {_md(report.get('verdict', 'inconclusive'))}",
        f"Selected plan complete: {bool(report.get('complete', False))}",
        f"Mutation pairs attempted / planned: {_md(report.get('mutants_completed', 0))} / {_md(report.get('mutants_planned', 0))}",
        "",
    ]
    for section in _sections(report):
        lines += [f"## {_md(section['title'])}", ""]
        for paragraph in section["paragraphs"]:
            lines += [_md(paragraph), ""]
        for snippet in section["snippets"]:
            lines += [_fence(snippet), ""]
        if section["headers"]:
            lines += [
                "| " + " | ".join(_md(h) for h in section["headers"]) + " |",
                "| " + " | ".join("---" for _ in section["headers"]) + " |",
            ]
            lines.extend(
                "| " + " | ".join(_md(cell) for cell in row) + " |" for row in section["rows"]
            )
            lines.append("")
        for label, detail, expanded in section["details"]:
            lines += [
                f"<details{' open' if expanded else ''}><summary>{_md(label)}</summary>",
                "",
                _fence(detail),
                "",
                "</details>",
                "",
            ]
    lines += [
        "Trusted local tests only; temporary copies are not a sandbox.",
        "No observed loss is not proof of test equivalence or software correctness.",
        "",
    ]
    return "\n".join(lines)


_STYLE = """
:root{color-scheme:light;--ink:#182c3e;--muted:#536779;--line:#dce5eb}*{box-sizing:border-box}
body{margin:0;background:#f2f6f8;color:var(--ink);font:15px/1.6 system-ui,sans-serif}
main{max-width:1120px;margin:0 auto;padding:40px 24px 64px}.eyebrow{font-size:12px;font-weight:700;letter-spacing:.14em;color:#447080}
h1{font-size:clamp(26px,4vw,40px);line-height:1.2;margin:10px 0}h2{font-size:20px;margin:0 0 16px;overflow-wrap:anywhere}p{overflow-wrap:anywhere}
.muted,footer{color:var(--muted)}section,article{background:#fff;border:1px solid var(--line);border-radius:12px;padding:24px;margin:18px 0}
.summary{border-top:5px solid #456d82}.warn{border-top-color:#b87b19}.loss{border-top-color:#b44444}
.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:20px}.metric{padding:12px 14px;background:#f5f8fa;border-radius:8px}
.metric strong{display:block;font-size:22px}.metric span{color:var(--muted);font-size:12px}.badge{padding:4px 9px;background:#eaf0f4;border-radius:5px;font-size:12px}
.provisional{border-left:4px solid #b87b19}.confirmed{border-left:4px solid #b44444}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:13px}
th,td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}th{background:#f3f7f9}
pre{font:12px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#edf3f6;padding:16px;border-radius:8px;max-height:460px;overflow:auto}
details{border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0}summary{cursor:pointer;font-weight:600;overflow-wrap:anywhere}footer{font-size:13px;margin-top:24px}
@media(max-width:700px){main{padding:20px 14px}section,article{padding:18px}.metrics{grid-template-columns:1fr}th,td{padding:8px}}
"""


def html_document(report: dict) -> str:
    title, explanation, tone = _summary(report)
    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>TestDelta · {_h(title)}</title><style>{_STYLE}</style></head><body><main>",
        f'<header><div class="eyebrow">TESTDELTA / EXECUTION EVIDENCE</div><h1>{_h(title)}</h1><p class="muted">{_h(explanation)}</p></header>',
        f'<section class="summary {tone}" aria-label="Comparison summary"><span class="badge">Recorded verdict: {_h(report.get("verdict", "inconclusive"))}</span><div class="metrics">',
    ]
    metrics = [
        (
            "Complete" if report.get("complete", False) else "Incomplete",
            "Selected plan and controls",
        ),
        (
            f"{report.get('mutants_completed', 0)} / {report.get('mutants_planned', 0)}",
            "Mutation pairs attempted / planned",
        ),
        (
            sum(_confirmed(w) for w in report.get("witnesses", [])),
            "Confirmed detection-loss findings",
        ),
    ]
    parts.extend(
        f'<div class="metric"><strong>{_h(value)}</strong><span>{_h(label)}</span></div>'
        for value, label in metrics
    )
    parts.append(
        '</div><p class="muted">Attempted pairs include inconclusive executions. Complete applies only to the finite selected scope.</p></section>'
    )
    for section in _sections(report):
        tag = "article" if section["kind"] in {"confirmed", "provisional"} else "section"
        parts.append(f'<{tag} class="{section["kind"]}"><h2>{_h(section["title"])}</h2>')
        parts.extend(f"<p>{_h(paragraph)}</p>" for paragraph in section["paragraphs"])
        parts.extend(f"<pre>{_h(snippet)}</pre>" for snippet in section["snippets"])
        if section["headers"]:
            parts.append('<div class="scroll"><table><thead><tr>')
            parts.extend(f'<th scope="col">{_h(header)}</th>' for header in section["headers"])
            parts.append("</tr></thead><tbody>")
            parts.extend(
                "<tr>" + "".join(f"<td>{_h(cell)}</td>" for cell in row) + "</tr>"
                for row in section["rows"]
            )
            parts.append("</tbody></table></div>")
        for label, detail, expanded in section["details"]:
            parts.append(
                f"<details{' open' if expanded else ''}><summary>{_h(label)}</summary><pre>{_h(detail)}</pre></details>"
            )
        parts.append(f"</{tag}>")
    parts.append(
        "<footer>Trusted local tests only; temporary copies are not a sandbox. No observed loss is not proof of test equivalence or software correctness. JSON is the canonical evidence record. Review captured output before sharing.</footer></main></body></html>"
    )
    return "\n".join(parts)


def write_report(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    text = markdown(report)
    (output / "report.md").write_text(text, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(github_summary(report) + "\n")
    (output / "report.html").write_text(html_document(report), encoding="utf-8")


def github_summary(report: dict) -> str:
    """Render only allowlisted outcomes for an automatically published CI summary."""
    summary = build_summary(report)
    title, explanation, _tone = _summary(summary)
    confirmed = sum(_confirmed(witness) for witness in summary["witnesses"])
    return "\n".join([
        "# TestDelta", "", f"## {title}", "", explanation, "",
        f"Recorded verdict: {summary['verdict']}",
        f"Selected plan complete: {summary['complete']}",
        f"Mutation pairs attempted / planned: {summary['mutants_completed']} / {summary['mutants_planned']}",
        f"Confirmed detection-loss findings: {confirmed}", "",
        "Finite selected mutation scope only; no proof of test equivalence or software correctness.",
        "Raw diagnostics, paths, diffs, and source/config text are omitted from this CI summary.",
        "Local report artifacts and replay bundles can contain private execution output and source.",
        "",
    ])


def exit_code(report: dict, advisory: bool = False) -> int:
    if not report.get("complete", False):
        return 2
    if report.get("verdict") == "no_loss_observed":
        return 0
    if report.get("verdict") == "loss_observed":
        return 0 if advisory else 1
    return 2
