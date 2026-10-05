"""Load labelled items from the golden evaluation set."""

from __future__ import annotations

from pathlib import Path

from aegis.eval.models import GoldenItem


def load_golden(path: Path) -> list[GoldenItem]:
    """Load every JSONL file under a file or directory, in stable order."""

    files = sorted(path.rglob("*.jsonl")) if path.is_dir() else [path]
    items: list[GoldenItem] = []
    for file in files:
        for line_number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                items.append(GoldenItem.model_validate_json(stripped))
            except ValueError as error:
                raise ValueError(f"{file}:{line_number}: invalid golden item: {error}") from error

    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        if item.id in seen:
            duplicates.add(item.id)
        seen.add(item.id)
    if duplicates:
        raise ValueError(f"duplicate golden item ids: {sorted(duplicates)}")
    return items
