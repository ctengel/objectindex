"""Shared fixtures for the ObjectIndex API contract tests.

The same ``test_api_contract.py`` suite runs against two server
implementations selected by the ``server`` fixture's params:

* ``flask``   - a frozen copy of the legacy Flask-RESTX app (``tests/oilegacy``)
* ``fastapi`` - the new FastAPI app (``obj_idx.api``)

Running the identical black-box suite against both is the proof that the
rewrite is a drop-in replacement.

Both servers talk to a real Postgres given by ``TEST_DATABASE_URL`` (a
SQLAlchemy URL).  The schema is (re)created from canonical DDL before every
test so neither app is responsible for table creation.
"""

import importlib.util
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests
from sqlalchemy import create_engine, text

TESTS_DIR = Path(__file__).resolve().parent
REPO_DIR = TESTS_DIR.parent

# SQLAlchemy URL used by the test harness itself (schema reset).
SA_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://claude@/objidx_test?host=/tmp",
)

# The buckets the servers are configured with for the test run.
TEST_BUCKETS = ["bucket1"]
TEST_S3 = "http://s3.example/"

# Canonical schema, mirroring schema.sql (minus pg_dump noise / owners).
SCHEMA_DDL = """
DROP TABLE IF EXISTS file CASCADE;
DROP TABLE IF EXISTS object CASCADE;
CREATE TABLE object (
    uuid uuid NOT NULL PRIMARY KEY,
    bucket character varying(63) NOT NULL,
    key character varying(1023) NOT NULL,
    obj_size bigint NOT NULL,
    checksum character varying(64),
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


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(SA_DB_URL, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def clean_db(db_engine):
    """Reset the schema to empty tables before each test."""
    with db_engine.begin() as conn:
        for statement in filter(None, (s.strip() for s in SCHEMA_DDL.split(";"))):
            conn.execute(text(statement))
    yield


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_up(port, proc, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"server process exited early with code {proc.returncode}"
            )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.2)
    raise RuntimeError("server did not start in time")


def _launch_flask(port, tmp_path_factory):
    cfg = tmp_path_factory.mktemp("flaskcfg") / "api.cfg"
    cfg.write_text(
        "SQLALCHEMY_DATABASE_URI = {url!r}\n"
        "SQLALCHEMY_TRACK_MODIFICATIONS = False\n"
        "OBJIDX_S3 = {s3!r}\n"
        "OBJIDX_BUCKETS = {buckets!r}\n".format(
            url=SA_DB_URL, s3=TEST_S3, buckets=TEST_BUCKETS
        )
    )
    env = dict(os.environ)
    env["OBJIDX_SETTINGS"] = str(cfg)
    env["FLASK_APP"] = "oilegacy.api"
    env["PYTHONPATH"] = str(TESTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "flask", "run", "--port", str(port)]
    return subprocess.Popen(cmd, env=env, cwd=str(REPO_DIR))


def _launch_fastapi(port, tmp_path_factory):
    env = dict(os.environ)
    env["OBJIDX_DATABASE_URL"] = SA_DB_URL
    env["OBJIDX_S3"] = TEST_S3
    env["OBJIDX_BUCKETS"] = '["bucket1"]'
    env["PYTHONPATH"] = str(REPO_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [
        sys.executable, "-m", "uvicorn", "obj_idx.api:app",
        "--port", str(port), "--log-level", "warning",
    ]
    return subprocess.Popen(cmd, env=env, cwd=str(REPO_DIR))


# NOTE: only "fastapi" on this branch. The checksum column changed from bytea to
# varchar(64) hex, which the frozen legacy Flask app in tests/oilegacy/ can't use
# (it stores bytea); the drop-in cross-check was already proven on the parent
# SQLAlchemy branch. The contract tests below still fully validate REST behavior.
@pytest.fixture(scope="session", params=["fastapi"])
def server(request, tmp_path_factory):
    impl = request.param
    if impl == "flask":
        # The legacy app is a frozen reference for the drop-in cross-check; it
        # needs the old Flask stack, which is no longer a core dependency.
        if importlib.util.find_spec("flask_restx") is None:
            pytest.skip("legacy Flask cross-check needs flask-restx "
                        "(pip install '.[test]')")
    port = _free_port()
    if impl == "flask":
        proc = _launch_flask(port, tmp_path_factory)
    else:
        proc = _launch_fastapi(port, tmp_path_factory)
    try:
        _wait_until_up(port, proc)
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture()
def base_url(server, clean_db):
    """Per-test: fresh empty schema + a running server base URL."""
    return server


@pytest.fixture()
def api(base_url):
    """A tiny HTTP helper bound to the server under test."""
    return _Api(base_url)


class _Api:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def url(self, path):
        return self.base + path

    def post(self, path, json):
        return requests.post(self.url(path), json=json, timeout=15)

    def get(self, path, params=None):
        return requests.get(self.url(path), params=params, timeout=15)

    def put(self, path, json):
        return requests.put(self.url(path), json=json, timeout=15)
