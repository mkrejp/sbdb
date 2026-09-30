"""Pydantic schemas for layers, objects, typed properties, tags, and URLs."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    database: str


class PropertyValueType(StrEnum):
    """Discriminant for typed object properties."""

    TEXT = "text"
    TEMPORAL = "temporal"
    IMAGE = "image"
    BINARY = "binary"


# --- layers ------------------------------------------------------------------


class LayerCreate(BaseModel):
    """Create a map layer."""

    name: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=10_000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        """Reject whitespace-only names."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class LayerUpdate(BaseModel):
    """Partial update for a map layer."""

    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10_000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str | None) -> str | None:
        """Reject whitespace-only names when provided."""
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class Layer(BaseModel):
    """Map layer resource."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    source_key: str | None = None
    source_url: str | None = None
    created_at: datetime
    updated_at: datetime


class LayerList(BaseModel):
    """Layer collection."""

    items: list[Layer]


# --- objects -----------------------------------------------------------------


class ObjectCreate(BaseModel):
    """Create a layer object with GeoJSON geometry."""

    geometry: dict[str, Any]

    @field_validator("geometry")
    @classmethod
    def geometry_has_type(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Require a GeoJSON type field."""
        if "type" not in value:
            raise ValueError("geometry must include a GeoJSON type")
        return value


class ObjectUpdate(BaseModel):
    """Partial update for object geometry."""

    geometry: dict[str, Any] | None = None

    @field_validator("geometry")
    @classmethod
    def geometry_has_type(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Require a GeoJSON type field when provided."""
        if value is None:
            return value
        if "type" not in value:
            raise ValueError("geometry must include a GeoJSON type")
        return value


class LayerObject(BaseModel):
    """Layer object (GeoJSON feature)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    layer_id: UUID
    geometry: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ObjectList(BaseModel):
    """Object collection."""

    items: list[LayerObject]


# --- typed properties --------------------------------------------------------


class PropertyCreate(BaseModel):
    """Create a typed property (discriminated by value_type)."""

    key: str = Field(min_length=1, max_length=200)
    value_type: PropertyValueType
    text_value: str | None = None
    temporal_value: datetime | None = None
    temporal_end: datetime | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    storage_url: str | None = None
    content_type: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    checksum: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("key")
    @classmethod
    def key_not_blank(cls, value: str) -> str:
        """Reject whitespace-only keys."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("key must not be blank")
        return stripped

    @model_validator(mode="after")
    def payload_matches_type(self) -> PropertyCreate:
        """Enforce typed payload rules matching the SQL CHECK constraint."""
        vt = self.value_type
        if vt is PropertyValueType.TEXT:
            if self.text_value is None:
                raise ValueError("text_value required for value_type=text")
            if any(
                [
                    self.temporal_value,
                    self.temporal_end,
                    self.storage_bucket,
                    self.storage_path,
                ]
            ):
                raise ValueError("text properties must not set temporal/storage fields")
        elif vt is PropertyValueType.TEMPORAL:
            if self.temporal_value is None:
                raise ValueError("temporal_value required for value_type=temporal")
            if self.text_value is not None or self.storage_bucket or self.storage_path:
                raise ValueError("temporal properties must not set text/storage fields")
            if self.temporal_end is not None and self.temporal_end < self.temporal_value:
                raise ValueError("temporal_end must be >= temporal_value")
        elif vt in {PropertyValueType.IMAGE, PropertyValueType.BINARY}:
            if not self.storage_bucket or not self.storage_path:
                raise ValueError("storage_bucket and storage_path required for image/binary")
            if self.text_value is not None or self.temporal_value is not None:
                raise ValueError("image/binary must not set text/temporal value fields")
        return self


class PropertyUpdate(BaseModel):
    """Partial update for a typed property (same type; change payload fields)."""

    key: str | None = Field(default=None, min_length=1, max_length=200)
    text_value: str | None = None
    temporal_value: datetime | None = None
    temporal_end: datetime | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    storage_url: str | None = None
    content_type: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    checksum: str | None = None
    meta: dict[str, Any] | None = None

    @field_validator("key")
    @classmethod
    def key_not_blank(cls, value: str | None) -> str | None:
        """Reject whitespace-only keys when provided."""
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("key must not be blank")
        return stripped


class ObjectProperty(BaseModel):
    """Typed property on a layer object."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    key: str
    value_type: PropertyValueType
    text_value: str | None = None
    temporal_value: datetime | None = None
    temporal_end: datetime | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    storage_url: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    checksum: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PropertyList(BaseModel):
    """Property collection."""

    items: list[ObjectProperty]


# --- tags --------------------------------------------------------------------


class TagCreate(BaseModel):
    """Create a classification tag."""

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        """Reject whitespace-only tag names."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class TagUpdate(BaseModel):
    """Rename a tag."""

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        """Reject whitespace-only tag names."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class Tag(BaseModel):
    """Tag resource."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class TagList(BaseModel):
    """Tag collection."""

    items: list[Tag]


# --- object URLs -------------------------------------------------------------


class ObjectUrlCreate(BaseModel):
    """Add a URL to an object's ordered URL list."""

    url: str = Field(min_length=1, max_length=4000)
    label: str = Field(default="", max_length=500)
    sort_order: int = 0

    @field_validator("url")
    @classmethod
    def url_not_blank(cls, value: str) -> str:
        """Reject whitespace-only URLs."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("url must not be blank")
        return stripped


class ObjectUrlUpdate(BaseModel):
    """Partial update for an object URL row."""

    url: str | None = Field(default=None, min_length=1, max_length=4000)
    label: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None

    @field_validator("url")
    @classmethod
    def url_not_blank(cls, value: str | None) -> str | None:
        """Reject whitespace-only URLs when provided."""
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("url must not be blank")
        return stripped


class ObjectUrl(BaseModel):
    """URL entry associated with a layer object."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    url: str
    label: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ObjectUrlList(BaseModel):
    """Ordered URL collection for an object."""

    items: list[ObjectUrl]


# Re-export literal helper for OpenAPI docs
PropertyTypeLiteral = Literal["text", "temporal", "image", "binary"]
