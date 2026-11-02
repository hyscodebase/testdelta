import subprocess

import pytest

from testdelta.adapters.bounded import generate_bounded


def test_actual_provider_worker_can_be_timed_out(tmp_path):
    (tmp_path / "calc.py").write_text("def add(x):\n    return x + 1\n")
    with pytest.raises(subprocess.TimeoutExpired):
        generate_bounded(tmp_path, ["calc.py"], 3, 0.001)


def test_actual_provider_worker_returns_recorded_sources(tmp_path):
    source = "def add(x):\n    return x + 1\n"
    (tmp_path / "calc.py").write_text(source)
    records = generate_bounded(tmp_path, ["calc.py"], 3, 15)
    assert len(records) == 3
    assert all(m["provider"] == "cosmic-ray" for m in records)
    assert all(m["original_source"] == source for m in records)
    assert (tmp_path / "calc.py").read_text() == source
