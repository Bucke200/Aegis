"""Tests for the blind annotation workflow (no database required)."""

from __future__ import annotations

import codecs
from pathlib import Path

import pytest

from aegis.detectors.intent import INTENT_LABELS, THREAT_LABELS
from aegis.eval.__main__ import main
from aegis.eval.agreement import cohen_kappa
from aegis.eval.annotate import (
    LabelRecord,
    agreement_stats,
    import_sheet,
    load_candidates,
    merge_to_golden,
    read_sheet,
    review_sample_ids,
    write_records,
    write_sheet,
)
from aegis.eval.candidates import generate_candidates
from aegis.eval.dataset import load_golden

PER_CLASS = 3


def _candidates():
    return generate_candidates(per_class=PER_CLASS, seed=7)


def _agreeing_records(candidates, *, annotator: str = "tester") -> list[LabelRecord]:
    return [
        LabelRecord(id=candidate.id, label=candidate.intended_label, annotator=annotator) for candidate in candidates
    ]


def test_generate_is_deterministic_and_covers_cells() -> None:
    first = _candidates()
    second = _candidates()
    assert first == second
    assert len(first) == len(INTENT_LABELS) * 3 * PER_CLASS

    for language in ("en", "hi", "hi-Latn"):
        for label in INTENT_LABELS:
            cell = [item for item in first if item.language == language and item.intended_label == label]
            assert len(cell) == PER_CLASS, (language, label)

    assert len({item.id for item in first}) == len(first)
    assert len({(item.language, item.text) for item in first}) == len(first)
    assert any(item.edge_case for item in first)


def test_sheet_hides_labels_and_has_bom(tmp_path: Path) -> None:
    candidates = _candidates()
    path = write_sheet(candidates, tmp_path / "sheet.csv", seed=7)

    raw = path.read_bytes()
    assert raw.startswith(codecs.BOM_UTF8)
    text = raw.decode("utf-8-sig")
    assert "intended_label" not in text

    rows = read_sheet(path)
    assert {row["id"] for row in rows} == {candidate.id for candidate in candidates}
    assert all(row["label"] == "" for row in rows)
    assert [row["id"] for row in rows] != [candidate.id for candidate in candidates]


def test_import_validates_labels(tmp_path: Path) -> None:
    good = tmp_path / "good.csv"
    good.write_text(
        "id,language,edge_case,text,label\ncand-1,en,,Some text,criticism\n",
        encoding="utf-8-sig",
    )
    records = import_sheet(good, annotator="tester")
    assert records == [LabelRecord(id="cand-1", label="criticism", annotator="tester")]

    bad = tmp_path / "bad.csv"
    bad.write_text(
        "id,language,edge_case,text,label\ncand-2,en,,Some text,bogus\ncand-3,en,,No label,\n",
        encoding="utf-8-sig",
    )
    with pytest.raises(ValueError, match="bogus") as error:
        import_sheet(bad, annotator="tester")
    assert "no label" in str(error.value)


def test_cohen_kappa() -> None:
    assert cohen_kappa([]) == 0.0
    assert cohen_kappa([("criticism", "criticism"), ("none", "none")]) == 1.0
    assert cohen_kappa([("a", "a"), ("a", "a")]) == 1.0
    assert cohen_kappa([("a", "a"), ("b", "b"), ("a", "b"), ("b", "a")]) == 0.0


def test_agreement_stats_and_sample() -> None:
    candidates = _candidates()
    annotated = _agreeing_records(candidates)
    annotated[0] = LabelRecord(id=candidates[0].id, label="ambiguous", annotator="tester")
    annotated[1] = LabelRecord(
        id=candidates[1].id,
        label="criticism" if candidates[1].intended_label != "criticism" else "none",
        annotator="tester",
    )

    stats = agreement_stats(candidates, annotated)
    assert stats["items"] == len(candidates)
    assert stats["ambiguous"] == 1
    assert len(stats["disagreements"]) == 1
    assert 0.0 <= stats["kappa"] <= 1.0

    required = review_sample_ids(candidates, annotated, fraction=0.25, seed=7)
    assert candidates[0].id in required
    assert candidates[1].id in required
    assert len(required) == round(0.25 * len(candidates))


