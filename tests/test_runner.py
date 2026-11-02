"""Runner behavior tests using real pytest subprocesses, not mocked reports."""

from __future__ import annotations

import hashlib
import os
import platform
import py_compile
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from testdelta.runner import run_pytest
from testdelta.runner.plugin import _Evidence


def project(tmp_path: Path, tests: str, source: str = "def discount(value):\n    return value * 0.1\n"):
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "pricing.py").write_text(source, encoding="utf-8")
    (workspace / "test_pricing.py").write_text(tests, encoding="utf-8")
    hashes = {"pricing.py": hashlib.sha256(source.encode()).hexdigest()}
    return workspace, hashes


def execute(workspace, hashes, timeout=15):
    return run_pytest(workspace, ["test_pricing.py"], timeout, hashes)


def test_valid_execution_reports_real_origin_and_reached_lines(tmp_path):
    workspace, hashes = project(tmp_path, "from pricing import discount\ndef test_discount():\n    assert discount(100) == 10\n")
    result = execute(workspace, hashes)
    assert result["status"] == "pass", result
    assert result["collected"] == ["test_pricing.py::test_discount"]
    assert result["ran"] == result["collected"]
    assert result["observed_source_origin"]["pricing.py"] == [str(workspace / "pricing.py")]
    assert 2 in result["reached_lines"]["pricing.py"]
    assert result["source_hashes_before"] == result["source_hashes_after"] == hashes


def test_assertion_failure_is_distinct_from_runtime_error(tmp_path):
    workspace, hashes = project(tmp_path, "from pricing import discount\ndef test_discount():\n    assert discount(100) == 11\n")
    assertion = execute(workspace, hashes)
    assert assertion["status"] == "assertion_failure", assertion
    assert assertion["assertion_failure_nodes"] == ["test_pricing.py::test_discount"]
    (workspace / "test_pricing.py").write_text("def test_discount():\n    raise ValueError('not an assertion')\n")
    runtime = execute(workspace, hashes)
    assert runtime["status"] == "runtime_error", runtime
    assert runtime["assertion_failure_nodes"] == []


def test_missing_expected_exception_is_assertion_failure(tmp_path):
    workspace, hashes = project(tmp_path, "import pytest\nfrom pricing import discount\ndef test_discount():\n    with pytest.raises(ValueError):\n        discount(100)\n")
    result = execute(workspace, hashes)
    assert result["status"] == "assertion_failure", result


@pytest.mark.parametrize(
    ("content", "status"),
    [
        ("import missing_testdelta_fixture_module\ndef test_one():\n    pass\n", "collection_error"),
        ("import pytest\n@pytest.fixture\ndef broken():\n    raise AssertionError('setup failure')\ndef test_one(broken):\n    pass\n", "fixture_error"),
        ("import pytest\n@pytest.fixture\ndef broken():\n    yield\n    raise AssertionError('teardown failure')\ndef test_one(broken):\n    pass\n", "fixture_error"),
        ("import pytest\n@pytest.mark.skip(reason='disabled')\ndef test_one():\n    pass\n", "not_executed"),
        ("# no collected tests\n", "not_executed"),
        ("import pytest\ndef test_one():\n    pytest.exit('early', returncode=0)\ndef test_two():\n    pass\n", "not_executed"),
        ("import pytest\n@pytest.mark.xfail\ndef test_one():\n    assert False\n", "not_executed"),
    ],
)
def test_non_measurements_never_become_kills_or_passes(tmp_path, content, status):
    workspace, hashes = project(tmp_path, content)
    result = execute(workspace, hashes)
    assert result["status"] == status, result


def test_source_does_not_need_to_be_imported_for_valid_survival(tmp_path):
    workspace, hashes = project(tmp_path, "def test_unrelated():\n    assert 1 == 1\n")
    result = execute(workspace, hashes)
    assert result["status"] == "pass", result
    assert result["reached_lines"] == {"pricing.py": []}


def test_importing_original_checkout_invalidates_evidence(tmp_path):
    outside = tmp_path / "original"
    outside.mkdir()
    (outside / "pricing.py").write_text("def discount(value):\n    return 10\n")
    workspace, hashes = project(tmp_path, f"import sys\nsys.path.insert(0, {str(outside)!r})\nfrom pricing import discount\ndef test_discount():\n    assert discount(100) == 10\n")
    result = execute(workspace, hashes)
    assert result["status"] == "invalid_evidence", result
    assert result["origin_mismatches"][0]["observed"] == str(outside / "pricing.py")


