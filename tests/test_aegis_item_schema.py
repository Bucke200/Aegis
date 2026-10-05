"""Contract tests for the common item schema v1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from aegis.common.models.enums import Source
from aegis.common.schemas import (
    SCHEMA_PATH,
    compute_dedup_key,
    export_json_schema,
    json_schema,
    load_item,
    parse_schema_version,
)

FIXTURES = Path("tests/fixtures/items")
VALID_FIXTURES = sorted(FIXTURES.glob("valid_*.json"))
INVALID_FIXTURES = sorted(FIXTURES.glob("invalid_*.json"))


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_source_has_a_valid_fixture() -> None:
    assert {read(path)["source"] for path in VALID_FIXTURES} == {source.value for source in Source}


@pytest.mark.parametrize("path", VALID_FIXTURES, ids=lambda path: path.stem)
def test_valid_fixtures_validate(path: Path) -> None:
    item = load_item(read(path))
    assert item.dedup_key == compute_dedup_key(item.source, item.platform_item_id)


@pytest.mark.parametrize("path", INVALID_FIXTURES, ids=lambda path: path.stem)
def test_invalid_fixtures_raise_readable_errors(path: Path) -> None:
    with pytest.raises((ValidationError, ValueError)) as excinfo:
        load_item(read(path))
    assert str(excinfo.value).strip()


def test_round_trip_serialization() -> None:
    item = load_item(read(VALID_FIXTURES[0]))
    again = load_item(json.loads(item.model_dump_json()))
    assert again == item


def test_missing_collected_at_names_the_field() -> None:
    with pytest.raises(ValidationError) as excinfo:
        load_item(read(FIXTURES / "invalid_missing_collected_at.json"))
    assert "collected_at" in str(excinfo.value)


def test_unknown_source_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        load_item(read(FIXTURES / "invalid_unknown_source.json"))
    assert "source" in str(excinfo.value)


def test_bad_media_type_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        load_item(read(FIXTURES / "invalid_bad_media_type.json"))
    assert "type" in str(excinfo.value)


def test_dedup_key_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="dedup_key does not match"):
        load_item(read(FIXTURES / "invalid_dedup_mismatch.json"))


def test_unsupported_major_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported schema major version"):
        load_item(read(FIXTURES / "invalid_unsupported_major.json"))


def test_minor_version_within_current_major_is_accepted() -> None:
    payload = read(FIXTURES / "valid_replay.json")
    payload["schema_version"] = "1.7"
    assert load_item(payload).schema_version == "1.7"


def test_dedup_key_is_computed_when_absent() -> None:
    payload = read(FIXTURES / "valid_replay.json")
    del payload["dedup_key"]
    item = load_item(payload)
    assert item.dedup_key == compute_dedup_key(item.source, item.platform_item_id)


def test_parse_schema_version_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="major.minor"):
        parse_schema_version("v1")


def test_exported_json_schema_is_current(tmp_path: Path) -> None:
    exported = export_json_schema(tmp_path / "item_v1.schema.json")
    assert json.loads(exported.read_text(encoding="utf-8")) == json_schema()
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == json_schema()
