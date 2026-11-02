import hashlib
import json

import pytest

from testdelta.cli import main
from testdelta.git_inputs import InputError, materialize, safe_path


@pytest.mark.parametrize("value", [".", "", "../outside", "/absolute", ".git/config"])
def test_unsupported_paths_raise_input_error(value):
    with pytest.raises(InputError):
        safe_path(value)


def test_nonobject_bundle_is_a_controlled_input_error(tmp_path, capsys):
    content = json.dumps([]).encode()
    (tmp_path / "bundle.json").write_bytes(content)
    (tmp_path / "bundle.sha256").write_text(hashlib.sha256(content).hexdigest())
    assert main(["replay", str(tmp_path), "--witness", "unused"]) == 3
    assert "JSON object" in capsys.readouterr().err


def test_materialization_does_not_copy_cached_bytecode(tmp_path):
    materialize({"calc.py": b"x = 1", "__pycache__/calc.cpython-313.pyc": b"cache",
                 "legacy.pyc": b"cache"}, tmp_path)
    assert (tmp_path / "calc.py").read_bytes() == b"x = 1"
    assert not (tmp_path / "__pycache__").exists()
    assert not (tmp_path / "legacy.pyc").exists()
