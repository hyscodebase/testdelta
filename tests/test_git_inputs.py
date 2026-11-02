import subprocess
from pathlib import Path

import pytest

from testdelta.git_inputs import InputError, make_plan, read_tree, resolve


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/calc.py").write_text("def add(x):\n    return x + 1\n")
    (tmp_path / "tests/test_calc.py").write_text("def test_old():\n    assert True\n")
    (tmp_path / ".testdelta.toml").write_text(
        'source_modules=["src/calc.py"]\ntest_paths=["tests"]\n'
    )

    def commit():
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c",
                        "user.email=test@example.invalid", "commit", "-qm", "snapshot"], check=True)
    commit()
    return tmp_path, commit


def test_test_only_plan_ignores_dirty_checkout(repository):
    repo, commit = repository
    (repo / "tests/test_calc.py").write_text("def test_new():\n    assert True\n")
    commit()
    (repo / "src/calc.py").write_text("raise RuntimeError('dirty file must never execute')")
    plan, _, after = make_plan(repo, "HEAD~1")
    assert plan["supported"]
    assert b"dirty" not in after["src/calc.py"]


@pytest.mark.parametrize("path", ["src/calc.py", "tests/conftest.py", "tests/helper.py", "pyproject.toml"])
def test_changes_outside_declared_tests_are_not_compared(repository, path):
    repo, commit = repository
    (repo / path).write_text("# changed\n")
    commit()
    plan, _, _ = make_plan(repo, "HEAD~1")
    assert not plan["supported"]
    assert path in plan["unsupported_changes"]


def test_export_ignore_cannot_hide_source_changes(repository):
    repo, commit = repository
    (repo / ".gitattributes").write_text("src/calc.py export-ignore\n")
    commit()
    before_sha = resolve(repo, "HEAD")
    assert "src/calc.py" in read_tree(repo, before_sha)
    (repo / "src/calc.py").write_text("# changed\n")
    commit()
    plan, _, _ = make_plan(repo, before_sha)
    assert not plan["supported"]


def test_symlink_is_not_exported(repository):
    repo, commit = repository
    (repo / "link").symlink_to(Path("src/calc.py"))
    commit()
    with pytest.raises(InputError, match="Symlinks"):
        read_tree(repo, resolve(repo, "HEAD"))


def test_deleted_source_is_an_explicit_unsupported_plan(repository):
    repo, commit = repository
    (repo / "src/calc.py").unlink()
    commit()
    plan, _, _ = make_plan(repo, "HEAD~1")
    assert not plan["supported"]
    assert plan["unsupported_changes"] == ["src/calc.py"]
    assert plan["source_hashes"]["src/calc.py"] is None
