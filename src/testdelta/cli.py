"""Local command line interface for TestDelta."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path

from testdelta import __version__
from testdelta.compare import compare, environment, target_runtime, write_bundle
from testdelta.git_inputs import InputError, digest, make_plan, safe_path
from testdelta.report import exit_code, write_report


def show(report: dict, output: Path) -> None:
    write_report(report, output)
    print(json.dumps({"verdict": report["verdict"], "complete": report["complete"],
                      "lost_faults": len(report["witnesses"]),
                      "mutants_completed": report["mutants_completed"],
                      "mutants_planned": report["mutants_planned"],
                      "report": str((output / "report.html").resolve())}, indent=2))


def demo(output: Path, scenario: str = "lost") -> int:
    """Generate a real two-commit repository and compare it with the actual engine."""
    output.mkdir(parents=True, exist_ok=True)
    # Keep this synthetic repo so the generated witness can actually be replayed.
    with nullcontext(tempfile.mkdtemp(prefix="repository-", dir=output.resolve())) as temporary:
        repo = Path(temporary)
        (repo / "src").mkdir()
        (repo / "tests").mkdir()
        (repo / ".testdelta.toml").write_text(
            'source_modules = ["src/pricing.py"]\ntest_paths = ["tests/test_pricing.py"]\n'
        )
        (repo / "src/pricing.py").write_text(
            'def total(price, quantity=1, member=False):\n'
            '    subtotal = price * quantity\n'
            '    if member:\n        subtotal = subtotal * 9 // 10\n'
            '    shipping = 0 if subtotal >= 5000 else 500\n'
            '    return subtotal + shipping\n'
        )
        tests = repo / "tests/test_pricing.py"
        tests.write_text(
            'from pricing import total\n\n'
            'def test_quantity():\n    assert total(1000, 3) == 3500\n\n'
            'def test_member():\n    assert total(1000, member=True) == 1400\n\n'
            'def test_shipping_boundary():\n    assert total(5000) == 5000\n\n'
            'def test_shipping_below():\n    assert total(4999) == 5499\n'
        )

        def commit(message: str) -> None:
            for arguments in (["add", "."], ["-c", "user.name=TestDelta Demo", "-c",
                              "user.email=testdelta@example.invalid", "-c", "commit.gpgsign=false",
                              "-c", "core.hooksPath=/dev/null", "commit", "-qm", message]):
                subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True)

        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        commit("Strong tests")
        if scenario == "lost":
            tests.write_text(tests.read_text().replace("== 3500", ">= 0").replace(
                "== 1400", ">= 0").replace("== 5000", ">= 0").replace("== 5499", ">= 0"))
        elif scenario == "refactor":
            tests.write_text(
                'from pricing import total\n\n'
                'def test_table():\n'
                '    for args, kwargs, expected in [((1000, 3), {}, 3500),\n'
                '        ((1000,), {"member": True}, 1400), ((5000,), {}, 5000),\n'
                '        ((4999,), {}, 5499)]:\n'
                '        assert total(*args, **kwargs) == expected\n'
            )
        else:
            tests.write_text('def test_bad_baseline():\n    assert False\n')
        commit(f"Synthetic {scenario} scenario")
        plan, before, after = make_plan(repo, "HEAD~1")
        report, bundle = compare(plan, before, after, budget_seconds=120, max_mutants=6)
        report["demo"] = "Executed original synthetic fixtures, not a real-project benchmark"
        report["demo_repository"] = str(repo)
        report["demo_scenario"] = scenario
        show(report, output)
        write_bundle(bundle, output)
        expected = {"lost": "loss_observed", "refactor": "no_loss_observed", "inconclusive": "inconclusive"}
        return 0 if report["verdict"] == expected[scenario] else 2


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Do changed pytest tests catch the same faults?")
    result.add_argument("--version", action="version", version=f"TestDelta {__version__}")
    commands = result.add_subparsers(dest="command", required=True)
    sample = commands.add_parser("demo", help="Run executed synthetic fixtures; no model API needed")
    sample.add_argument("--output", type=Path, default=Path(".testdelta/demo"))
    sample.add_argument("--scenario", choices=["lost", "refactor", "inconclusive"], default="lost")
    init = commands.add_parser("init", help="Write an explicit manifest; no tests are executed")
    init.add_argument("--source", action="append", required=True)
    init.add_argument("--tests", action="append", required=True)
    init.add_argument("--repo", type=Path, default=Path.cwd())
    init.add_argument("--output", type=Path, help="Write external config here instead of the repository")
    for name in ("plan", "compare"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--base", required=True)
        cmd.add_argument("--head", default="HEAD")
        cmd.add_argument("--repo", type=Path, default=Path.cwd())
        cmd.add_argument("--direct-base", action="store_true")
        cmd.add_argument("--config", type=Path, help="External UTF-8 manifest; relative to current directory")
        if name == "compare":
            cmd.add_argument("--output", type=Path, default=Path(".testdelta/report"))
            cmd.add_argument("--budget-seconds", type=float, default=120)
            cmd.add_argument("--timeout-seconds", type=float, default=15)
            cmd.add_argument("--max-mutants", type=int, default=10)
            cmd.add_argument("--python", dest="python_executable")
            cmd.add_argument("--advisory", action="store_true")
    replay = commands.add_parser("replay", help="Re-run a trusted local bundle on its committed repo")
    replay.add_argument("bundle", type=Path)
    replay.add_argument("--witness", required=True)
    replay.add_argument("--repo", type=Path, default=Path.cwd())
    replay.add_argument("--output", type=Path, default=Path(".testdelta/replay"))
    replay.add_argument("--python", dest="python_executable")
    share = commands.add_parser("export", help="Write an allowlisted summary without raw logs or source")
    share.add_argument("report", type=Path)
    share.add_argument("--output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if getattr(args, "python_executable", None):
            selected = shutil.which(args.python_executable)
            if selected is None:
                raise InputError("Selected Python executable was not found")
            # abspath deliberately preserves a venv's executable symlink.
            args.python_executable = os.path.abspath(selected)
        if args.command == "demo":
            return demo(args.output, args.scenario)
        if args.command == "init":
            config = args.output if args.output is not None else args.repo / ".testdelta.toml"
            if config.exists() or config.is_symlink():
                raise InputError(f"Config already exists; it was not overwritten: {config}")
            sources, tests = [safe_path(p) for p in args.source], [safe_path(p) for p in args.tests]
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(f"source_modules = {json.dumps(sources)}\ntest_paths = {json.dumps(tests)}\n", encoding="utf-8")
            instruction = ("Use --config with plan/compare." if args.output is not None else
                           "Commit it before the test change you want to compare.")
            print(f"Created {config}. {instruction}")
            return 0
        if args.command == "export":
            from testdelta.export import export_summary
            summary = export_summary(args.report, args.output)
            print(json.dumps({"output": str(args.output), "verdict": summary["verdict"]}))
            return 0
        if args.command == "replay":
            path = args.bundle / "bundle.json" if args.bundle.is_dir() else args.bundle
            raw = path.read_bytes()
            recorded_digest = path.with_name("bundle.sha256").read_text().strip()
            if digest(raw) != recorded_digest:
                raise InputError("Bundle checksum mismatch")
            bundle = json.loads(raw)
            if not isinstance(bundle, dict):
                raise InputError("Bundle root must be a JSON object")
            if bundle["environment"] != environment():
                raise InputError("Replay environment differs from recorded tool/Python/platform versions")
            if bundle.get("target_runtime") != target_runtime(args.python_executable):
                raise InputError("Replay target runtime differs from recorded Python/pytest interpreter")
            recorded = bundle["plan"]
            manifest_bytes = None
            origin = recorded.get("manifest_origin", "base_commit")
            if origin == "external":
                snapshot = recorded["manifest_snapshot"]
                if not isinstance(snapshot["text"], str):
                    raise InputError("Invalid external manifest snapshot")
                manifest_bytes = snapshot["text"].encode("utf-8")
                if digest(manifest_bytes) != snapshot["sha256"] or snapshot["sha256"] != recorded["manifest_hash"]:
                    raise InputError("External manifest checksum mismatch")
            elif origin != "base_commit":
                raise InputError("Unknown manifest origin")
            plan, before, after = make_plan(
                args.repo, recorded["base_sha"], recorded["head_sha"], direct_base=True,
                manifest_bytes=manifest_bytes,
            )
            if plan["manifest_hash"] != recorded["manifest_hash"] or plan["manifest"] != recorded["manifest"]:
                raise InputError("Replay manifest does not match the recorded configuration")
            if plan["source_hashes"] != bundle["source_hashes"]:
                raise InputError("Replay source does not match the recorded source")
            mutations = [m for m in bundle["mutations"] if m["id"] == args.witness]
            if len(mutations) != 1:
                raise InputError("Unknown or ambiguous witness id")
            mutation = mutations[0]
            if mutation["path"] not in plan["source_hashes"]:
                raise InputError("Mutation path is outside the declared source scope")
            if digest(after[mutation["path"]]) != mutation["original_sha256"] or digest(
                mutation["mutated_source"].encode("utf-8")
            ) != mutation["mutated_sha256"]:
                raise InputError("Mutation source checksum mismatch")
            report, new_bundle = compare(
                plan, before, after, mutations_override=mutations,
                python_executable=args.python_executable,
            )
            show(report, args.output)
            write_bundle(new_bundle, args.output)
            return exit_code(report)
        manifest_bytes = args.config.read_bytes() if args.config is not None else None
        plan, before, after = make_plan(args.repo, args.base, args.head, args.direct_base,
                                        manifest_bytes=manifest_bytes)
        if args.command == "plan":
            plan["execution_estimate"] = {"default_max_mutants": 10, "suite_calls_max": 66,
                                          "formula": "6 + 6 * max_mutants",
                                          "runtime_seconds": "unknown_until_baselines_execute"}
            print(json.dumps(plan, indent=2))
            return 0 if plan["supported"] else 2
        if args.budget_seconds <= 0 or args.timeout_seconds <= 0 or not 1 <= args.max_mutants <= 100:
            raise InputError("Use positive time budgets and max-mutants between 1 and 100")
        report, bundle = compare(
            plan, before, after, budget_seconds=args.budget_seconds,
            max_mutants=args.max_mutants, timeout_seconds=args.timeout_seconds,
            python_executable=args.python_executable,
        )
        show(report, args.output)
        write_bundle(bundle, args.output)
        return exit_code(report, args.advisory)
    except (InputError, ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as exc:
        print(f"TestDelta could not complete: {exc}", file=sys.stderr)
        return 3
