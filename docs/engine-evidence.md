# Mutation engine decision and evidence

TestDelta reuses **Cosmic Ray 8.7.0** to generate mutants. It does not implement a replacement mutation engine. The adapter is `src/testdelta/adapters/cosmic_ray.py`; the tests exercise the installed upstream package, not a fake provider.

## Upstream API inspected

On 2026-11-02, an isolated `uv run --no-project --with cosmic-ray==8.7.0 --with pytest` environment resolved Cosmic Ray 8.7.0. The installed source was inspected with `inspect.getsource` before writing the adapter. These APIs were present:

- `cosmic_ray.operators.provider.OperatorProvider`: built-in operator classes.
- `cosmic_ray.ast.get_ast` and `ast_nodes`: the provider's parser and traversal order.
- `operator.mutation_positions(node)`: available positions for an upstream operator.
- `cosmic_ray.mutating.mutate_code(source, operator, occurrence)`: one actual upstream mutation, returned as a source string.

Cosmic Ray documents operator discovery and mutation positions in its [operator guide](https://cosmic-ray.readthedocs.io/en/latest/how-tos/operators.html). Its [mutating module](https://github.com/sixty-north/cosmic-ray/blob/master/src/cosmic_ray/mutating.py) implements the string-to-string mutation API. The installed 8.7.0 source, rather than the moving `master` branch, was the implementation checked in this experiment.

## Adapter contract

```python
generate_mutations(
    workspace: pathlib.Path,
    source_modules: list[str],
    max_mutants: int = 10,
) -> list[dict]
```

`source_modules` contains workspace-relative `.py` files or directories. Directories expand recursively to Python files. The caller must target production modules; this adapter does not infer which files are tests. Absolute paths, parent traversal, symlink paths and missing targets are rejected.

The adapter reads original bytes without newline normalization and accepts UTF-8 source without a BOM. Original syntax must compile and must be supported by Cosmic Ray's parser. Every selected source is validated even if an earlier module fills the cap. Source is parsed and compiled but **never imported or executed by this adapter**.

Candidate order is relative path, source line, source column, operator name and operator occurrence. A candidate always starts from the same original source, never from a previously mutated variant. Cosmic Ray creates each mutated string. TestDelta compile-checks it without execution, skips invalid syntax and duplicate byte outputs, and records the selected candidates.

Each record includes:

```text
id, path, line, operator, occurrence,
provider, provider_version,
original_sha256, mutated_sha256,
original_source, mutated_source, replacement_description
```

Hashes are SHA-256 of the UTF-8 source bytes. IDs include the provider version, relative path, original hash, operator, occurrence and mutated hash. A provider upgrade can intentionally change IDs and candidate selection; compare stored bytes rather than assuming stability across versions.

The runner must materialize `mutated_source.encode("utf-8")` from the **same record** into both test workspaces. The adapter does not run tests, classify kills, clone Git revisions or create a sandbox. A returned empty list is not evidence of test adequacy.

## Scope of the first operator set

The adapter selects 19 deterministic, argument-free built-in operator classes: numeric constants, boolean substitutions, six comparison changes, six arithmetic changes and removal of unary `not`. Their exact names are in `OPERATOR_NAMES`.

Cosmic Ray's variable insertion/replacement operators require arguments and use randomness. They are excluded. Third-party operator providers are not selected. This is an explicit subset of Cosmic Ray, not an exhaustive mutation analysis. Duplicate byte outputs are removed; **equivalent mutants are not identified**.

The cap selects a deterministic prefix, not a statistically representative sample. Earlier files and lines receive priority. A small cap can omit the boundary a user cares about; a report must not turn “no selected witness” into “the test change is safe.” There is no coverage-guided selection in this version.

## Actual local generation experiment

Executed on 2026-11-02 with Cosmic Ray 8.7.0. The input was this synthetic, pure pricing function:

```python
def total(price_cents, quantity=1, member=False):
    subtotal = price_cents * quantity
    if member:
        subtotal = subtotal * 9 // 10
    shipping = 0 if subtotal >= 5000 else 500
    return subtotal + shipping
```

Observed results from actual adapter calls:

| Check | Actual result |
|---|---|
| Generation with cap 10 | 10 candidates |
| Generation repeated with the same source/configuration | Full records identical |
| Original file after both calls | Byte-identical to input |
| Generation with cap 200 | 22 unique compilable candidates |
| Exact-threshold change | `core/ReplaceComparisonOperator_GtE_Gt`, line 5 |
| Threshold mutant | `subtotal >= 5000` became `subtotal > 5000` |

Input SHA-256:

```text
02dfb1193367f2121227f32039ad4644318e522e2bf3cb57a167d6e4df67e97a
```

Boundary mutant SHA-256:

```text
9a155a2bc0910d5861dbb67a0c93dd6dd5fe367aeb26e69434ae3763ff4459d2
```

The boundary mutant was **not in the first ten candidates** because earlier source locations filled the cap. This result directly demonstrates the selection limit rather than hiding it. The experiment establishes reproducible upstream generation; it does not establish test kills or usefulness on an external repository.

## Verification

```bash
uv run --no-project --with cosmic-ray==8.7.0 --with pytest python -c \
  'import sys; sys.path.insert(0,"src"); import pytest; raise SystemExit(pytest.main(["tests/test_mutations.py","-q"]))'
```

The integration tests independently call Cosmic Ray's `mutate_code` for returned records and compare the resulting source bytes. They also check stable selection, actual boundary mutation, unchanged input, path ordering, directory expansion, invalid-source handling, path/symlink rejection, CRLF preservation and absence of source execution.

There are no claims here about untrusted-code isolation, equivalent-mutant filtering, complete Python syntax support, coverage accuracy, real-project runtime, or regression detection quality. Those require the separate runner and project-level validation.
