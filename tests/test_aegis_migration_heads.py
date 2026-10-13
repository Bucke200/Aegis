"""Guardrails for the Alembic migration graph.

Parallel work packages each add at most one migration (orchestration plan
section 3.5), so the script directory must keep exactly one head and a linear
``down_revision`` chain that reaches every migration.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]


def script_directory() -> ScriptDirectory:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    location = config.get_main_option("script_location") or "migrations"
    config.set_main_option("script_location", str(REPO_ROOT / location))
    return ScriptDirectory.from_config(config)


def test_exactly_one_head() -> None:
    heads = script_directory().get_heads()
    assert len(heads) == 1, f"expected exactly one Alembic head, found {sorted(heads)}"


def test_down_revision_chain_is_unbroken() -> None:
    script = script_directory()
    head = script.get_heads()[0]
    revision = script.get_revision(head)
    walked: list[str] = []
    while revision is not None:
        walked.append(revision.revision)
        down = revision.down_revision
        assert down is None or isinstance(down, str), (
            f"revision {revision.revision} has multiple parents ({down!r}); keep one linear chain"
        )
        revision = None if down is None else script.get_revision(down)
    assert walked[0] == head
    assert len(walked) == len(list(script.walk_revisions())), "the down_revision chain does not cover every migration"
    assert script.get_bases() == [walked[-1]], "the chain does not reach the single base revision"
