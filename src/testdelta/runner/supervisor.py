"""Supervise pytest and qualify evidence for trusted local repositories.

An isolated working directory is not a sandbox. Target tests retain the host
user's OS privileges; only environment inheritance and process lifetime are
restricted here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

_OUTPUT_LIMIT = 12000
_ENV_ALLOWLIST = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TMP", "TEMP", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "TZ"}


def _trim(text: str | None) -> str:
    text = text or ""
    if len(text) <= _OUTPUT_LIMIT:
        return text
    half = _OUTPUT_LIMIT // 2
    return text[:half] + "\n[output truncated]\n" + text[-half:]


def _hash_sources(workspace: Path, expected: dict[str, str]) -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative in expected:
        path = workspace / relative
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"source path must be relative and contained: {relative}")
        resolved = path.resolve()
        if not resolved.is_relative_to(workspace) or path.is_symlink():
            raise ValueError(f"source path escapes workspace or is a symlink: {relative}")
        actual[relative] = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return actual


def _stop_process_group(process: subprocess.Popen[str]) -> list[str]:
    errors: list[str] = []
    if os.name == "posix":
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                break
            except PermissionError as error:
                # macOS can report EPERM after the session leader exits. Do
                # not let a cleanup race overwrite a genuine timeout. A
                # still-running leader gets a direct kill as a fallback.
                errors.append(f"process group cleanup: {error}")
                if process.poll() is None:
                    try:
                        process.kill()
                    except OSError as kill_error:
                        errors.append(f"process cleanup: {kill_error}")
                break
            if sig == signal.SIGTERM:
                time.sleep(0.1)
    elif process.poll() is None:
        process.kill()
    return errors


def _classify(data: dict[str, Any], returncode: int) -> str:
    if data.get("origin_mismatches"):
        return "invalid_evidence"
    if data.get("collection_errors"):
        return "collection_error"
    if data.get("fixture_errors"):
        return "fixture_error"
    if data.get("runtime_errors") or returncode not in (0, 1, 5):
        return "runtime_error"
    if not data.get("ran") or data.get("skipped") or data.get("missing_test_ids"):
        return "not_executed"
    if data.get("assertion_failure_nodes"):
        return "assertion_failure"
    return "pass" if returncode == 0 else "runtime_error"


def run_pytest(
    workspace: Path,
    test_paths: list[str],
    timeout_seconds: float,
    expected_source_hashes: dict[str, str],
    python_executable: str | None = None,
) -> dict[str, Any]:
    """Run actual pytest with bounded lifetime and independently checked hashes.

    Any skip/xfail makes this initial runner incomplete. Assertion failures do
    not by themselves prove a mutant was reached: callers must also inspect
    ``reached_lines`` when establishing a witness.
    """
    started = time.monotonic()
    workspace = Path(workspace).resolve()
    executable = python_executable or sys.executable
    command = [executable, "-m", "pytest", "-p", "testdelta.runner.plugin", "-q", "--disable-warnings", "--import-mode=importlib", "--", *test_paths]
    result: dict[str, Any] = {
        "status": "invalid_evidence", "collected": [], "ran": [],
        "assertion_failure_nodes": [], "observed_source_origin": {},
        "reached_lines": {}, "duration_seconds": 0.0, "stdout": "", "stderr": "",
        "command": command, "skipped": [], "missing_test_ids": [],
        "origin_mismatches": [], "source_hashes_before": {}, "source_hashes_after": {},
        "evidence_finished": False, "returncode": None, "cleanup_errors": [],
    }

    def finish() -> dict[str, Any]:
        result["duration_seconds"] = time.monotonic() - started
        return result

    try:
        if not workspace.is_dir() or not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or not test_paths or not expected_source_hashes:
            raise ValueError("workspace, test paths, positive timeout and source hashes are required")
        for relative in test_paths:
            # Node IDs are allowed, but no pytest options or paths outside the
            # snapshot may be smuggled into the command.
            path_part = relative.split("::", 1)[0]
            if relative.startswith("-") or Path(path_part).is_absolute() or ".." in Path(path_part).parts:
                raise ValueError(f"test path must be relative and contained: {relative}")
            if not (workspace / path_part).resolve().is_relative_to(workspace):
                raise ValueError(f"test path escapes workspace: {relative}")
        result["source_hashes_before"] = _hash_sources(workspace, expected_source_hashes)
        if result["source_hashes_before"] != expected_source_hashes:
            raise ValueError("source hashes do not match before execution")
    except (ValueError, OSError) as error:
        result["stderr"] = str(error)
        return finish()

    with tempfile.TemporaryDirectory(prefix="testdelta-evidence-") as directory:
        config_path = Path(directory) / "config.json"
        evidence_path = Path(directory) / "evidence.json"
        run_id = uuid.uuid4().hex
        config_path.write_text(json.dumps({
            "run_id": run_id, "workspace": str(workspace),
            "expected_source_hashes": expected_source_hashes,
            "evidence_path": str(evidence_path),
        }), encoding="utf-8")
        tool_src = Path(__file__).resolve().parents[2]
        python_paths = [str(tool_src), str(workspace)]
        if (workspace / "src").is_dir():
            python_paths.append(str(workspace / "src"))
        environment = {key: value for key, value in os.environ.items() if key in _ENV_ALLOWLIST}
        environment.update({
            "PYTHONPATH": os.pathsep.join(python_paths),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
            # DONTWRITEBYTECODE suppresses writes, not reads. An unchecked-hash
            # cache may otherwise execute old code despite valid source hashes
            # and co_filename origins. Redirect reads to this fresh run's tree.
            "PYTHONPYCACHEPREFIX": str(Path(directory) / "pycache"),
            "TESTDELTA_RUN_CONFIG": str(config_path),
        })
        timed_out = False
        try:
            process = subprocess.Popen(
                command, cwd=workspace, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", start_new_session=(os.name == "posix"),
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                result["cleanup_errors"].extend(_stop_process_group(process))
                stdout, stderr = process.communicate(timeout=3)
            finally:
                # Also clean up ordinary descendants after pytest exits.
                if not timed_out:
                    result["cleanup_errors"].extend(_stop_process_group(process))
            result.update(stdout=_trim(stdout), stderr=_trim(stderr), returncode=process.returncode)
        except (OSError, subprocess.SubprocessError) as error:
            result.update(status="timeout" if timed_out else "runtime_error", stderr=_trim(str(error)))
            return finish()
        try:
            result["source_hashes_after"] = _hash_sources(workspace, expected_source_hashes)
        except (OSError, ValueError) as error:
            result["stderr"] += "\nSource verification failed: " + str(error)
        if timed_out:
            result["status"] = "timeout"
            return finish()
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            if evidence.get("run_id") != run_id or evidence.get("schema_version") != 1 or not evidence.get("finished"):
                raise ValueError("missing or mismatched completed runner evidence")
            for field in ("collected", "ran", "skipped", "assertion_failure_nodes", "collection_errors", "fixture_errors", "runtime_errors", "origin_mismatches"):
                if not isinstance(evidence.get(field), list):
                    raise ValueError(f"invalid runner evidence field: {field}")
            for field in ("observed_source_origin", "reached_lines"):
                if not isinstance(evidence.get(field), dict):
                    raise ValueError(f"invalid runner evidence field: {field}")
            result.update({key: evidence[key] for key in evidence if key not in {"run_id", "workspace", "schema_version", "finished"}})
            result["evidence_finished"] = True
            result["missing_test_ids"] = sorted(set(result["collected"]) - set(result["ran"]))
            result["status"] = _classify(result, process.returncode)
        except (OSError, ValueError, TypeError) as error:
            result["status"] = "invalid_evidence"
            result["stderr"] += "\n" + str(error)
        if result["source_hashes_after"] != expected_source_hashes:
            result["status"] = "invalid_evidence"
            result["stderr"] += "\nSource hashes changed during execution."
        return finish()
