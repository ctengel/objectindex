"""Object Index database models (SQLAlchemy 2.0 ORM).

The table names, columns, types and indexes match the existing PostgreSQL
schema (see ``schema.sql``) exactly, so this is a drop-in replacement for the
previous Flask-SQLAlchemy models.
"""

import datetime
import uuid
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    create_engine,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from .config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ObjectIndex models."""


class Object(Base):
    """A unique stored object (deduplicated by checksum)."""

    __tablename__ = "object"
    __table_args__ = (Index("buckey", "bucket", "key"),)

    uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid1
    )
    bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    key: Mapped[str] = mapped_column(String(1023), nullable=False)
    # NOTE Postgres doesn't support unsigned
    obj_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[Optional[bytes]] = mapped_column(LargeBinary(32), index=True)
    ctime: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    mime: Mapped[Optional[str]] = mapped_column(String(255))
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)

    files = relationship(
        "File", back_populates="file_object", lazy="selectin"
    )


class File(Base):
    """A source URL that maps to an :class:`Object`."""

    __tablename__ = "file"

    uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid1
    )
    obj_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("object.uuid"), index=True, nullable=True
    )
    ctime: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    mtime: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    url: Mapped[str] = mapped_column(String(2047), index=True, nullable=False)
    direct: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    partial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)
    ul_user: Mapped[Optional[str]] = mapped_column(String(15))
    ul_sw: Mapped[Optional[str]] = mapped_column(String(15))
    ul_host: Mapped[Optional[str]] = mapped_column(String(64))

    file_object = relationship(
        "Object", back_populates="files", lazy="joined"
    )


# Engine / session factory, built from settings at import time.
engine = create_engine(get_settings().database_url, future=True)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, future=True
)


def get_session():
    """FastAPI dependency yielding a scoped Session."""
    with SessionLocal() as session:
        yield session


__all__ = ["Base", "Object", "File", "engine", "SessionLocal", "get_session", "select"]
