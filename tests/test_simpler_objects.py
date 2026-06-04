"""Tests for client.py's interaction with the simpler-objects HTTP store.

simple_upload  → PUT /{bucket}/{key}
simple_download → GET /{bucket}/{key}

Responses are mocked to match the simpler-objects OpenAPI contract
(https://github.com/ctengel/simpler-objects/blob/main/openapi.yaml).

Also covers simple_download behaviour with arbitrary (non-simpler-objects) URLs,
which is the main path for upload_remote of generic web content.
"""

import base64
import datetime
import hashlib
import io
import tempfile
from unittest.mock import Mock, patch, call

import pytest
import requests

from obj_idx import client

CONTENT = b'simpler objects test content'
CKSUM_BYTES = hashlib.sha256(CONTENT).digest()
CKSUM_B64 = base64.b64encode(CKSUM_BYTES).decode()
S3_URL = 'http://s3.example/bucket1/abc-test.mp4'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _put_response(status_code=201):
    """Simulate a simpler-objects PUT response."""
    m = Mock()
    m.status_code = status_code
    if status_code >= 400:
        m.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=Mock(status_code=status_code)
        )
    else:
        m.raise_for_status.return_value = None
    return m


def _get_response(content=CONTENT, headers=None, status_code=200):
    """Simulate a simpler-objects GET response with chunked streaming."""
    hdrs = headers or {}
    m = Mock()
    m.status_code = status_code
    m.headers = hdrs
    if status_code >= 400:
        m.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=Mock(status_code=status_code)
        )
    else:
        m.raise_for_status.return_value = None
    # Stream content in one chunk (mirrors real requests streaming)
    m.iter_content.return_value = [content] if content else []
    return m


# ---------------------------------------------------------------------------
# simple_upload — PUT contract
# ---------------------------------------------------------------------------

def test_simple_upload_sets_content_type():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(201)
            client.simple_upload(tf.name, S3_URL, 'video/mp4')
    headers = mock_req.put.call_args.kwargs['headers']
    assert headers['Content-Type'] == 'video/mp4'


def test_simple_upload_sends_content_digest_when_checksum_provided():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(201)
            client.simple_upload(tf.name, S3_URL, 'video/mp4', checksum_val=CKSUM_BYTES)
    headers = mock_req.put.call_args.kwargs['headers']
    assert 'Content-Digest' in headers
    assert headers['Content-Digest'].startswith('sha-256=:')
    assert headers['Content-Digest'].endswith(':')
    # Verify the base64 payload round-trips to the original checksum
    encoded = client.encode_digest_header(CKSUM_BYTES)
    assert headers['Content-Digest'] == encoded


def test_simple_upload_no_content_digest_without_checksum():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(201)
            client.simple_upload(tf.name, S3_URL, 'video/mp4', checksum_val=None)
    headers = mock_req.put.call_args.kwargs['headers']
    assert 'Content-Digest' not in headers