def test_merge_requires_review_and_writes_golden(tmp_path: Path) -> None:
    candidates = _candidates()
    annotated = _agreeing_records(candidates)
    annotated[0] = LabelRecord(id=candidates[0].id, label="ambiguous", annotator="tester")

    with pytest.raises(ValueError, match="review-required"):
        merge_to_golden(
            candidates=candidates,
            annotated=annotated,
            reviewed=[],
            out_dir=tmp_path / "golden",
        )

    required = review_sample_ids(candidates, annotated, fraction=0.25, seed=7)
    by_id = {candidate.id: candidate for candidate in candidates}
    reviewed = [
        LabelRecord(id=item, label=by_id[item].intended_label, annotator="reviewer", role="reviewer")
        for item in required
    ]
    discard_id = required[-1]
    reviewed[-1] = LabelRecord(id=discard_id, label="discard", annotator="reviewer", role="reviewer")

    summary = merge_to_golden(
        candidates=candidates,
        annotated=annotated,
        reviewed=reviewed,
        out_dir=tmp_path / "golden",
        guideline_version="v1-test",
    )
    assert summary["written"] == len(candidates) - 1
    assert summary["dropped"] == 1

    loaded = load_golden(tmp_path / "golden")
    assert len(loaded) == len(candidates) - 1
    assert discard_id not in {item.id for item in loaded}
    for item in loaded:
        assert item.provenance == "synthetic"
        assert item.guideline_version == "v1-test"
        assert item.final_label in INTENT_LABELS
        assert item.labels["text_intent_llm"] == (item.final_label in THREAT_LABELS)
        assert item.labels["text_lexicon"] == (item.final_label in THREAT_LABELS)
    assert any(item.reviewer == "reviewer" for item in loaded)


def test_merge_rejects_missing_blind_labels(tmp_path: Path) -> None:
    candidates = _candidates()
    annotated = _agreeing_records(candidates)[:-1]
    with pytest.raises(ValueError, match="no blind label") as error:
        merge_to_golden(
            candidates=candidates,
            annotated=annotated,
            reviewed=[],
            out_dir=tmp_path / "golden",
        )
    assert "no blind label" in str(error.value)


def test_cli_generate_sheet_import_stats_merge(tmp_path: Path) -> None:
    candidates_path = tmp_path / "candidates.jsonl"
    sheet_path = tmp_path / "sheet.csv"
    annotated_path = tmp_path / "annotated.jsonl"
    review_sheet_path = tmp_path / "review-sheet.csv"
    reviewed_path = tmp_path / "reviewed.jsonl"
    golden_dir = tmp_path / "golden"

    assert main(["generate", "--out", str(candidates_path), "--per-class", "2"]) == 0
    assert main(["sheet", "--candidates", str(candidates_path), "--out", str(sheet_path)]) == 0

    candidates = load_candidates(candidates_path)
    rows = read_sheet(sheet_path)
    by_id = {candidate.id: candidate for candidate in candidates}
    records = [LabelRecord(id=row["id"], label=by_id[row["id"]].intended_label, annotator="tester") for row in rows]
    write_records(records, annotated_path)

    assert main(["stats", "--candidates", str(candidates_path), "--annotated", str(annotated_path)]) == 0
    assert (
        main(
            [
                "sample",
                "--candidates",
                str(candidates_path),
                "--annotated",
                str(annotated_path),
                "--out",
                str(review_sheet_path),
                "--fraction",
                "0.25",
            ]
        )
        == 0
    )
    review_rows = read_sheet(review_sheet_path)
    write_records(
        [
            LabelRecord(id=row["id"], label=by_id[row["id"]].intended_label, annotator="reviewer", role="reviewer")
            for row in review_rows
        ],
        reviewed_path,
    )

    assert (
        main(
            [
                "merge",
                "--candidates",
                str(candidates_path),
                "--annotated",
                str(annotated_path),
                "--reviewed",
                str(reviewed_path),
                "--out-dir",
                str(golden_dir),
            ]
        )
        == 0
    )
    assert len(load_golden(golden_dir)) == len(candidates)
