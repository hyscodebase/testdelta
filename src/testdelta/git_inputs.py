"""Read committed Git snapshots without touching the user's checkout."""

from __future__ import annotations

import hashlib
import subprocess
import tomllib
from pathlib import Path, PurePosixPath


class InputError(ValueError):
    """The requested comparison cannot be made under the supported contract."""


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False, timeout=30
    )
    if result.returncode:
        raise InputError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise InputError(f"Expected a repository-relative path: {value!r}")
    if not path.parts or path.parts[0] == ".git" or str(path) == ".":
        raise InputError(f"Unsupported path: {value!r}")
    return str(path)


def resolve(repo: Path, ref: str) -> str:
    # --end-of-options prevents a supplied ref from becoming a Git option.
    return git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()


def read_tree(repo: Path, sha: str) -> dict[str, bytes]:
    tree = git(repo, "ls-tree", "-rlz", "--full-tree", sha)
    records = []
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        mode, kind, oid, size = metadata.split()
        if mode not in (b"100644", b"100755") or kind != b"blob":
            raise InputError("Symlinks and submodules are unsupported in v0.1 snapshots")
        if int(size) > 5_000_000:
            raise InputError("File exceeds the v0.1 5 MB limit")
        records.append((safe_path(path.decode("utf-8")), oid, int(size)))
    if sum(size for _, _, size in records) > 25_000_000:
        raise InputError("Snapshot exceeds the v0.1 25 MB limit")
    # Read Git blobs, not git archive: export-ignore attributes must not hide changed code.
    process = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=b"".join(oid + b"\n" for _, oid, _ in records),
        capture_output=True, check=True, timeout=30,
    )
    files: dict[str, bytes] = {}
    cursor = 0
    for path, oid, size in records:
        header_end = process.stdout.index(b"\n", cursor)
        if process.stdout[cursor:header_end] != oid + b" blob " + str(size).encode():
            raise InputError("Unexpected Git blob response")
        cursor = header_end + 1
        files[path] = process.stdout[cursor:cursor + size]
        cursor += size + 1
    return files


def load_manifest(files: dict[str, bytes]) -> dict:
    if ".testdelta.toml" not in files:
        raise InputError("Commit .testdelta.toml at the base revision before changing tests")
    try:
        config = tomllib.loads(files[".testdelta.toml"].decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise InputError(f"Invalid .testdelta.toml: {exc}") from exc
    if set(config) - {"source_modules", "test_paths"}:
        raise InputError("Unknown manifest keys; expected source_modules and test_paths")
    for key in ("source_modules", "test_paths"):
        values = config.get(key)
        if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
            raise InputError(f"{key} must be a non-empty array of relative paths")
        config[key] = [safe_path(v) for v in values]
        if len(config[key]) != len(set(config[key])):
            raise InputError(f"Duplicate paths in {key}")
    for path in config["source_modules"]:
        if path not in files or not path.endswith(".py"):
            raise InputError(f"source_modules must name tracked Python files: {path}")
    return config


def is_test_file(path: str, test_paths: list[str]) -> bool:
    name = PurePosixPath(path).name
    conventional = name.startswith("test_") or name.endswith("_test.py")
    if name == "conftest.py" or not name.endswith(".py"):
        return False
    return any(
        path == selected or (path.startswith(selected.rstrip("/") + "/") and conventional)
        for selected in test_paths
    )


def make_plan(repo: Path, base: str, head: str = "HEAD", direct_base: bool = False) -> tuple:
    repo = Path(git(repo, "rev-parse", "--show-toplevel").decode().strip())
    head_sha = resolve(repo, head)
    base_ref_sha = resolve(repo, base)
    base_sha = base_ref_sha if direct_base else git(
        repo, "merge-base", base_ref_sha, head_sha
    ).decode().strip()
    before = read_tree(repo, base_sha)
    after = read_tree(repo, head_sha)
    config = load_manifest(before)
    changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    unsupported = [p for p in changed if not is_test_file(p, config["test_paths"])]
    # Never let a source file be overlaid as a test, even if paths overlap.
    if any(is_test_file(p, config["test_paths"]) for p in config["source_modules"]):
        raise InputError("Source modules and test paths must not overlap")
    test_files = sorted(
        p for p in before.keys() | after.keys() if is_test_file(p, config["test_paths"])
    )
    if not test_files:
        raise InputError("No tracked test files match test_paths")
    if not changed:
        unsupported.append("<no committed test changes>")
    plan = {
        "schema_version": "0.1", "repo": str(repo), "base_sha": base_sha,
        "requested_base_sha": base_ref_sha, "head_sha": head_sha,
        "base_mode": "direct" if direct_base else "merge_base", "manifest": config,
        "manifest_hash": digest(before[".testdelta.toml"]),
        "source_hashes": {p: digest(after[p]) if p in after else None
                          for p in config["source_modules"]},
        "test_hashes": {p: {"old": digest(before[p]) if p in before else None,
                            "new": digest(after[p]) if p in after else None} for p in test_files},
        "changed_files": changed, "test_files": test_files,
        "supported": not unsupported, "unsupported_changes": unsupported,
        "working_tree": "committed snapshots only; uncommitted files excluded",
    }
    return plan, before, after


def materialize(files: dict[str, bytes], destination: Path) -> None:
    for path, content in files.items():
        # Credentials are never needed for the supported deterministic local tests.
        name = PurePosixPath(path).name.lower()
        if "__pycache__" in PurePosixPath(path).parts or name.endswith((".pyc", ".pyo")):
            continue
        if name == ".env" or name.startswith(".env.") or name.endswith((".pem", ".key")):
            continue
        target = destination / safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def test_overlay(after: dict, before: dict, test_files: list[str]) -> dict:
    old = dict(after)
    for path in test_files:
        if path in before:
            old[path] = before[path]
        else:
            old.pop(path, None)
    return old
