"""Blind labelling workflow for the golden gate set.

Flow:

    generate  -> candidates JSONL (intended label hidden from annotators)
    sheet     -> shuffled CSV with a UTF-8 BOM (Excel-safe Devanagari)
    import    -> validated labels JSONL per annotator
    stats     -> intended-vs-blind agreement (Cohen's kappa)
    sample    -> review sheet: disagreements, ambiguous items, and a random slice
    merge     -> validated golden items under data/private/golden/intent/

The reviewer's label is final where present; ``discard`` drops an item; an
item only enters the golden set with a blind label that either matches the
generator's intent or was adjudicated by the reviewer.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

from aegis.detectors.intent import INTENT_LABELS, THREAT_LABELS
from aegis.eval.agreement import cohen_kappa, per_class_agreement
from aegis.eval.bank import DEFAULT_BANK_DIR, DRAFTER_HAND, DRAFTER_TEMPLATE
from aegis.eval.candidates import Candidate, generate_from_bank
from aegis.eval.dataset import load_golden
from aegis.eval.models import GoldenItem

ANNOTATOR_MARKERS = ("ambiguous", "unusable")
REVIEWER_MARKERS = ("ambiguous", "discard")
UNUSABLE_REDRAFT_THRESHOLD = 0.10
DEFAULT_CANDIDATES = Path("data/labelling/candidates.jsonl")
DEFAULT_SHEET = Path("data/labelling/sheet.csv")
DEFAULT_ANNOTATED = Path("data/labelling/annotated.jsonl")
DEFAULT_REVIEW_SHEET = Path("data/labelling/review-sheet.csv")
DEFAULT_REVIEWED = Path("data/labelling/reviewed.jsonl")
DEFAULT_GOLDEN_DIR = Path("data/private/golden/intent")


class LabelRecord(BaseModel):
    """One label assigned by a human to a candidate."""

    id: str
    label: str
    annotator: str
    role: str = "annotator"

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        if value not in {"annotator", "reviewer"}:
            raise ValueError("role must be annotator or reviewer")
        return value

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        allowed = {*INTENT_LABELS, *ANNOTATOR_MARKERS, *REVIEWER_MARKERS}
        if value not in allowed:
            raise ValueError(f"unknown label {value!r}")
        return value


def write_candidates(candidates: list[Candidate], path: Path = DEFAULT_CANDIDATES) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(candidate), ensure_ascii=False) for candidate in candidates]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_candidates(path: Path = DEFAULT_CANDIDATES) -> list[Candidate]:
    candidates: list[Candidate] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            candidates.append(Candidate(**json.loads(line)))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{path}:{line_number}: invalid candidate: {error}") from error
    return candidates


def run_generate(
    *,
    out: Path = DEFAULT_CANDIDATES,
    per_class: int = 100,
    seed: int = 7,
    bank_dir: Path = DEFAULT_BANK_DIR,
    cells: list[str] | None = None,
) -> Path:
    return write_candidates(generate_from_bank(bank_dir, per_class=per_class, seed=seed, cells=cells), out)


def write_sheet(candidates: list[Candidate], path: Path = DEFAULT_SHEET, *, seed: int = 7) -> Path:
    rows = list(candidates)
    random.Random(seed).shuffle(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "language", "edge_case", "text", "label"])
        writer.writeheader()
        for candidate in rows:
            writer.writerow(
                {
                    "id": candidate.id,
                    "language": candidate.language,
                    "edge_case": candidate.edge_case or "",
                    "text": candidate.text,
                    "label": "",
                }
            )
    return path


def read_sheet(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def import_sheet(sheet_path: Path, *, annotator: str, role: str = "annotator") -> list[LabelRecord]:
    records: list[LabelRecord] = []
    problems: list[str] = []
    for row_number, row in enumerate(read_sheet(sheet_path), start=2):
        label = (row.get("label") or "").strip()
        if not label:
            problems.append(f"row {row_number} ({row.get('id')}): no label")
            continue
        try:
            records.append(LabelRecord(id=str(row["id"]), label=label, annotator=annotator, role=role))
        except ValueError as error:
            problems.append(f"row {row_number} ({row.get('id')}): {error}")
    if problems:
        raise ValueError("; ".join(problems[:20]))
    return records


def write_records(records: list[LabelRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [record.model_dump_json() for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_records(path: Path) -> list[LabelRecord]:
    records: list[LabelRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(LabelRecord.model_validate_json(line))
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: invalid label record: {error}") from error
    return records


def _record_map(records: list[LabelRecord]) -> dict[str, LabelRecord]:
    mapped: dict[str, LabelRecord] = {}
    for record in records:
        if record.id in mapped:
            raise ValueError(f"duplicate label record for {record.id}")
        mapped[record.id] = record
    return mapped


def agreement_stats(
    candidates: list[Candidate],
    annotated: list[LabelRecord],
) -> dict[str, Any]:
    by_id = _record_map(annotated)
    pairs: list[tuple[str, str]] = []
    all_pairs: list[tuple[str, str]] = []
    ambiguous = 0
    unusable = 0
    missing = 0
    unusable_by_cell: dict[str, int] = {}
    totals_by_cell: dict[str, int] = {}
    for candidate in candidates:
        cell = f"{candidate.language}/{candidate.intended_label}"
        totals_by_cell[cell] = totals_by_cell.get(cell, 0) + 1
        record = by_id.get(candidate.id)
        if record is None:
            missing += 1
            continue
        if record.label == "ambiguous":
            ambiguous += 1
            all_pairs.append((candidate.intended_label, record.label))
            continue
        if record.label == "unusable":
            unusable += 1
            unusable_by_cell[cell] = unusable_by_cell.get(cell, 0) + 1
            continue
        pairs.append((candidate.intended_label, record.label))
        all_pairs.append((candidate.intended_label, record.label))
    redraft_cells = sorted(
        cell
        for cell, count in unusable_by_cell.items()
        if count / totals_by_cell.get(cell, count) > UNUSABLE_REDRAFT_THRESHOLD
    )
    return {
        "items": len(pairs),
        "items_with_ambiguous": len(all_pairs),
        "missing": missing,
        "ambiguous": ambiguous,
        "unusable": unusable,
        "unusable_by_cell": unusable_by_cell,
        "redraft_cells": redraft_cells,
        "kappa": cohen_kappa(pairs),
        "kappa_with_ambiguous": cohen_kappa(all_pairs),
        "per_class": {label: per_class_agreement(pairs, label) for label in INTENT_LABELS},
        "disagreements": [
            {"id": candidate.id, "intended": candidate.intended_label, "blind": by_id[candidate.id].label}
            for candidate in candidates
            if candidate.id in by_id
            and by_id[candidate.id].label not in {"ambiguous", "unusable"}
            and by_id[candidate.id].label != candidate.intended_label
        ],
    }


def review_sample_ids(
    candidates: list[Candidate],
    annotated: list[LabelRecord],
    *,
    fraction: float = 0.25,
    seed: int = 7,
) -> list[str]:
    """Disagreements, ambiguous items, plus a random slice weighted to model drafts."""

    by_id = _record_map(annotated)
    flagged: set[str] = set()
    rest: list[str] = []
    for candidate in candidates:
        record = by_id.get(candidate.id)
        if record is None:
            raise ValueError(f"candidate {candidate.id} has no blind label")
        if record.label == "unusable":
            continue
        if record.label != candidate.intended_label or record.label == "ambiguous":
            flagged.add(candidate.id)
        else:
            rest.append(candidate.id)

    rest.sort(key=lambda item: hashlib.sha256(f"{seed}:{item}".encode()).hexdigest())
    drafter_by_id = {candidate.id: candidate.drafter for candidate in candidates}
    model_drafts = [item for item in rest if drafter_by_id.get(item) not in {DRAFTER_HAND, DRAFTER_TEMPLATE}]
    model_set = set(model_drafts)
    ordered = model_drafts + [item for item in rest if item not in model_set]
    sample_size = round(fraction * (len(flagged) + len(rest)))
    random_slice = set(ordered[: max(0, sample_size - len(flagged))])
    return sorted(flagged | random_slice)


def write_review_sheet(
    candidates: list[Candidate],
    ids: list[str],
    path: Path = DEFAULT_REVIEW_SHEET,
    *,
    seed: int = 7,
) -> Path:
    wanted = set(ids)
    rows = [candidate for candidate in candidates if candidate.id in wanted]
    random.Random(seed).shuffle(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "language", "edge_case", "text", "label"])
        writer.writeheader()
        for candidate in rows:
            writer.writerow(
                {
                    "id": candidate.id,
                    "language": candidate.language,
                    "edge_case": candidate.edge_case or "",
                    "text": candidate.text,
                    "label": "",
                }
            )
    return path


def merge_to_golden(
    *,
    candidates: list[Candidate],
    annotated: list[LabelRecord],
    reviewed: list[LabelRecord],
    out_dir: Path = DEFAULT_GOLDEN_DIR,
    guideline_version: str = "v1",
    sample_fraction: float = 0.25,
    sample_seed: int = 7,
) -> dict[str, Any]:
    blind = _record_map(annotated)
    review = _record_map(reviewed)

    missing_blind = [candidate.id for candidate in candidates if candidate.id not in blind]
    if missing_blind:
        raise ValueError(f"{len(missing_blind)} candidates have no blind label, e.g. {missing_blind[:3]}")

    required = set(review_sample_ids(candidates, annotated, fraction=sample_fraction, seed=sample_seed))
    missing_review = sorted(item for item in required if item not in review)
    if missing_review:
        raise ValueError(f"{len(missing_review)} review-required items have no reviewer label: {missing_review[:5]}")

    reviewed_at = datetime.now(tz=UTC).isoformat()
    golden: list[GoldenItem] = []
    dropped: list[str] = []
    for candidate in candidates:
        blind_label = blind[candidate.id].label
        if blind_label == "unusable":
            dropped.append(candidate.id)
            continue
        reviewer = review.get(candidate.id)
        if reviewer is not None and reviewer.label in {"ambiguous", "discard"}:
            dropped.append(candidate.id)
            continue
        final = reviewer.label if reviewer is not None else blind_label
        if final == "ambiguous":
            dropped.append(candidate.id)
            continue
        threat = final in THREAT_LABELS
        golden.append(
            GoldenItem(
                id=candidate.id,
                language=candidate.language,
                text=candidate.text,
                labels={"text_lexicon": threat, "text_intent_llm": threat},
                intent=final,
                source="synthetic",
                provenance="synthetic",
                intended_label=candidate.intended_label,
                blind_label=blind_label,
                final_label=final,
                drafter=candidate.drafter,
                annotator=blind[candidate.id].annotator,
                reviewer=reviewer.annotator if reviewer is not None else None,
                reviewed_at=reviewed_at if reviewer is not None else None,
                edge_case=candidate.edge_case,
                generator_model=candidate.generator_model,
                guideline_version=guideline_version,
            )
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    by_language: dict[str, list[GoldenItem]] = {}
    for item in golden:
        by_language.setdefault(item.language, []).append(item)
    counts: dict[str, dict[str, int]] = {}
    for language, items in sorted(by_language.items()):
        items.sort(key=lambda item: item.id)
        (out_dir / f"{language}.jsonl").write_text(
            "\n".join(item.model_dump_json() for item in items) + "\n",
            encoding="utf-8",
        )
        by_class: dict[str, int] = dict.fromkeys(INTENT_LABELS, 0)
        for item in items:
            by_class[item.final_label or "none"] += 1
        counts[language] = by_class

    loaded = load_golden(out_dir)
    return {
        "written": len(loaded),
        "dropped": len(dropped),
        "reviewed": len(review),
        "required_reviews": len(required),
        "per_language": counts,
    }
