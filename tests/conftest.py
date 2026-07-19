"""Shared fixtures for the ObjectIndex API contract tests.

The suite drives the FastAPI app in-process via Starlette's ``TestClient`` and
pins the REST wire contract that ``gui.py`` / ``clilib.py`` / ``client.py``
depend on.

The app still talks to a **real PostgreSQL** given by ``TEST_DATABASE_URL``
(JSONB / bytea / LIKE-escaping are Postgres-specific — ``TestClient`` only
replaces the HTTP transport, not the database). The two tables are recreated
from canonical DDL before every test.
"""

import os

import pytest

# Point the app at the test database *before* importing it: the engine and
# settings bind at import time (see obj_idx/db.py). Set these explicitly so an
# ambient OBJIDX_* in the environment can't leak a real database into the tests.
TEST_S3 = "http://s3.example/"
os.environ["OBJIDX_DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://claude@/objidx_test?host=/tmp"
)
os.environ["OBJIDX_S3"] = TEST_S3
os.environ["OBJIDX_BUCKETS"] = "bucket1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from obj_idx import config  # noqa: E402
from obj_idx.api import app  # noqa: E402
from obj_idx.db import engine  # noqa: E402

# Three clients for the auth tests: alice has full access to bucket1, bob is
# read-only there, carol write-only. Same TOML format as simpler-objects'
# auth.toml.
ALICE_KEY = "alice-secret-key"
BOB_KEY = "bob-secret-key"
CAROL_KEY = "carol-secret-key"
AUTH_TOML = f"""
[clients.alice]
key = "{ALICE_KEY}"
[clients.alice.buckets]
"bucket1" = ["read", "write", "list"]

[clients.bob]
key = "{BOB_KEY}"
[clients.bob.buckets]
"bucket1" = ["read"]

[clients.carol]
key = "{CAROL_KEY}"
[clients.carol.buckets]
"bucket1" = ["write"]
"""

# Canonical schema, mirroring schema.sql (minus pg_dump noise / owners). Kept as
# a literal so the tests run against the contract schema, independent of the ORM.
SCHEMA_DDL = """
DROP TABLE IF EXISTS file CASCADE;
DROP TABLE IF EXISTS object CASCADE;
CREATE TABLE object (
    uuid uuid NOT NULL PRIMARY KEY,
    bucket character varying(63) NOT NULL,
    key character varying(1023) NOT NULL,
    obj_size bigint NOT NULL,
    checksum bytea,
    ctime timestamp without time zone NOT NULL,
    mime character varying(255),
    completed boolean NOT NULL,
    deleted boolean NOT NULL,
    extra jsonb
);
CREATE TABLE file (
    uuid uuid NOT NULL PRIMARY KEY,
    obj_uuid uuid REFERENCES object(uuid),
    ctime timestamp without time zone NOT NULL,
    mtime timestamp without time zone,
    url character varying(2047) NOT NULL,
    direct boolean NOT NULL,
    partial boolean NOT NULL,
    extra jsonb,
    ul_user character varying(15),
    ul_sw character varying(15),
    ul_host character varying(64)
);
CREATE INDEX buckey ON object USING btree (bucket, key);
CREATE INDEX ix_file_obj_uuid ON file USING btree (obj_uuid);
CREATE INDEX ix_file_url ON file USING btree (url);
CREATE INDEX ix_object_checksum ON object USING btree (checksum);
"""

_client = TestClient(app)


def _reset_schema():
    with engine.begin() as conn:
        for statement in filter(None, (s.strip() for s in SCHEMA_DDL.split(";"))):
            conn.execute(text(statement))


@pytest.fixture()
def client():
    """Reset to an empty schema, then yield the in-process TestClient."""
    _reset_schema()
    return _client


@pytest.fixture()
def auth_client(tmp_path):
    """TestClient with OBJIDX_AUTH_CONFIG pointing at the alice/bob config.

    The auth dependency reads config.get_auth() per request, so clearing the
    settings caches around the env change is all that's needed; the DB engine
    binding (import time) is unaffected.
    """
    auth_path = tmp_path / "auth.toml"
    auth_path.write_text(AUTH_TOML)
    auth_path.chmod(0o600)  # avoid AuthConfig.load's permissions warning
    os.environ["OBJIDX_AUTH_CONFIG"] = str(auth_path)
    config.get_settings.cache_clear()
    config.get_auth.cache_clear()
    _reset_schema()
    yield _client
    del os.environ["OBJIDX_AUTH_CONFIG"]
    config.get_settings.cache_clear()
    config.get_auth.cache_clear()
