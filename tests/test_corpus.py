"""Frozen corpus shape plus one real comparison exemplar in the normal suite."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/validate_corpus.py"
SPEC = importlib.util.spec_from_file_location("testdelta_corpus_validation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CORPUS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORPUS)


def test_corpus_records_and_frozen_hashes():
    manifest, cases = CORPUS.load_corpora()
    assert len(cases) == 50
    assert [case["id"] for case in cases[:30]] == [f"dev-{index:03}" for index in range(1, 31)]
    assert [case["id"] for case in cases[30:]] == [f"val-{index:03}" for index in range(1, 21)]
    assert all(
        CORPUS.expected_for(case, manifest).get("baseline_failure_status")
        for case in cases if case["mutant"] is None
    )


def test_real_loss_exemplar_preserves_repeated_evidence():
    manifest, cases = CORPUS.load_corpora(split="development")
    result = CORPUS.run_case(cases[0], manifest)
    assert result["matches_expected"], result["checks"]
    assert result["actual"]["verdict"] == "loss_observed"
    report = result["report"]
    mutant = report["mutants"][0]
    assert [item["status"] for item in mutant["old"]] == ["assertion_failure"] * 3
    assert [item["status"] for item in mutant["new"]] == ["pass"] * 3
    assert report["witnesses"][0]["confirmation"] == "three_pairs_and_final_controls"
    assert report["plan"]["snapshot_kind"] == "controlled_fixture_bytes_not_git"
