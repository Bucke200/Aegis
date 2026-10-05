"""Common item schema v1.

Collectors emit items in this shape; the normalizer validates them and
rejects anything malformed with a readable error. The schema is versioned:
the loader accepts the current major version and rejects anything newer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aegis.common.models.enums import ItemType, MediaType, Source

SCHEMA_VERSION = "1.0"
SUPPORTED_MAJOR_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("item_v1.schema.json")


class SelfLabel(StrEnum):
    PARODY = "parody"
    FAN = "fan"


class StrictModel(BaseModel):
    """Base model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


class Author(StrictModel):
    platform_account_id: str
    handle: str
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    created_at: datetime | None = None
    followers: int | None = Field(default=None, ge=0)
    following: int | None = Field(default=None, ge=0)
    verified: bool | None = None
    self_labels: list[SelfLabel] = Field(default_factory=list)


class Content(StrictModel):
    text: str
    language: str | None = None
    script: str | None = None


class MediaAttachment(StrictModel):
    url: str
    type: MediaType
    platform_media_id: str | None = None


class Relations(StrictModel):
    reply_to: str | None = None
    repost_of: str | None = None
    quote_of: str | None = None
    mentions: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)


class Engagement(StrictModel):
    likes: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    replies: int | None = Field(default=None, ge=0)
    views: int | None = Field(default=None, ge=0)


class Collection(StrictModel):
    connector: str
    connector_version: str
    query: str | None = None


class ItemV1(StrictModel):
    schema_version: str = SCHEMA_VERSION
    source: Source
    platform_item_id: str
    dedup_key: str | None = None
    item_type: ItemType
    url: str
    posted_at: datetime | None = None
    collected_at: datetime
    author: Author
    content: Content
    media: list[MediaAttachment] = Field(default_factory=list)
    relations: Relations = Field(default_factory=Relations)
    engagement: Engagement = Field(default_factory=Engagement)
    collection: Collection
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_schema_version(self) -> ItemV1:
        major, _ = parse_schema_version(self.schema_version)
        if major != SUPPORTED_MAJOR_VERSION:
            raise ValueError(f"unsupported schema major version {major}; supported: {SUPPORTED_MAJOR_VERSION}")
        return self

    @model_validator(mode="after")
    def _validate_dedup_key(self) -> ItemV1:
        expected = compute_dedup_key(self.source, self.platform_item_id)
        if self.dedup_key is None:
            self.dedup_key = expected
        elif self.dedup_key != expected:
            raise ValueError(f"dedup_key does not match source and platform_item_id (expected {expected})")
        return self


def compute_dedup_key(source: Source, platform_item_id: str) -> str:
    """Return the canonical dedup key for a source item."""

    return hashlib.sha256(f"{source.value}:{platform_item_id}".encode()).hexdigest()


def parse_schema_version(value: str) -> tuple[int, int]:
    """Parse a ``major.minor`` schema version."""

    parts = value.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"schema_version must be 'major.minor', got {value!r}")
    return int(parts[0]), int(parts[1])


def load_item(data: dict[str, Any]) -> ItemV1:
    """Validate a raw payload against schema v1."""

    version = data.get("schema_version")
    if not isinstance(version, str):
        raise ValueError("schema_version is required")
    major, _ = parse_schema_version(version)
    if major != SUPPORTED_MAJOR_VERSION:
        raise ValueError(f"unsupported schema major version {major}; supported: {SUPPORTED_MAJOR_VERSION}")
    return ItemV1.model_validate(data)


def json_schema() -> dict[str, Any]:
    """Return the exported JSON Schema for item v1."""

    return ItemV1.model_json_schema()


def export_json_schema(path: Path = SCHEMA_PATH) -> Path:
    """Write the JSON Schema to disk and return the path."""

    path.write_text(json.dumps(json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    """Export the JSON Schema for the item v1 contract."""

    path = export_json_schema()
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
