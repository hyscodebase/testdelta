"""GitHub composite Action adapter; project tests use the caller's interpreter."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Mapping

from testdelta.cli import main as cli_main
from testdelta.report import exit_code

_PREFIX = "TESTDELTA_INPUT_"
_VERDICTS = {"no_loss_observed", "loss_observed", "incomplete_with_witnesses", "inconclusive", "unsupported_change"}


def resolve_python(value: str) -> str:
    """Keep venv symlinks intact: resolving their real path loses their environment."""
    executable = shutil.which(value)
    if not executable:
        raise ValueError(f"Target Python executable was not found: {value!r}")
    return os.path.abspath(executable)


def arguments(environ: Mapping[str, str]) -> tuple[list[str], Path, bool]:
    def value(name: str, default: str = "") -> str:
        return environ.get(_PREFIX + name, default)

    base = value("BASE")
    if not base:
        raise ValueError("The base input is required")
    advisory_value = value("ADVISORY", "false").lower()
    if advisory_value not in {"true", "false"}:
        raise ValueError("The advisory input must be true or false")
    advisory = advisory_value == "true"
    target = environ.get("TESTDELTA_TARGET_PYTHON") or resolve_python(value("PYTHON", "python"))
    output = Path(value("OUTPUT", ".testdelta/report")).absolute()
    # Equals-form arguments also keep option-looking input values from becoming flags.
    argv = [
        "compare",
        "--repo=" + value("REPO", "."),
        "--base=" + base,
        "--head=" + value("HEAD", "HEAD"),
        "--output=" + str(output),
        "--budget-seconds=" + value("BUDGET_SECONDS", "120"),
        "--timeout-seconds=" + value("TIMEOUT_SECONDS", "15"),
        "--max-mutants=" + value("MAX_MUTANTS", "10"),
        "--python=" + target,
    ]
    if value("CONFIG"):
        argv.append("--config=" + value("CONFIG"))
    if advisory:
        argv.append("--advisory")
    return argv, output / "report.json", advisory


def _signature(path: Path) -> tuple | None:
    try:
        data = path.read_bytes()
        stat = path.stat()
        return stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, hashlib.sha256(data).digest()
    except FileNotFoundError:
        return None


def _outputs(path: str | None, values: Mapping[str, str]) -> None:
    if not path:
        return
    # Paths can contain newlines. A collision-checked delimiter prevents a path
    # from appending new outputs or workflow commands to GITHUB_OUTPUT.
    with open(path, "a", encoding="utf-8", newline="\n") as stream:
        for name, value in values.items():
            while True:
                delimiter = "testdelta_" + uuid.uuid4().hex
                if delimiter not in value.splitlines():
                    break
            stream.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def main(environ: Mapping[str, str] | None = None) -> int:
    environ = os.environ if environ is None else environ
    values = {"verdict": "error", "complete": "false", "report-path": ""}
    code = 3
    try:
        argv, report_path, advisory = arguments(environ)
        previous = _signature(report_path)
        try:
            code = cli_main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 3
        if not isinstance(code, int) or isinstance(code, bool):
            code = 3
            raise ValueError("The CLI did not return an integer exit code")
        current = _signature(report_path)
        if current is None or current == previous:
            raise ValueError("The comparison did not produce a fresh report.json")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (
            not isinstance(report, dict)
            or report.get("verdict") not in _VERDICTS
            or not isinstance(report.get("complete"), bool)
        ):
            raise ValueError("The comparison produced an invalid report.json")
        expected = exit_code(report, advisory)
        if code != expected:
            # Even a plausible report must not turn a CLI error into clean output.
            if code == 0:
                code = expected or 3
            raise ValueError("The comparison exit code does not match its report")
        values = {
            "verdict": report["verdict"],
            "complete": str(report["complete"]).lower(),
            "report-path": str(report_path),
        }
    except Exception as exc:
        print(f"TestDelta Action could not complete: {exc}", file=sys.stderr)
        if code == 0:
            code = 3
    try:
        _outputs(environ.get("GITHUB_OUTPUT"), values)
    except OSError as exc:
        print(f"TestDelta Action could not write outputs: {exc}", file=sys.stderr)
        if code == 0:
            code = 3
    return code


if __name__ == "__main__":
    raise SystemExit(main())
