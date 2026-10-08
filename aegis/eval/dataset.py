"""Load labelled items from the golden evaluation set.

Golden data lives under the private ``data/private/golden/`` checkout (the
``Aegis-data`` repository, cloned by ``make data``) in the canonical subfolders
``intent/``, ``impersonation/``, and ``leaks/``. Loading a directory reads only
those subfolders, so caches and other stray JSONL files are never parsed as
golden data. Every line must validate as a ``GoldenItem``; invalid lines raise
with a message that never echoes the item text.
"""

from __future__ import annotations

from pathlib import Path

from aegis.eval.models import GoldenItem, validation_summary

GOLDEN_SUBFOLDERS = ("intent", "impersonation", "leaks")


def _golden_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.parent.name not in GOLDEN_SUBFOLDERS:
            raise ValueError(f"{path}: golden files must live under one of {', '.join(GOLDEN_SUBFOLDERS)}")
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"golden path not found: {path}")
    if path.name in GOLDEN_SUBFOLDERS:
        return sorted(path.glob("*.jsonl"))
    subfolders = [name for name in GOLDEN_SUBFOLDERS if (path / name).is_dir()]
    if not subfolders:
        raise ValueError(
            f"{path}: no golden subfolder ({', '.join(GOLDEN_SUBFOLDERS)}) found; refusing to scan arbitrary JSONL files"
        )
    files: list[Path] = []
    for name in subfolders:
        files.extend(sorted((path / name).glob("*.jsonl")))
    return files


def load_golden(path: Path) -> list[GoldenItem]:
    """Load every golden item under a file or a golden directory."""

    items: list[GoldenItem] = []
    for file in _golden_files(path):
        for line_number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                items.append(GoldenItem.model_validate_json(stripped))
            except ValueError as error:
                raise ValueError(f"{file}:{line_number}: invalid golden item: {validation_summary(error)}") from None

    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        if item.id in seen:
            duplicates.add(item.id)
        seen.add(item.id)
    if duplicates:
        raise ValueError(f"duplicate golden item ids: {sorted(duplicates)}")
    return items
