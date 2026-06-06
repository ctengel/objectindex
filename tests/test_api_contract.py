"""Black-box characterization tests for the ObjectIndex REST API.

Driven in-process via FastAPI's ``TestClient`` (see ``conftest.py``'s ``client``
fixture, which also resets the database to an empty schema before each test).
They pin the wire contract that ``gui.py`` / ``clilib.py`` / ``client.py``
depend on.
"""

import hashlib
import uuid

from conftest import TEST_S3


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def make_payload(content=b"hello world",
                 url="file://host/path/hello.txt",
                 bucket="bucket1",
                 filename="hello.txt",
                 mime="text/plain",
                 direct=True,
                 partial=False,
                 obj_size=None,
                 extra_file=None,
                 extra_object=None,
                 mtime="2021-01-01T00:00:00"):
    """Build a full upload payload, mirroring what the real client sends."""
    payload = {
        "url": url,
        "bucket": bucket,
        "obj_size": len(content) if obj_size is None else obj_size,
        "checksum": _checksum(content),
        "direct": direct,
        "partial": partial,
        "mtime": mtime,
        "filename": filename,
        "mime": mime,
        "ul_user": "tester",
        "ul_sw": "pytest",
        "ul_host": "localhost",
    }
    if extra_file is not None:
        payload["extra_file"] = extra_file
    if extra_object is not None:
        payload["extra_object"] = extra_object
    return payload


def _upload(client, **kwargs):
    payload = make_payload(**kwargs)
    resp = client.post("/upload/", json=payload)
    return resp, payload


def _complete(client, object_url):
    return client.put(object_url, json={"completed": True})


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------

def test_upload_new(client):
    content = b"brand new content"
    chk = _checksum(content)
    resp, _ = _upload(client, content=content)
    assert resp.status_code == 201
    body = resp.json()

    assert body["exists"] is False
    assert "download" not in body or not body["download"]
    assert "upload" in body
    expected_key = f"{chk}-hello.txt"
    assert body["upload"]["s3"] == f"{TEST_S3}bucket1/{expected_key}"

    fil = body["file"]
    assert uuid.UUID(fil["uuid"])
    assert fil["url"] == "file://host/path/hello.txt"
    # file embeds the FULL object
    obj = fil["file_object"]
    assert obj["key"] == expected_key
    assert obj["checksum"] == chk  # hex, not bytes
    assert obj["bucket"] == "bucket1"
    assert obj["completed"] is False
    assert body["upload"]["finished"] == f"/object/{obj['uuid']}/"


def test_upload_rejects_invalid_url(client):
    # A bare string / empty url has no scheme+netloc and is rejected at the
    # request-validation layer (422) before any object is created.
    for bad_url in ("not a url", ""):
        resp, _ = _upload(client, url=bad_url)
        assert resp.status_code == 422


def test_upload_dedup_returns_existing(client):
    content = b"dedup me"
    resp1, _ = _upload(client, content=content)
    obj_url = resp1.json()["upload"]["finished"]
    assert _complete(client, obj_url).status_code == 200

    # second upload of same checksum from a different url -> exists, download
    resp2, _ = _upload(client, content=content, url="file://host/other/copy.txt")
    assert resp2.status_code == 201
    body = resp2.json()
    assert body["exists"] is True
    assert body["download"] == resp1.json()["upload"]["s3"]


def test_upload_conflict_409_has_object_uuid(client):
    content = b"in progress"
    resp1, _ = _upload(client, content=content)
    obj_uuid = resp1.json()["file"]["file_object"]["uuid"]

    # second upload while the first is still incomplete -> conflict
    resp2, _ = _upload(client, content=content, url="file://host/other.txt")
    assert resp2.status_code == 409
    assert resp2.json()["object_uuid"] == obj_uuid


def test_upload_size_mismatch_rejected(client):
    content = b"sizing"
    resp1, _ = _upload(client, content=content)
    _complete(client, resp1.json()["upload"]["finished"])

    # same checksum, different declared size
    resp2, _ = _upload(client, content=content, obj_size=999999,
                       url="file://host/other.txt")
    assert resp2.status_code >= 400


def test_reupload_after_delete(client):
    content = b"retry me"
    resp1, _ = _upload(client, content=content)
    obj_url = resp1.json()["upload"]["finished"]
    assert client.put(obj_url, json={"deleted": True}).status_code == 200

    resp2, _ = _upload(client, content=content)
    assert resp2.status_code == 201
    body = resp2.json()
    assert body["exists"] is False
    assert "upload" in body


