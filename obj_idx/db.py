"""Object Index database models (SQLModel).

Table names, columns, indexes and the FK match the existing PostgreSQL schema
(see ``schema.sql``) exactly, including the SHA-256 ``checksum`` stored as a
32-byte ``bytea``. This is a drop-in replacement for the SQLAlchemy 2.0 models
with no schema change.
"""

import datetime
import uuid
from typing import List, Optional

from sqlalchemy import BigInteger, Column, ForeignKey, Index, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select

from .config import get_settings


class Object(SQLModel, table=True):
    """A unique stored object (deduplicated by checksum)."""

    __tablename__ = "object"
    __table_args__ = (Index("buckey", "bucket", "key"),)

    uuid: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid1)
    )
    bucket: str = Field(max_length=63)
    key: str = Field(max_length=1023)
    # NOTE Postgres doesn't support unsigned; large WORM files need BIGINT
    obj_size: int = Field(sa_column=Column(BigInteger, nullable=False))
    checksum: Optional[bytes] = Field(
        default=None, sa_column=Column(LargeBinary(32), index=True)
    )
    ctime: datetime.datetime = Field(
        default_factory=datetime.datetime.utcnow, nullable=False
    )
    mime: Optional[str] = Field(default=None, max_length=255)
    completed: bool = Field(default=False, nullable=False)
    deleted: bool = Field(default=False, nullable=False)
    extra: Optional[dict] = Field(default=None, sa_column=Column(JSONB))

    files: List["File"] = Relationship(
        back_populates="file_object",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


class File(SQLModel, table=True):
    """A source URL that maps to an :class:`Object`."""

    __tablename__ = "file"

    uuid: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid1)
    )
    obj_uuid: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(UUID(as_uuid=True), ForeignKey("object.uuid"), index=True),
    )
    ctime: datetime.datetime = Field(
        default_factory=datetime.datetime.utcnow, nullable=False
    )
    mtime: Optional[datetime.datetime] = Field(default=None)
    url: str = Field(max_length=2047, index=True)
    direct: bool = Field(default=True, nullable=False)
    partial: bool = Field(default=False, nullable=False)
    extra: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    ul_user: Optional[str] = Field(default=None, max_length=15)
    ul_sw: Optional[str] = Field(default=None, max_length=15)
    ul_host: Optional[str] = Field(default=None, max_length=64)

    file_object: Optional[Object] = Relationship(
        back_populates="files",
        sa_relationship_kwargs={"lazy": "joined"},
    )


# Expression index speeding up GET /file/?extra=ytdl-id=... (see issue #79).
# Operators of pre-existing databases can add it via scripts/schema-79.sql.
#Index("ix_file_extra_ytdl_id", File.extra["ytdl-id"].astext)
# NOTE - commented because not generally applicable and maybe wasteful

# Engine / session factory, built from settings at import time.
engine = create_engine(get_settings().database_url)


def get_session():
    """FastAPI dependency yielding a scoped Session."""
    with Session(engine, expire_on_commit=False) as session:
        yield session


__all__ = ["Object", "File", "engine", "get_session", "select", "SQLModel"]
