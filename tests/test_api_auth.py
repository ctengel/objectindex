"""API auth contract: 401/403 behavior, ul_user override, opt-in-off path.

Uses the ``auth_client`` fixture (alice = read/write/list on bucket1, bob =
read-only, carol = write-only; see ``conftest.AUTH_TOML``). The ``client``
fixture runs with auth off and pins that nothing requires credentials then.
"""

import base64

import pytest
from pydantic import ValidationError

from obj_idx.config import Settings, get_auth

from conftest import TEST_S3, ALICE_KEY, BOB_KEY, CAROL_KEY
from test_api_contract import make_payload, _checksum


def bearer(key):
    return {"Authorization": f"Bearer {key}"}


def basic(name, key):
    token = base64.b64encode(f"{name}:{key}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


SOME_UUID = "00000000-0000-0000-0000-000000000000"
ALL_ENDPOINTS = [
    ("post", "/upload/", make_payload()),
    ("get", "/file/?url=file://host/x", None),
    ("get", f"/file/{SOME_UUID}/", None),
    ("get", f"/object/?checksum={'0' * 64}", None),
    ("get", f"/object/{SOME_UUID}/", None),
    ("get", "/buckets/bucket1/", None),
    ("put", f"/object/{SOME_UUID}/", {"completed": True}),
    ("get", f"/object/{SOME_UUID}/download", None),
]


def _upload_completed(client, headers, content=b"auth bytes"):
    """Upload and complete an object as the given client; return its uuid."""
    resp = client.post("/upload/", json=make_payload(content=content),
                       headers=headers)
    assert resp.status_code == 201
    obj_uuid = resp.json()["file"]["file_object"]["uuid"]
    assert client.put(f"/object/{obj_uuid}/", json={"completed": True},
                      headers=headers).status_code == 200
    return obj_uuid


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,json", ALL_ENDPOINTS)
def test_all_endpoints_401_without_credentials(auth_client, method, path, json):
    resp = auth_client.request(method, path, json=json)
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"].startswith("Basic")


@pytest.mark.parametrize("method,path,json", ALL_ENDPOINTS)
def test_all_endpoints_401_with_bad_key(auth_client, method, path, json):
    resp = auth_client.request(method, path, json=json,
                               headers=bearer("wrong-key"))
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path,json", ALL_ENDPOINTS)
def test_auth_off_never_401(client, method, path, json):
    resp = client.request(method, path, json=json)
    assert resp.status_code not in (401, 403)


def test_basic_auth_accepted(auth_client):
    resp = auth_client.get("/buckets/bucket1/", headers=basic("alice", ALICE_KEY))
    assert resp.status_code == 200


# --------------------------------------------------------------------------
# Authorization / ul_user
# --------------------------------------------------------------------------

def test_upload_overrides_ul_user(auth_client):
    # make_payload self-reports ul_user="tester"; the server must replace it
    # with the authenticated client name.
    resp = auth_client.post("/upload/", json=make_payload(),
                            headers=bearer(ALICE_KEY))
    assert resp.status_code == 201
    assert resp.json()["file"]["ul_user"] == "alice"


def test_upload_requires_write(auth_client):
    resp = auth_client.post("/upload/", json=make_payload(),
                            headers=bearer(BOB_KEY))
    assert resp.status_code == 403


def test_upload_unknown_bucket_403_before_404(auth_client):
    # No grant on bucket2 -> 403, not the unknown-bucket 404: an ungranted
    # client must not learn which buckets exist.
    resp = auth_client.post("/upload/", json=make_payload(bucket="bucket2"),
                            headers=bearer(ALICE_KEY))
    assert resp.status_code == 403


def test_bucket_list_requires_list(auth_client):
    assert auth_client.get("/buckets/bucket1/",
                           headers=bearer(BOB_KEY)).status_code == 403
    assert auth_client.get("/buckets/bucket1/",
                           headers=bearer(ALICE_KEY)).status_code == 200


def test_update_object_requires_write(auth_client):
    obj_uuid = _upload_completed(auth_client, bearer(ALICE_KEY))
    resp = auth_client.put(f"/object/{obj_uuid}/", json={"deleted": True},
                           headers=bearer(BOB_KEY))
    assert resp.status_code == 403


def test_download_requires_read(auth_client):
    content = b"downloadable"
    obj_uuid = _upload_completed(auth_client, bearer(ALICE_KEY), content=content)
    resp = auth_client.get(f"/object/{obj_uuid}/download",
                           headers=bearer(BOB_KEY))
    assert resp.status_code == 200
    # Clean locator URL: no credentials embedded (issue #25)
    key = f"{_checksum(content)}-hello.txt"
    assert resp.json()["presigned"] == f"{TEST_S3}bucket1/{key}"
    assert auth_client.get(f"/object/{obj_uuid}/download",
                           headers=bearer(CAROL_KEY)).status_code == 403


def test_metadata_any_authenticated(auth_client):
    # Metadata endpoints require authn but no per-bucket grant: carol
    # (write-only) can still search/read metadata.
    obj_uuid = _upload_completed(auth_client, bearer(ALICE_KEY))
    resp = auth_client.get(f"/object/{obj_uuid}/", headers=bearer(CAROL_KEY))
    assert resp.status_code == 200
    resp = auth_client.get("/file/?url=file://host/path/hello.txt",
                           headers=bearer(CAROL_KEY))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def test_s3_with_credentials_rejected_at_startup():
    # other required fields come from the env set in conftest
    with pytest.raises(ValidationError):
        Settings(s3="http://user:pass@localhost:9000/")
    with pytest.raises(ValidationError):
        Settings(s3="http://user@localhost:9000/")
    assert Settings(s3="http://localhost:9000/").s3 == "http://localhost:9000/"


def test_auth_off_by_default(client):
    assert get_auth() is None