def test_unknown_bucket_404(client):
    resp, _ = _upload(client, bucket="nope")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown bucket"


def test_upload_invalid_checksum_400(client):
    payload = make_payload()
    payload["checksum"] = "not-hex"
    resp = client.post("/upload/", json=payload)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "checksum must be hex"


def test_upload_missing_required_field_422(client):
    # FastAPI validates the request body against UploadRequest; a missing
    # required field returns 422 (not possible to assert against flask-restx).
    payload = make_payload()
    del payload["checksum"]
    resp = client.post("/upload/", json=payload)
    assert resp.status_code == 422
    assert any(err["loc"][-1] == "checksum" for err in resp.json()["detail"])


def test_upload_missing_filename_generates_key(client):
    # filename is optional: the server generates a key component from the MIME
    # type rather than rejecting the request or minting a degenerate "{sha256}-".
    payload = make_payload()
    del payload["filename"]
    resp = client.post("/upload/", json=payload)
    assert resp.status_code == 201
    key = resp.json()["file"]["file_object"]["key"]
    suffix = key.split("-", 1)[1]
    assert suffix and suffix != ""  # no degenerate key


def test_upload_empty_string_filename_uses_fallback(client):
    # An empty-string filename must not produce a key ending in just "-".
    payload = make_payload(content=b"empty fn", url="file://host/path/empty.txt")
    payload["filename"] = ""
    resp = client.post("/upload/", json=payload)
    assert resp.status_code == 201
    key = resp.json()["file"]["file_object"]["key"]
    assert not key.endswith("-")


def test_upload_no_filename_with_mime_uses_extension(client):
    # When no filename but MIME is provided, the key suffix includes a file
    # extension derived from the MIME type.
    payload = make_payload(content=b"mp4 content", url="file://host/path/video",
                           mime="video/mp4")
    del payload["filename"]
    resp = client.post("/upload/", json=payload)
    assert resp.status_code == 201
    key = resp.json()["file"]["file_object"]["key"]
    assert key.endswith(".mp4")


# --------------------------------------------------------------------------
# File endpoints
# --------------------------------------------------------------------------

def test_get_file_404(client):
    resp = client.get(f"/file/{uuid.uuid4()}/")
    assert resp.status_code == 404


def test_get_file_embeds_object(client):
    resp1, _ = _upload(client)
    fil_uuid = resp1.json()["file"]["uuid"]
    resp = client.get(f"/file/{fil_uuid}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["uuid"] == fil_uuid
    assert body["url"] == "file://host/path/hello.txt"
    assert body["file_object"]["key"].endswith("-hello.txt")


def test_file_search_exact(client):
    url = "file://host/exact/one.txt"
    _upload(client, content=b"one", url=url)
    _upload(client, content=b"two", url="file://host/exact/two.txt")
    resp = client.get("/file/", params={"url": url})
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["url"] for r in rows] == [url]
    assert rows[0]["file_object"]  # full object embedded


def test_file_search_wildcard_prefix(client):
    _upload(client, content=b"a", url="file://host/dir/a.txt")
    _upload(client, content=b"b", url="file://host/dir/b.txt")
    _upload(client, content=b"c", url="file://other/c.txt")
    resp = client.get("/file/", params={"url": "file://host/dir/*"})
    assert resp.status_code == 200
    urls = sorted(r["url"] for r in resp.json())
    assert urls == ["file://host/dir/a.txt", "file://host/dir/b.txt"]


def test_file_search_wildcard_escapes_underscore(client):
    # '_' is a SQL LIKE single-char wildcard; it must be escaped so it only
    # matches a literal underscore (regression test for the escaping commit).
    _upload(client, content=b"u1", url="file://host/a_b.txt")
    _upload(client, content=b"u2", url="file://host/axb.txt")
    resp = client.get("/file/", params={"url": "file://host/a_*"})
    assert resp.status_code == 200
    urls = sorted(r["url"] for r in resp.json())
    assert urls == ["file://host/a_b.txt"]


def test_file_search_wildcard_escapes_percent(client):
    _upload(client, content=b"p1", url="file://host/p%q.txt")
    _upload(client, content=b"p2", url="file://host/pXXq.txt")
    resp = client.get("/file/", params={"url": "file://host/p%*"})
    assert resp.status_code == 200
    urls = sorted(r["url"] for r in resp.json())
    assert urls == ["file://host/p%q.txt"]


