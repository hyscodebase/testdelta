"""Materialize deterministic mutants using Cosmic Ray's own operators.

This module selects, orders and records Cosmic Ray mutations; it does not
implement mutation operators or execute the source under examination.
"""

from __future__ import annotations

import hashlib
import io
import json
import tokenize
import warnings
from importlib.metadata import version
from pathlib import Path
from typing import Any

from cosmic_ray.ast import ast_nodes, get_ast
from cosmic_ray.mutating import mutate_code
from cosmic_ray.operators.provider import OperatorProvider

PROVIDER = "cosmic-ray"
# Explicitly limited to deterministic, argument-free, built-in operators.
# The randomized VariableReplacer/VariableInserter are intentionally excluded.
OPERATOR_NAMES = tuple(sorted((
    "AddNot",
    "NumberReplacer",
    "ReplaceAndWithOr",
    "ReplaceOrWithAnd",
    "ReplaceTrueWithFalse",
    "ReplaceFalseWithTrue",
    "ReplaceComparisonOperator_Eq_NotEq",
    "ReplaceComparisonOperator_NotEq_Eq",
    "ReplaceComparisonOperator_Lt_LtE",
    "ReplaceComparisonOperator_LtE_Lt",
    "ReplaceComparisonOperator_Gt_GtE",
    "ReplaceComparisonOperator_GtE_Gt",
    "ReplaceBinaryOperator_Add_Sub",
    "ReplaceBinaryOperator_Sub_Add",
    "ReplaceBinaryOperator_Mul_Add",
    "ReplaceBinaryOperator_Mul_Div",
    "ReplaceBinaryOperator_Div_Mul",
    "ReplaceBinaryOperator_FloorDiv_Mul",
    "ReplaceUnaryOperator_Delete_Not",
)))


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _contains_symlink(path: Path, workspace: Path) -> bool:
    cursor = path
    while cursor != workspace:
        if cursor.is_symlink():
            return True
        cursor = cursor.parent
    return False


def _module_paths(workspace: Path, source_modules: list[str]) -> list[Path]:
    """Resolve explicit Python files/directories without importing packages."""
    paths: dict[str, Path] = {}
    for requested in source_modules:
        relative = Path(requested)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"source module must be workspace-relative: {requested}")
        candidate = workspace / relative
        resolved = candidate.resolve()
        if not resolved.is_relative_to(workspace):
            raise ValueError(f"source module escapes workspace: {requested}")
        if not candidate.exists():
            raise ValueError(f"source module does not exist: {requested}")
        if _contains_symlink(candidate, workspace):
            raise ValueError(f"symlink source modules are unsupported: {requested}")
        if candidate.is_dir():
            expanded = list(candidate.rglob("*.py"))
        elif candidate.is_file() and candidate.suffix == ".py":
            expanded = [candidate]
        else:
            raise ValueError(f"source module must be a .py file or directory: {requested}")
        for path in expanded:
            resolved_path = path.resolve()
            if not resolved_path.is_relative_to(workspace):
                raise ValueError(f"source module escapes workspace: {path}")
            if _contains_symlink(path, workspace):
                raise ValueError(f"symlink source modules are unsupported: {path}")
            if not path.is_file():
                continue
            key = path.relative_to(workspace).as_posix()
            paths[key] = path
    return [paths[key] for key in sorted(paths)]


def _source(path: Path) -> tuple[bytes, str, Any]:
    raw = path.read_bytes()
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        if encoding != "utf-8":
            raise ValueError("only UTF-8 source without a BOM is supported")
        text = raw.decode("utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            compile(text, str(path), "exec")
        tree = get_ast(text)
    except (SyntaxError, UnicodeError, ValueError) as exc:
        raise ValueError(f"unsupported Python source {path}: {exc}") from exc
    if any(node.type in {"error_node", "error_leaf"} for node in ast_nodes(tree)):
        raise ValueError(f"source syntax is unsupported by Cosmic Ray's parser: {path}")
    return raw, text, tree


def _description(operator: str, line: int, before: str, after: str) -> str:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    old_line = before_lines[line - 1] if line <= len(before_lines) else ""
    new_line = after_lines[line - 1] if line <= len(after_lines) else ""
    return f"{operator} at line {line}: {old_line.strip()!r} -> {new_line.strip()!r}"


def generate_mutations(
    workspace: Path,
    source_modules: list[str],
    max_mutants: int = 10,
) -> list[dict]:
    """Return up to ``max_mutants`` immutable-by-convention source records.

    Inputs are explicit workspace-relative .py files or directories. Candidate
    order is path, source position, operator name, occurrence. Every candidate
    is generated from the original source, then compile-checked without exec.
    Source files are never changed. The caller must write the same recorded
    ``mutated_source.encode('utf-8')`` to both test workspaces.

    Raises ValueError for unsupported/invalid inputs or provider failures.
    An empty list means no candidate was selected, not that tests are adequate.
    """
    if isinstance(max_mutants, bool) or not isinstance(max_mutants, int) or max_mutants < 0:
        raise ValueError("max_mutants must be a nonnegative integer")
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")
    if max_mutants == 0:
        return []
    paths = _module_paths(root, source_modules)
    provider = OperatorProvider()
    provider_version = version(PROVIDER)
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    # Validate every explicitly selected module even if an earlier file fills
    # the mutation cap. Unsupported input must not disappear behind truncation.
    sources = [(path, _source(path)) for path in paths]
    for path, (original_bytes, original, tree) in sources:
        relative = path.relative_to(root).as_posix()
        original_hash = _sha256(original_bytes)
        positions: list[tuple[int, int, str, int]] = []
        for operator_name in OPERATOR_NAMES:
            operator = provider[operator_name]()
            occurrence = 0
            for node in ast_nodes(tree):
                for start, _end in operator.mutation_positions(node):
                    positions.append((start[0], start[1], operator_name, occurrence))
                    occurrence += 1
        for line, _column, operator_name, occurrence in sorted(positions):
            full_name = f"core/{operator_name}"
            try:
                mutated = mutate_code(original, provider[operator_name](), occurrence)
            except Exception as exc:
                raise ValueError(
                    f"Cosmic Ray failed for {relative}: {full_name} occurrence {occurrence}: {exc}"
                ) from exc
            if mutated is None or mutated == original:
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    compile(mutated, relative, "exec")
            except (SyntaxError, ValueError):
                # Some otherwise valid operator positions yield invalid syntax.
                continue
            mutated_hash = _sha256(mutated.encode("utf-8"))
            if (relative, mutated_hash) in seen:
                continue
            seen.add((relative, mutated_hash))
            identity = json.dumps(
                [PROVIDER, provider_version, relative, original_hash, full_name, occurrence, mutated_hash],
                separators=(",", ":"),
            ).encode("utf-8")
            records.append({
                "id": f"cr-{_sha256(identity)[:16]}",
                "path": relative,
                "line": line,
                "operator": full_name,
                "occurrence": occurrence,
                "provider": PROVIDER,
                "provider_version": provider_version,
                "original_sha256": original_hash,
                "mutated_sha256": mutated_hash,
                "original_source": original,
                "mutated_source": mutated,
                "replacement_description": _description(full_name, line, original, mutated),
            })
            if len(records) >= max_mutants:
                return records
    return records
