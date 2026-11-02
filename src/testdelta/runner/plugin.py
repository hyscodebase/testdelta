"""Pytest evidence collector loaded by the external TestDelta supervisor.

Project tests remain trusted code: this collector detects mistakes, not a
malicious test deliberately forging the evidence or disabling tracing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import sys
import threading
from pathlib import Path
from types import FrameType
from typing import Any

import pytest
from _pytest.outcomes import Failed


class _Evidence:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.workspace = Path(config["workspace"]).resolve()
        self.targets = {
            str((self.workspace / name).resolve()): name
            for name in config["expected_source_hashes"]
        }
        self.module_targets: dict[str, set[str]] = {}
        for relative in config["expected_source_hashes"]:
            parts = list(Path(relative).with_suffix("").parts)
            variants = [parts]
            if parts and parts[0] == "src":
                variants.append(parts[1:])
            for variant in variants:
                if variant and variant[-1] == "__init__":
                    variant = variant[:-1]
                if variant:
                    self.module_targets.setdefault(".".join(variant), set()).add(relative)
        self.data: dict[str, Any] = {
            "schema_version": 1,
            "run_id": config["run_id"],
            "workspace": str(self.workspace),
            "collected": [],
            "ran": [],
            "skipped": [],
            "assertion_failure_nodes": [],
            "collection_errors": [],
            "fixture_errors": [],
            "runtime_errors": [],
            "origin_mismatches": [],
            "finished": False,
            "runtime": {
                "python_version": platform.python_version(),
                "python_executable": sys.executable,
                "pytest_version": pytest.__version__,
            },
        }
        self.lines: dict[str, set[int]] = {name: set() for name in config["expected_source_hashes"]}
        self.origins: dict[str, set[str]] = {name: set() for name in config["expected_source_hashes"]}
        self.previous_trace = None
        self.previous_thread_trace = None

    def _observe_origin(self, module_name: str, filename: str) -> str | None:
        if not filename or filename.startswith("<"):
            return None
        path = str(Path(filename).resolve())
        if path.endswith((".pyc", ".pyo")):
            try:
                path = str(Path(importlib.util.source_from_cache(path)).resolve())
            except ValueError:
                pass
        direct = self.targets.get(path)
        if direct:
            self.origins[direct].add(path)
        for expected in self.module_targets.get(module_name, ()):
            self.origins[expected].add(path)
            wanted = str((self.workspace / expected).resolve())
            if path != wanted:
                mismatch = {"module": module_name, "expected": wanted, "observed": path}
                if mismatch not in self.data["origin_mismatches"]:
                    self.data["origin_mismatches"].append(mismatch)
        return direct

    def trace(self, frame: FrameType, event: str, arg: Any):
        if event not in {"call", "line"}:
            return self.trace
        filename = frame.f_code.co_filename
        # Most Python calls are pytest's own implementation. Avoid resolving
        # their paths on every line; global tracing still sees nested calls.
        module = str(frame.f_globals.get("__name__", ""))
        if filename not in self.targets and module not in self.module_targets:
            return None
        relative = self._observe_origin(module, filename)
        if relative is not None:
            if event == "line":
                self.lines[relative].add(frame.f_lineno)
            return self.trace
        return None

    def inspect_modules(self) -> None:
        for name, module in list(sys.modules.items()):
            if name in self.module_targets:
                filename = getattr(module, "__file__", None)
                if isinstance(filename, str):
                    self._observe_origin(name, filename)

    def write(self) -> None:
        self.inspect_modules()
        self.data["reached_lines"] = {key: sorted(value) for key, value in self.lines.items()}
        self.data["observed_source_origin"] = {key: sorted(value) for key, value in self.origins.items()}
        output = Path(self.config["evidence_path"])
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        temporary.replace(output)


_state: _Evidence | None = None


def pytest_configure(config):
    global _state
    config_path = os.environ.get("TESTDELTA_RUN_CONFIG")
    if config_path:
        _state = _Evidence(json.loads(Path(config_path).read_text(encoding="utf-8")))


def pytest_sessionstart(session):
    if _state is None:
        return
    _state.previous_trace = sys.gettrace()
    _state.previous_thread_trace = threading.gettrace()
    sys.settrace(_state.trace)
    threading.settrace(_state.trace)


def pytest_collection_finish(session):
    if _state is not None:
        _state.data["collected"] = [item.nodeid for item in session.items]


def pytest_collectreport(report):
    if _state is not None:
        if report.failed:
            _state.data["collection_errors"].append({"nodeid": report.nodeid, "detail": str(report.longrepr)[-8000:]})
        elif report.skipped and report.nodeid not in _state.data["skipped"]:
            # importorskip/allow_module_level skip never produces a test call.
            _state.data["skipped"].append(report.nodeid)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if _state is None:
        return
    report = outcome.get_result()
    if report.skipped or hasattr(report, "wasxfail"):
        if report.nodeid not in _state.data["skipped"]:
            _state.data["skipped"].append(report.nodeid)
    if report.when == "call" and not report.skipped:
        _state.data["ran"].append(report.nodeid)
    if report.failed:
        detail = {"nodeid": report.nodeid, "phase": report.when, "detail": str(report.longrepr)[-8000:]}
        if report.when != "call":
            _state.data["fixture_errors"].append(detail)
        elif call.excinfo is not None and isinstance(call.excinfo.value, (AssertionError, Failed)):
            _state.data["assertion_failure_nodes"].append(report.nodeid)
        else:
            _state.data["runtime_errors"].append(detail)
    _state.inspect_modules()


def pytest_internalerror(excrepr, excinfo):
    if _state is not None:
        _state.data["runtime_errors"].append({"nodeid": "", "phase": "internal", "detail": str(excrepr)[-8000:]})


def pytest_sessionfinish(session, exitstatus):
    if _state is not None:
        sys.settrace(_state.previous_trace)
        threading.settrace(_state.previous_thread_trace)
        _state.data["finished"] = True
        _state.data["pytest_exitstatus"] = int(exitstatus)
        _state.write()
