"""Pydantic v2 response/request schemas for the ObjectIndex API.

These reproduce the exact JSON shapes the previous Flask-RESTX app emitted,
which the GUI and client depend on:

* ``checksum`` is stored as binary but exposed as a hex string.
* A ``File`` response embeds the *full* object (``file_object``); an
  ``Object`` response embeds only *brief* files (``uuid`` + ``url``).
"""

import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


class BriefFile(BaseModel):
    """Minimal file view embedded inside an Object."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    url: str


class ObjectRead(BaseModel):
    """Full object view (checksum rendered as hex)."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    bucket: str
    key: str
    obj_size: int
    checksum: Optional[bytes] = None
    ctime: datetime.datetime
    mime: Optional[str] = None
    completed: bool
    deleted: bool
    extra: Optional[Any] = None
    files: list[BriefFile] = []

    @field_serializer("checksum")
    def _serialize_checksum(self, value: Optional[bytes]) -> Optional[str]:
        return value.hex() if value is not None else None


class FileRead(BaseModel):
    """Full file view (embeds the full object as ``file_object``)."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    url: str
    ctime: datetime.datetime
    mtime: Optional[datetime.datetime] = None
    direct: bool
    partial: bool
    extra: Optional[Any] = None
    ul_user: Optional[str] = None
    ul_sw: Optional[str] = None
    ul_host: Optional[str] = None
    file_object: Optional[ObjectRead] = None


class UploadLinks(BaseModel):
    """Where to PUT the bytes and how to mark the upload finished."""

    s3: str
    finished: str


class UploadResult(BaseModel):
    """Response from ``POST /upload/``."""

    file: FileRead
    exists: bool
    upload: Optional[UploadLinks] = None
    download: Optional[str] = None


class S3Link(BaseModel):
    """Direct object URL (named ``presigned`` for historical reasons)."""

    presigned: str


class UploadRequest(BaseModel):
    """Body of ``POST /upload/``."""

    url: str
    bucket: str
    obj_size: int
    checksum: str
    direct: bool = True
    partial: bool = False
    mtime: Optional[datetime.datetime] = None
    filename: Optional[str] = None
    mime: Optional[str] = None
    ul_user: Optional[str] = None
    ul_sw: Optional[str] = None
    ul_host: Optional[str] = None
    extra_file: Optional[Any] = None
    extra_object: Optional[Any] = None


class ObjectUpdate(BaseModel):
    """Body of ``PUT /object/{uuid}/``."""

    completed: Optional[bool] = None
    deleted: Optional[bool] = None
