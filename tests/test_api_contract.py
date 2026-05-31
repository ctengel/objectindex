"""Black-box characterization tests for the ObjectIndex REST API.

The exact same tests run against the legacy Flask-RESTX app and the new
FastAPI app (see ``conftest.py``'s ``server`` fixture).  They pin the wire
contract that ``gui.py`` / ``clilib.py`` / ``client.py`` depend on.
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


def _upload(api, **kwargs):
    payload = make_payload(**kwargs)
    resp = api.post("/upload/", payload)
    return resp, payload


def _complete(api, object_url):
    return api.put(object_url, {"completed": True})


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------

def test_upload_new(api):
    content = b"brand new content"
    chk = _checksum(content)
    resp, _ = _upload(api, content=content)
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


def test_upload_dedup_returns_existing(api):
    content = b"dedup me"
    resp1, _ = _upload(api, content=content)
    obj_url = resp1.json()["upload"]["finished"]
    assert _complete(api, obj_url).status_code == 200

    # second upload of same checksum from a different url -> exists, download
    resp2, _ = _upload(api, content=content, url="file://host/other/copy.txt")
    assert resp2.status_code == 201
    body = resp2.json()
    assert body["exists"] is True
    assert body["download"] == resp1.json()["upload"]["s3"]


def test_upload_conflict_409_has_object_uuid(api):
    content = b"in progress"
    resp1, _ = _upload(api, content=content)
    obj_uuid = resp1.json()["file"]["file_object"]["uuid"]

    # second upload while the first is still incomplete -> conflict
    resp2, _ = _upload(api, content=content, url="file://host/other.txt")
    assert resp2.status_code == 409
    assert resp2.json()["object_uuid"] == obj_uuid


def test_upload_size_mismatch_rejected(api):
    content = b"sizing"
    resp1, _ = _upload(api, content=content)
    _complete(api, resp1.json()["upload"]["finished"])

    # same checksum, different declared size
    resp2, _ = _upload(api, content=content, obj_size=999999,
                       url="file://host/other.txt")
    assert resp2.status_code >= 400


def test_reupload_after_delete(api):
    content = b"retry me"
    resp1, _ = _upload(api, content=content)
    obj_url = resp1.json()["upload"]["finished"]
    assert api.put(obj_url, {"deleted": True}).status_code == 200

    resp2, _ = _upload(api, content=content)
    assert resp2.status_code == 201
    body = resp2.json()
    assert body["exists"] is False
    assert "upload" in body


def test_unknown_bucket_400_has_bucket(api):
    resp, _ = _upload(api, bucket="nope")
    assert resp.status_code == 400
    assert resp.json()["bucket"] == "nope"


# --------------------------------------------------------------------------
# File endpoints
# --------------------------------------------------------------------------

def test_get_file_404(api):
    resp = api.get(f"/file/{uuid.uuid4()}/")
    assert resp.status_code == 404


def test_get_file_embeds_object(api):
    resp1, _ = _upload(api)
    fil_uuid = resp1.json()["file"]["uuid"]
    resp = api.get(f"/file/{fil_uuid}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["uuid"] == fil_uuid
    assert body["url"] == "file://host/path/hello.txt"
    assert body["file_object"]["key"].endswith("-hello.txt")


def test_file_search_exact(api):
    url = "file://host/exact/one.txt"
    _upload(api, content=b"one", url=url)
    _upload(api, content=b"two", url="file://host/exact/two.txt")
    resp = api.get("/file/", params={"url": url})
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["url"] for r in rows] == [url]
    assert rows[0]["file_object"]  # full object embedded


def test_file_search_wildcard_prefix(api):
    _upload(api, content=b"a", url="file://host/dir/a.txt")
    _upload(api, content=b"b", url="file://host/dir/b.txt")
    _upload(api, content=b"c", url="file://other/c.txt")
    resp = api.get("/file/", params={"url": "file://host/dir/*"})
    assert resp.status_code == 200
    urls = sorted(r["url"] for r in resp.json())
    assert urls == ["file://host/dir/a.txt", "file://host/dir/b.txt"]


def test_file_search_wildcard_escapes_underscore(api):
    # '_' is a SQL LIKE single-char wildcard; it must be escaped so it only
    # matches a literal underscore (regression test for the escaping commit).
    _upload(api, content=b"u1", url="file://host/a_b.txt")
    _upload(api, content=b"u2", url="file://host/axb.txt")
    resp = api.get("/file/", params={"url": "file://host/a_*"})
    assert resp.status_code == 200
    urls = sorted(r["url"] for r in resp.json())
    assert urls == ["file://host/a_b.txt"]


def test_file_search_wildcard_escapes_percent(api):
    _upload(api, content=b"p1", url="file://host/p%q.txt")
    _upload(api, content=b"p2", url="file://host/pXXq.txt")
    resp = api.get("/file/", params={"url": "file://host/p%*"})
    assert resp.status_code == 200
    urls = sorted(r["url"] for r in resp.json())
    assert urls == ["file://host/p%q.txt"]


def test_file_search_by_extra(api):
    # JSONB extra-field search (extra->>key == value). The api.py TODO claiming
    # this returns 0 results is stale; it works under SQLAlchemy 2.0 and the
    # FastAPI rewrite must keep it working.
    url = "file://host/tagged.txt"
    resp1, _ = _upload(api, content=b"tagged", url=url,
                       extra_file={"colour": "blue"})
    _complete(api, resp1.json()["upload"]["finished"])

    resp = api.get("/file/", params={"extra": "colour=blue"})
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["url"] for r in rows] == [url]
    # a non-matching value returns nothing
    assert api.get("/file/", params={"extra": "colour=red"}).json() == []


# --------------------------------------------------------------------------
# Object endpoints
# --------------------------------------------------------------------------

def test_get_object_404(api):
    resp = api.get(f"/object/{uuid.uuid4()}/")
    assert resp.status_code == 404


def test_get_object_hex_and_brief_files(api):
    content = b"object body"
    chk = _checksum(content)
    resp1, _ = _upload(api, content=content)
    obj_uuid = resp1.json()["file"]["file_object"]["uuid"]
    fil_uuid = resp1.json()["file"]["uuid"]

    resp = api.get(f"/object/{obj_uuid}/")
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


def test_object_search_by_checksum(api):
    content = b"searchable"
    chk = _checksum(content)
    _upload(api, content=content)
    resp = api.get("/object/", params={"checksum": chk})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["checksum"] == chk


def test_put_completed(api):
    resp1, _ = _upload(api)
    obj_url = resp1.json()["upload"]["finished"]
    resp = api.put(obj_url, {"completed": True})
    assert resp.status_code == 200
    assert resp.json()["completed"] is True
    assert api.get(obj_url).json()["completed"] is True


def test_put_deleted(api):
    resp1, _ = _upload(api)
    obj_url = resp1.json()["upload"]["finished"]
    resp = api.put(obj_url, {"deleted": True})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_put_both_true_rejected(api):
    resp1, _ = _upload(api)
    obj_url = resp1.json()["upload"]["finished"]
    resp = api.put(obj_url, {"completed": True, "deleted": True})
    assert resp.status_code >= 400


def test_object_download_presigned(api):
    content = b"download body"
    chk = _checksum(content)
    resp1, _ = _upload(api, content=content)
    obj_uuid = resp1.json()["file"]["file_object"]["uuid"]
    resp = api.get(f"/object/{obj_uuid}/download")
    assert resp.status_code == 200
    assert resp.json()["presigned"] == f"{TEST_S3}bucket1/{chk}-hello.txt"