@pytest.mark.parametrize("source_path,module_name", [("lib/calc.py", "calc"), ("lib/project/__init__.py", "project")])
def test_non_src_layout_importing_original_checkout_invalidates_evidence(tmp_path, source_path, module_name):
    workspace = tmp_path / "snapshot"
    target = workspace / source_path
    target.parent.mkdir(parents=True)
    source = b"def calculate():\n    return 999\n"
    target.write_bytes(source)
    original = tmp_path / "original"
    outside_source = original / Path(source_path).relative_to("lib")
    outside_source.parent.mkdir(parents=True)
    outside_source.write_text("def calculate():\n    return 2\n")
    (workspace / "test_calc.py").write_text(
        f"import sys\nsys.path.insert(0, {str(original)!r})\n"
        f"from {module_name} import calculate\n"
        "def test_calculate():\n    assert calculate() == 2\n"
    )

    result = run_pytest(workspace, ["test_calc.py"], 10, {source_path: hashlib.sha256(source).hexdigest()})

    assert result["status"] == "invalid_evidence", result
    assert result["origin_mismatches"][0]["observed"] == str(outside_source)


def test_non_src_layout_with_correct_workspace_import_is_valid(tmp_path):
    workspace = tmp_path / "snapshot"
    (workspace / "lib").mkdir(parents=True)
    source = b"def calculate():\n    return 2\n"
    (workspace / "lib/calc.py").write_bytes(source)
    (workspace / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent / 'lib'))\n"
    )
    (workspace / "test_calc.py").write_text(
        "from calc import calculate\ndef test_calculate():\n    assert calculate() == 2\n"
    )
    result = run_pytest(workspace, ["test_calc.py"], 10, {"lib/calc.py": hashlib.sha256(source).hexdigest()})
    assert result["status"] == "pass", result
    assert result["observed_source_origin"]["lib/calc.py"] == [str(workspace / "lib/calc.py")]
    assert 2 in result["reached_lines"]["lib/calc.py"]


def test_explicit_import_root_inside_package_still_detects_outside_shadow(tmp_path):
    workspace = tmp_path / "snapshot"
    package = workspace / "package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    source = b"def calculate():\n    return 999\n"
    (package / "calc.py").write_bytes(source)
    outside = tmp_path / "original"
    outside.mkdir()
    (outside / "calc.py").write_text("def calculate():\n    return 2\n")
    (workspace / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent / 'package'))\n"
    )
    (workspace / "test_calc.py").write_text(
        f"import sys\nsys.path.insert(0, {str(outside)!r})\n"
        "from calc import calculate\ndef test_calculate():\n    assert calculate() == 2\n"
    )
    result = run_pytest(workspace, ["test_calc.py"], 10, {"package/calc.py": hashlib.sha256(source).hexdigest()})
    assert result["status"] == "invalid_evidence", result
    assert result["origin_mismatches"][0]["observed"] == str(outside / "calc.py")


@pytest.mark.parametrize("regular_package", [True, False], ids=["regular-package", "namespace-package"])
@pytest.mark.parametrize("import_target", [True, False], ids=["imported-target", "unused-target"])
def test_package_json_does_not_conflict_with_unrelated_stdlib_json(tmp_path, regular_package, import_target):
    workspace = tmp_path / "snapshot"
    (workspace / "package").mkdir(parents=True)
    if regular_package:
        (workspace / "package/__init__.py").write_text("")
    source = b"def calculate():\n    return 2\n"
    (workspace / "package/json.py").write_bytes(source)
    tests = "import json\n"
    if import_target:
        tests += "from package.json import calculate\ndef test_json():\n    assert json.loads('2') == calculate()\n"
    else:
        tests += "def test_json():\n    assert json.loads('2') == 2\n"
    (workspace / "test_json.py").write_text(tests)
    result = run_pytest(workspace, ["test_json.py"], 10, {"package/json.py": hashlib.sha256(source).hexdigest()})
    assert result["status"] == "pass", result
    assert result["origin_mismatches"] == []
    if import_target:
        assert 2 in result["reached_lines"]["package/json.py"]
    else:
        assert result["reached_lines"] == {"package/json.py": []}


def test_repeated_target_line_events_do_not_repeat_path_resolution(tmp_path, monkeypatch):
    source_path = tmp_path / "calc.py"
    source_path.write_text("def calculate():\n    return 2\n")
    evidence = _Evidence({
        "workspace": str(tmp_path), "expected_source_hashes": {"calc.py": "unused-by-collector"},
        "run_id": "hot-path-test", "evidence_path": str(tmp_path / "evidence.json"),
    })
    frame = SimpleNamespace(f_code=SimpleNamespace(co_filename=str(source_path)),
                            f_globals={"__name__": "calc"}, f_lineno=2)
    evidence.trace(frame, "call", None)

    def forbidden_resolution(*args, **kwargs):
        raise AssertionError("Known target line events must not resolve filesystem paths")

    monkeypatch.setattr(Path, "resolve", forbidden_resolution)
    for _ in range(1000):
        evidence.trace(frame, "line", None)
    assert evidence.lines["calc.py"] == {2}
    assert evidence.origins["calc.py"] == {str(source_path)}