def test_file_search_by_extra(client):
    # JSONB extra-field search (extra->>key == value). The api.py TODO claiming
    # this returns 0 results is stale; it works under SQLAlchemy 2.0 and the
    # FastAPI rewrite must keep it working.
    url = "file://host/tagged.txt"
    resp1, _ = _upload(client, content=b"tagged", url=url,
                       extra_file={"colour": "blue"})
    _complete(client, resp1.json()["upload"]["finished"])

    resp = client.get("/file/", params={"extra": "colour=blue"})
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["url"] for r in rows] == [url]
    # a non-matching value returns nothing
    assert client.get("/file/", params={"extra": "colour=red"}).json() == []


def test_file_search_no_criteria_400(client):
    # Neither url nor extra is a malformed query (the Flask version 500'd on it);
    # it must fail loudly rather than silently returning an empty 200.
    resp = client.get("/file/")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Must search by url or extra"


def test_file_search_both_criteria_400(client):
    resp = client.get("/file/", params={"url": "x", "extra": "k=v"})
    assert resp.status_code == 400


# --------------------------------------------------------------------------
# Object endpoints
# --------------------------------------------------------------------------

def test_get_object_404(client):
    resp = client.get(f"/object/{uuid.uuid4()}/")
    assert resp.status_code == 404


def test_get_object_hex_and_brief_files(client):
    content = b"object body"
    chk = _checksum(content)
    resp1, _ = _upload(client, content=content)
    obj_uuid = resp1.json()["file"]["file_object"]["uuid"]
    fil_uuid = resp1.json()["file"]["uuid"]

    resp = client.get(f"/object/{obj_uuid}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checksum"] == chk  # hex string
    assert body["bucket"] == "bucket1"
    assert body["key"] == f"{chk}-hello.txt"
    # files are BRIEF: uuid + url only
    assert len(body["files"]) == 1
    brief = body["files"][0]
    assert brief["uuid"] == fil_uuid
    assert brief["url"] == "file://host/path/hello.txt"
    assert "direct" not in brief
    assert "file_object" not in brief


def test_object_search_by_checksum(client):
    content = b"searchable"
    chk = _checksum(content)
    _upload(client, content=content)
    resp = client.get("/object/", params={"checksum": chk})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["checksum"] == chk


def test_put_completed(client):
    resp1, _ = _upload(client)
    obj_url = resp1.json()["upload"]["finished"]
    resp = client.put(obj_url, json={"completed": True})
    assert resp.status_code == 200
    assert resp.json()["completed"] is True
    assert client.get(obj_url).json()["completed"] is True


def test_put_deleted(client):
    resp1, _ = _upload(client)
    obj_url = resp1.json()["upload"]["finished"]
    resp = client.put(obj_url, json={"deleted": True})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_put_both_true_rejected(client):
    resp1, _ = _upload(client)
    obj_url = resp1.json()["upload"]["finished"]
    resp = client.put(obj_url, json={"completed": True, "deleted": True})
    assert resp.status_code >= 400


def test_object_download_presigned(client):
    content = b"download body"
    chk = _checksum(content)
    resp1, _ = _upload(client, content=content)
    obj_uuid = resp1.json()["file"]["file_object"]["uuid"]
    _complete(client, resp1.json()["upload"]["finished"])
    resp = client.get(f"/object/{obj_uuid}/download")
    assert resp.status_code == 200
    assert resp.json()["presigned"] == f"{TEST_S3}bucket1/{chk}-hello.txt"


def test_object_download_incomplete_503(client):
    # Upload initiated but not completed -> upload may still be in progress.
    resp1, _ = _upload(client, content=b"in progress")
    obj_uuid = resp1.json()["file"]["file_object"]["uuid"]
    resp = client.get(f"/object/{obj_uuid}/download")
    assert resp.status_code == 503


def test_object_download_deleted_410(client):
    resp1, _ = _upload(client, content=b"to be deleted")
    obj_uuid = resp1.json()["file"]["file_object"]["uuid"]
    client.put(resp1.json()["upload"]["finished"], json={"deleted": True})
    resp = client.get(f"/object/{obj_uuid}/download")
    assert resp.status_code == 410


# --------------------------------------------------------------------------
# FastAPI surface
# --------------------------------------------------------------------------

def test_openapi_available(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert set(paths) >= {
        "/upload/", "/file/", "/file/{fil_uuid}/",
        "/object/", "/object/{obj_uuid}/", "/object/{obj_uuid}/download",
    }
