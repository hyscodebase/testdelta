"""Provider integration checks: real Cosmic Ray, not a mocked mutation engine."""

import hashlib
from importlib.metadata import version

import pytest
from cosmic_ray.mutating import mutate_code
from cosmic_ray.operators.provider import OperatorProvider

from testdelta.adapters.cosmic_ray import generate_mutations

PRICING = '''def total(price_cents, quantity=1, member=False):
    subtotal = price_cents * quantity
    if member:
        subtotal = subtotal * 9 // 10
    shipping = 0 if subtotal >= 5000 else 500
    return subtotal + shipping
'''


def test_real_provider_records_are_stable_reproducible_and_leave_source_untouched(tmp_path):
    path = tmp_path / "pricing.py"
    path.write_bytes(PRICING.encode("utf-8"))
    first = generate_mutations(tmp_path, ["pricing.py"], max_mutants=10)
    second = generate_mutations(tmp_path, ["pricing.py"], max_mutants=10)
    assert first == second
    assert len(first) == 10
    assert path.read_bytes() == PRICING.encode("utf-8")
    assert len({record["id"] for record in first}) == len(first)
    provider = OperatorProvider()
    for record in first:
        assert record["provider"] == "cosmic-ray"
        assert record["provider_version"] == version("cosmic-ray")
        operator_name = record["operator"].split("/", 1)[1]
        # Independently call upstream: the recorded mutant must be its real output.
        upstream = mutate_code(PRICING, provider[operator_name](), record["occurrence"])
        assert record["mutated_source"] == upstream
        assert record["original_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert record["mutated_sha256"] == hashlib.sha256(upstream.encode("utf-8")).hexdigest()
        assert record["original_source"] != record["mutated_source"]
        compile(record["mutated_source"], record["path"], "exec")


def test_boundary_operator_exists_in_real_pricing_candidates(tmp_path):
    (tmp_path / "pricing.py").write_text(PRICING, encoding="utf-8")
    mutants = generate_mutations(tmp_path, ["pricing.py"], max_mutants=200)
    boundary = next(m for m in mutants if m["operator"] == "core/ReplaceComparisonOperator_GtE_Gt")
    assert "subtotal > 5000" in boundary["mutated_source"]
    assert boundary["line"] == 5


def test_input_order_does_not_change_mutant_selection(tmp_path):
    (tmp_path / "a.py").write_text("result = 1 + 2\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("result = 3 + 4\n", encoding="utf-8")
    assert generate_mutations(tmp_path, ["b.py", "a.py"]) == generate_mutations(tmp_path, ["a.py", "b.py", "a.py"])


def test_directory_paths_expand_to_same_candidates_as_explicit_files(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 3\n", encoding="utf-8")
    assert generate_mutations(tmp_path, ["pkg"]) == generate_mutations(tmp_path, ["pkg/mod.py"])


@pytest.mark.parametrize("requested", ["../outside.py", "/tmp/outside.py"])
def test_rejects_paths_outside_workspace(tmp_path, requested):
    with pytest.raises(ValueError, match="workspace-relative"):
        generate_mutations(tmp_path, [requested])


def test_rejects_symlink_source(tmp_path):
    (tmp_path / "real.py").write_text("x = 3\n", encoding="utf-8")
    (tmp_path / "alias.py").symlink_to(tmp_path / "real.py")
    with pytest.raises(ValueError, match="symlink"):
        generate_mutations(tmp_path, ["alias.py"])


def test_invalid_source_is_not_silently_reported_as_no_mutants(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported Python source"):
        generate_mutations(tmp_path, ["bad.py"])


def test_invalid_later_source_is_not_hidden_by_mutation_cap(tmp_path):
    (tmp_path / "a.py").write_text("x = 3\n", encoding="utf-8")
    (tmp_path / "z.py").write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported Python source"):
        generate_mutations(tmp_path, ["a.py", "z.py"], 1)


def test_symlink_parent_is_not_a_second_path_to_the_same_module(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "mod.py").write_text("x = 3\n", encoding="utf-8")
    (tmp_path / "alias").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        generate_mutations(tmp_path, ["alias/mod.py"])


def test_source_is_parsed_without_importing_or_executing_it(tmp_path):
    marker = tmp_path / "must_not_exist"
    (tmp_path / "side_effect.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\nvalue = 1\n",
        encoding="utf-8",
    )
    assert generate_mutations(tmp_path, ["side_effect.py"])
    assert not marker.exists()


def test_preserves_original_crlf_bytes_in_hash_and_record(tmp_path):
    original = b"value = 3\r\n"
    (tmp_path / "windows.py").write_bytes(original)
    record = generate_mutations(tmp_path, ["windows.py"], 1)[0]
    assert record["original_source"].encode("utf-8") == original
    assert record["original_sha256"] == hashlib.sha256(original).hexdigest()