def test_hash_mismatch_prevents_execution(tmp_path):
    workspace, hashes = project(tmp_path, "raise RuntimeError('must not run')\n")
    result = execute(workspace, {"pricing.py": "0" * 64})
    assert result["status"] == "invalid_evidence"
    assert result["returncode"] is None


def test_source_modification_during_test_invalidates_pass(tmp_path):
    workspace, hashes = project(tmp_path, "from pathlib import Path\ndef test_changes_source():\n    Path('pricing.py').write_text('# changed')\n")
    result = execute(workspace, hashes)
    assert result["status"] == "invalid_evidence", result
    assert result["source_hashes_after"] != hashes


def test_stale_unchecked_hash_bytecode_cannot_hide_changed_source(tmp_path):
    original = "def discount(value):\n    return value + 1\n"
    mutated = "def discount(value):\n    return value + 2\n"
    workspace, _ = project(
        tmp_path,
        "from pricing import discount\ndef test_discount():\n    assert discount(1) == 2\n",
        source=original,
    )
    source_path = workspace / "pricing.py"
    cache_path = py_compile.compile(
        str(source_path), doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    assert cache_path is not None and Path(cache_path).is_file()
    source_path.write_text(mutated, encoding="utf-8")
    hashes = {"pricing.py": hashlib.sha256(mutated.encode()).hexdigest()}

    result = execute(workspace, hashes)

    assert result["status"] == "assertion_failure", result
    assert result["source_hashes_before"] == result["source_hashes_after"] == hashes
    assert result["observed_source_origin"]["pricing.py"] == [str(source_path)]
    assert 2 in result["reached_lines"]["pricing.py"]
    assert Path(cache_path).is_file(), "The runner must not delete caller-owned caches"


def test_parent_credentials_and_pytest_addopts_are_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "example-not-a-secret")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--does-not-exist")
    workspace, hashes = project(tmp_path, "import os\ndef test_environment():\n    assert 'GITHUB_TOKEN' not in os.environ\n    assert 'PYTEST_ADDOPTS' not in os.environ\n")
    result = execute(workspace, hashes)
    assert result["status"] == "pass", result


def test_timeout_is_never_a_kill(tmp_path):
    workspace, hashes = project(tmp_path, "import time\ndef test_waits():\n    time.sleep(30)\n")
    result = execute(workspace, hashes, timeout=0.8)
    assert result["status"] == "timeout", result
    assert result["duration_seconds"] < 5


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_timeout_never_starts_process(tmp_path, timeout):
    workspace, hashes = project(tmp_path, "raise RuntimeError('must not run')\n")
    result = execute(workspace, hashes, timeout=timeout)
    assert result["status"] == "invalid_evidence"
    assert result["returncode"] is None


def test_explicit_interpreter_is_used(tmp_path):
    workspace, hashes = project(tmp_path, "def test_one():\n    pass\n")
    result = run_pytest(workspace, ["test_pricing.py"], 10, hashes, python_executable="/no/such/python")
    assert result["status"] == "runtime_error"
    assert result["command"][0] == "/no/such/python"


def test_runtime_metadata_comes_from_child_interpreter(tmp_path):
    workspace, hashes = project(tmp_path, "def test_one():\n    pass\n")
    result = run_pytest(workspace, ["test_pricing.py"], 10, hashes, python_executable=sys.executable)
    assert result["status"] == "pass", result
    assert result["runtime"] == {
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "pytest_version": pytest.__version__,
    }


def test_module_skip_with_other_passing_tests_is_incomplete(tmp_path):
    workspace, hashes = project(tmp_path, "def test_one():\n    pass\n")
    (workspace / "test_optional.py").write_text("import pytest\npytest.skip('module unavailable', allow_module_level=True)\n")
    result = run_pytest(workspace, ["test_pricing.py", "test_optional.py"], 10, hashes)
    assert result["status"] == "not_executed", result
    assert result["ran"] == ["test_pricing.py::test_one"]
    assert "test_optional.py" in result["skipped"]


@pytest.mark.skipif(os.name != "posix", reason="process-group cleanup is POSIX-only")
def test_timeout_cleans_up_descendant_processes(tmp_path):
    workspace, hashes = project(tmp_path, "import subprocess, sys, time\ndef test_spawns_child():\n    subprocess.Popen([sys.executable, '-c', \"import time; from pathlib import Path; time.sleep(2); Path('descendant-survived').write_text('unexpected')\"])\n    time.sleep(30)\n")
    result = execute(workspace, hashes, timeout=0.8)
    assert result["status"] == "timeout", result
    time.sleep(1.5)
    assert not (workspace / "descendant-survived").exists(), result