def test_simple_upload_streams_file_body():
    """File must be passed as a file object (data=), not pre-loaded bytes."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(201)
            client.simple_upload(tf.name, S3_URL, 'video/mp4')
    data_arg = mock_req.put.call_args.kwargs['data']
    # Should be a file-like object, not bytes loaded into memory
    assert hasattr(data_arg, 'read')
    assert not isinstance(data_arg, (bytes, bytearray))


def test_simple_upload_correct_url():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(201)
            client.simple_upload(tf.name, S3_URL, 'video/mp4')
    assert mock_req.put.call_args.args[0] == S3_URL


def test_simple_upload_201_success():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(201)
            # Must not raise
            client.simple_upload(tf.name, S3_URL, 'video/mp4')


def test_simple_upload_400_digest_mismatch_raises():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(400)
            with pytest.raises(requests.exceptions.HTTPError):
                client.simple_upload(tf.name, S3_URL, 'video/mp4')


def test_simple_upload_409_conflict_raises():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(409)
            with pytest.raises(requests.exceptions.HTTPError):
                client.simple_upload(tf.name, S3_URL, 'video/mp4')


def test_simple_upload_415_mime_mismatch_raises():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(415)
            with pytest.raises(requests.exceptions.HTTPError):
                client.simple_upload(tf.name, S3_URL, 'video/mp4')


def test_simple_upload_507_no_space_raises():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.put.return_value = _put_response(507)
            with pytest.raises(requests.exceptions.HTTPError):
                client.simple_upload(tf.name, S3_URL, 'video/mp4')


# ---------------------------------------------------------------------------
# simple_download — GET contract (simpler-objects as source)
# ---------------------------------------------------------------------------

def test_simple_download_sends_want_content_digest_header():
    """Client must advertise its preference for a SHA-256 digest."""
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response()
            client.simple_download(S3_URL, tf.name)
    req_headers = mock_req.get.call_args.kwargs['headers']
    assert req_headers.get('Want-Content-Digest') == 'sha-256=9'


def test_simple_download_uses_streaming():
    """Must use stream=True so large files are not loaded into memory."""
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response()
            client.simple_download(S3_URL, tf.name)
    assert mock_req.get.call_args.kwargs.get('stream') is True


def test_simple_download_picks_up_content_digest():
    """When the server returns Content-Digest, digest is decoded to bytes."""
    hdrs = {
        'Content-Digest': f'sha-256=:{CKSUM_B64}:',
        'Content-Type': 'video/mp4',
    }
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(headers=hdrs)
            digest, mime, fname, mtime = client.simple_download(S3_URL, tf.name)
    assert digest == CKSUM_BYTES
    assert isinstance(digest, bytes)


@pytest.mark.xfail(strict=True,
                   reason="bug: simple_download reads Content-Digest only; "
                          "simpler-objects returns Repr-Digest (openapi.yaml). "
                          "Fix: also check result.headers.get('Repr-Digest') "
                          "when Content-Digest is absent.")
def test_simple_download_repr_digest_not_picked_up():
    """simple_download should decode Repr-Digest returned by simpler-objects.
    Currently it only reads Content-Digest, so digest is always None against a
    real simpler-objects server and the integrity check is silently skipped."""
    hdrs = {
        'Repr-Digest': f'sha-256=:{CKSUM_B64}:',  # what simpler-objects actually sends
        'Content-Type': 'application/octet-stream',
        # No Content-Digest header
    }
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(headers=hdrs)
            digest, _, _, _ = client.simple_download(S3_URL, tf.name)
    assert digest == CKSUM_BYTES  # Repr-Digest should be decoded just like Content-Digest


def test_simple_download_reads_content_type():
    hdrs = {'Content-Type': 'video/webm'}
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(headers=hdrs)
            _, mime, _, _ = client.simple_download(S3_URL, tf.name)
    assert mime == 'video/webm'


def test_simple_download_reads_content_disposition():
    hdrs = {'Content-Disposition': 'attachment; filename="video.mp4"'}
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(headers=hdrs)
            _, _, sugg_fname, _ = client.simple_download(S3_URL, tf.name)
    assert sugg_fname == 'video.mp4'


def test_simple_download_reads_last_modified():
    hdrs = {'Last-Modified': 'Mon, 01 Jan 2024 00:00:00 GMT'}
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(headers=hdrs)
            _, _, _, mtime = client.simple_download(S3_URL, tf.name)
    assert isinstance(mtime, datetime.datetime)
    assert mtime.year == 2024


def test_simple_download_writes_chunks_to_file():
    """Streamed chunks must be written to the output file."""
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(content=CONTENT)
            client.simple_download(S3_URL, tf.name)
        tf.seek(0)
        assert tf.read() == CONTENT


def test_simple_download_404_raises():
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(status_code=404)
            with pytest.raises(requests.exceptions.HTTPError):
                client.simple_download(S3_URL, tf.name)


# ---------------------------------------------------------------------------
# simple_download — arbitrary website behaviour
# ---------------------------------------------------------------------------

def test_simple_download_arbitrary_no_digest_headers():
    """Generic websites don't send Content-Digest; digest must be None."""
    hdrs = {'Content-Type': 'text/html; charset=utf-8'}  # no digest headers at all
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(content=b'<html/>', headers=hdrs)
            digest, mime, sugg_fname, mtime = client.simple_download(
                'http://example.com/page', tf.name
            )
    assert digest is None
    assert mime == 'text/html; charset=utf-8'
    assert sugg_fname is None
    assert mtime is None


def test_simple_download_arbitrary_no_content_disposition():
    """No Content-Disposition header → sugg_fname is None."""
    hdrs = {'Content-Type': 'application/zip'}
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(headers=hdrs)
            _, _, sugg_fname, _ = client.simple_download(
                'http://example.com/archive', tf.name
            )
    assert sugg_fname is None


def test_simple_download_arbitrary_no_last_modified():
    """No Last-Modified header → mtime is None."""
    hdrs = {'Content-Type': 'image/jpeg'}
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(headers=hdrs)
            _, _, _, mtime = client.simple_download(
                'http://example.com/photo.jpg', tf.name
            )
    assert mtime is None


def test_simple_download_arbitrary_html_content_type():
    """text/html from a website is returned as the mime type."""
    hdrs = {'Content-Type': 'text/html'}
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(content=b'<html/>', headers=hdrs)
            _, mime, _, _ = client.simple_download('http://example.com/', tf.name)
    assert mime == 'text/html'


def test_simple_download_arbitrary_binary_content_written():
    """Binary content from any URL is streamed to disk unchanged."""
    binary_content = bytes(range(256)) * 4  # 1 KB of arbitrary bytes
    with tempfile.NamedTemporaryFile() as tf:
        with patch('obj_idx.client.requests') as mock_req:
            mock_req.get.return_value = _get_response(
                content=binary_content,
                headers={'Content-Type': 'application/octet-stream'},
            )
            client.simple_download('http://example.com/binary', tf.name)
        tf.seek(0)
        assert tf.read() == binary_content
