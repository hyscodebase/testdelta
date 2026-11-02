import subprocess
from pathlib import Path

import pytest

from testdelta.git_inputs import InputError, digest, load_manifest, make_plan, read_tree, resolve

MANIFEST = b'source_modules=["src/calc.py"]\ntest_paths=["tests"]\n'


def create_repository(tmp_path, *, include_manifest=True):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/calc.py").write_text("def add(x):\n    return x + 1\n")
    (tmp_path / "tests/test_calc.py").write_text("def test_old():\n    assert True\n")
    if include_manifest:
        (tmp_path / ".testdelta.toml").write_bytes(MANIFEST)

    def commit():
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c",
                        "user.email=test@example.invalid", "commit", "-qm", "snapshot"], check=True)
    commit()
    return tmp_path, commit


@pytest.fixture
def repository(tmp_path):
    return create_repository(tmp_path)


def test_test_only_plan_ignores_dirty_checkout(repository):
    repo, commit = repository
    (repo / "tests/test_calc.py").write_text("def test_new():\n    assert True\n")
    commit()
    (repo / "src/calc.py").write_text("raise RuntimeError('dirty file must never execute')")
    plan, _, after = make_plan(repo, "HEAD~1")
    assert plan["supported"]
    assert plan["manifest_origin"] == "base_commit"
    assert plan["manifest_hash"] == digest(MANIFEST)
    assert "manifest_snapshot" not in plan
    assert b"dirty" not in after["src/calc.py"]


@pytest.mark.parametrize("manifest_bytes", [None, MANIFEST], ids=["base_commit", "external"])
@pytest.mark.parametrize("path", [
    "src/calc.py", "tests/conftest.py", "tests/helper.py", "pyproject.toml", ".testdelta.toml",
])
def test_changes_outside_declared_tests_are_not_compared(repository, path, manifest_bytes):
    repo, commit = repository
    (repo / path).write_text("# changed\n")
    commit()
    plan, _, _ = make_plan(repo, "HEAD~1", manifest_bytes=manifest_bytes)
    assert not plan["supported"]
    assert path in plan["unsupported_changes"]


def test_external_manifest_plans_existing_test_only_commits_without_base_config(tmp_path):
    repo, commit = create_repository(tmp_path, include_manifest=False)
    (repo / "tests/test_calc.py").write_text("def test_new():\n    assert True\n")
    commit()
    external = b'# External scope\r\nsource_modules=["src/calc.py"]\r\ntest_paths=["tests"]\r\n'

    plan, before, after = make_plan(repo, "HEAD~1", manifest_bytes=external)

    assert plan["supported"]
    assert plan["manifest"] == {"source_modules": ["src/calc.py"], "test_paths": ["tests"]}
    assert plan["manifest_origin"] == "external"
    assert plan["manifest_hash"] == digest(external)
    assert plan["manifest_snapshot"] == {"text": external.decode("utf-8"),
                                         "sha256": digest(external)}
    assert plan["source_hashes"] == {"src/calc.py": digest(before["src/calc.py"])}
    assert before["src/calc.py"] == after["src/calc.py"]
    assert plan["test_hashes"] == {"tests/test_calc.py": {
        "old": digest(before["tests/test_calc.py"]), "new": digest(after["tests/test_calc.py"]),
    }}
    assert plan["changed_files"] == ["tests/test_calc.py"]
    assert ".testdelta.toml" not in before
    assert ".testdelta.toml" not in after
    assert not (repo / ".testdelta.toml").exists()
    with pytest.raises(InputError, match=r"Commit \.testdelta\.toml at the base revision"):
        make_plan(repo, "HEAD~1")


def test_external_manifest_overrides_base_config_without_changing_snapshot(repository):
    repo, commit = repository
    (repo / "tests/test_calc.py").write_text("def test_new():\n    assert True\n")
    commit()
    external = b'source_modules=["src/calc.py"]\ntest_paths=["tests/test_calc.py"]\n'

    plan, before, after = make_plan(repo, "HEAD~1", manifest_bytes=external)

    assert plan["supported"]
    assert plan["manifest"]["test_paths"] == ["tests/test_calc.py"]
    assert plan["manifest_hash"] == digest(external)
    assert before[".testdelta.toml"] == after[".testdelta.toml"] == MANIFEST


@pytest.mark.parametrize(("external", "message"), [
    (b'source_modules=["src/missing.py"]\ntest_paths=["tests"]\n', "tracked Python files"),
    (b'source_modules=["tests/test_calc.py"]\ntest_paths=["tests"]\n', "must not overlap"),
    (b'source_modules=["src/calc.py"]\ntest_paths=["other_tests"]\n', "No tracked test files"),
    (MANIFEST + b'ignore=["src/calc.py"]\n', "Unknown manifest keys"),
    (b'source_modules=["../calc.py"]\ntest_paths=["tests"]\n', "repository-relative path"),
    (b'source_modules=["src/calc.py"]\ntest_paths=["/tests"]\n', "repository-relative path"),
    (b'source_modules=["src/calc.py"]\ntest_paths=[".git"]\n', "Unsupported path"),
    (b'source_modules=["src/calc.py"]\ntest_paths=["tests", "tests/"]\n', "Duplicate paths"),
    (b'source_modules=["src/calc.py"]\ntest_paths=[]\n', "non-empty array"),
    (b'source_modules=["src/calc.py"]\ntest_paths=["tests"]\n\xff', "Invalid .testdelta.toml"),
    (b'source_modules=["src/calc.py"]\ntest_paths=[\n', "Invalid .testdelta.toml"),
])
def test_external_manifest_rejects_invalid_scope(repository, external, message):
    repo, commit = repository
    (repo / "tests/test_calc.py").write_text("def test_new():\n    assert True\n")
    commit()
    with pytest.raises(InputError, match=message):
        make_plan(repo, "HEAD~1", manifest_bytes=external)


def test_external_manifest_source_must_exist_at_base(repository):
    repo, commit = repository
    (repo / "src/new.py").write_text("value = 1\n")
    commit()
    external = b'source_modules=["src/new.py"]\ntest_paths=["tests"]\n'
    with pytest.raises(InputError, match="tracked Python files: src/new.py"):
        make_plan(repo, "HEAD~1", manifest_bytes=external)


def test_empty_external_manifest_does_not_fall_back_to_base(repository):
    repo, _ = repository
    with pytest.raises(InputError, match="source_modules must be a non-empty array"):
        load_manifest(read_tree(repo, resolve(repo, "HEAD")), b"")


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


@pytest.mark.parametrize("manifest_bytes", [None, MANIFEST], ids=["base_commit", "external"])
def test_deleted_source_is_an_explicit_unsupported_plan(repository, manifest_bytes):
    repo, commit = repository
    (repo / "src/calc.py").unlink()
    commit()
    plan, _, _ = make_plan(repo, "HEAD~1", manifest_bytes=manifest_bytes)
    assert not plan["supported"]
    assert plan["unsupported_changes"] == ["src/calc.py"]
    assert plan["source_hashes"]["src/calc.py"] is None
