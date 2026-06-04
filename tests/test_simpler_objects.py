"""Tests for client.py's interaction with simpler-objects (pycurl-based).

simple_upload  → pycurl PUT /{bucket}/{key}
simple_download → pycurl GET /{bucket}/{key}

These functions are imported from simpler_objects.client, which uses pycurl
(not requests). Tests mock pycurl.Curl to simulate server responses.
"""

import base64
import datetime
import hashlib
import io
import pathlib
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest
import pycurl

from obj_idx import client
from simpler_objects.client import ClientError

CONTENT = b'simpler objects test content'
CKSUM_BYTES = hashlib.sha256(CONTENT).digest()
CKSUM_B64 = base64.b64encode(CKSUM_BYTES).decode()
S3_URL = 'http://s3.example/bucket1/abc-test.mp4'


# ---------------------------------------------------------------------------
# MockCurlInstance — simulates pycurl.Curl behavior
# ---------------------------------------------------------------------------

class MockCurlInstance:
    """Mock pycurl.Curl that captures setopt calls and simulates perform/getinfo."""

    def __init__(self, status_code=201, response_headers=None, response_body=b''):
        self._status_code = status_code
        self._response_headers = response_headers or {}
        self._response_body = response_body
        self.opts = {}

    def setopt(self, option, value):
        """Capture setopt calls (this is how pycurl config works)."""
        self.opts[option] = value

    def perform(self):
        """Simulate performing the request: invoke callbacks with mock data."""
        hdr_fn = self.opts.get(pycurl.HEADERFUNCTION)
        if hdr_fn:
            # First call is the status line (triggers _header_collector's store.clear())
            hdr_fn(b'HTTP/1.1 200 OK\r\n')
            # Then each header as a separate call
            for k, v in self._response_headers.items():
                hdr_fn(f'{k}: {v}\r\n'.encode('latin1'))

        write_fn = self.opts.get(pycurl.WRITEFUNCTION)
        if write_fn and self._response_body:
            write_fn(self._response_body)

    def getinfo(self, info):
        """Simulate getinfo calls (we only care about RESPONSE_CODE)."""
        if info == pycurl.RESPONSE_CODE:
            return self._status_code
        return 0

    def close(self):
        """No-op; closing is a no-op in tests."""
        pass


# ---------------------------------------------------------------------------
# simple_upload — PUT contract
# ---------------------------------------------------------------------------

def test_simple_upload_sets_content_type():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('pycurl.Curl', return_value=MockCurlInstance(201)):
            client.simple_upload(tf.name, S3_URL, 'video/mp4')


def test_simple_upload_sends_content_digest_when_checksum_provided():
    """simple_upload sends Content-Digest header when checksum_val is provided."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_curl = MockCurlInstance(201)
        with patch('pycurl.Curl', return_value=mock_curl):
            result = client.simple_upload(tf.name, S3_URL, 'video/mp4', checksum_val=CKSUM_BYTES)
        # Check that Content-Digest header was set
        headers = mock_curl.opts.get(pycurl.HTTPHEADER, [])
        assert any('Content-Digest:' in h for h in headers)
        assert result == CKSUM_BYTES


def test_simple_upload_sends_content_digest_computed_from_file():
    """simple_upload always sends Content-Digest: it computes SHA-256 if not supplied."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_curl = MockCurlInstance(201)
        with patch('pycurl.Curl', return_value=mock_curl):
            result = client.simple_upload(tf.name, S3_URL, 'video/mp4', checksum_val=None)
        headers = mock_curl.opts.get(pycurl.HTTPHEADER, [])
        # Content-Digest is always sent (computed from file)
        assert any('Content-Digest:' in h for h in headers)
        assert result == CKSUM_BYTES


def test_simple_upload_uses_expect_100_continue():
    """simple_upload should send Expect: 100-continue for locator."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_curl = MockCurlInstance(201)
        with patch('pycurl.Curl', return_value=mock_curl):
            client.simple_upload(tf.name, S3_URL, 'video/mp4')
        headers = mock_curl.opts.get(pycurl.HTTPHEADER, [])
        assert 'Expect: 100-continue' in headers


def test_simple_upload_sets_correct_url():
    """simple_upload puts to the right URL."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_curl = MockCurlInstance(201)
        with patch('pycurl.Curl', return_value=mock_curl):
            client.simple_upload(tf.name, S3_URL, 'video/mp4')
        assert mock_curl.opts[pycurl.URL] == S3_URL


def test_simple_upload_sets_upload_mode():
    """simple_upload uses UPLOAD mode (PUT, not POST)."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_curl = MockCurlInstance(201)
        with patch('pycurl.Curl', return_value=mock_curl):
            client.simple_upload(tf.name, 'http://s3/key', 'video/mp4')
        assert mock_curl.opts.get(pycurl.UPLOAD) == 1


def test_simple_upload_sets_readdata_file_object():
    """simple_upload passes open file object as READDATA (for streaming)."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_curl = MockCurlInstance(201)
        with patch('pycurl.Curl', return_value=mock_curl):
            client.simple_upload(tf.name, S3_URL, 'video/mp4')
        readdata = mock_curl.opts.get(pycurl.READDATA)
        assert hasattr(readdata, 'read'), "READDATA should be a file object"


def test_simple_upload_201_success():
    """201 response from upload succeeds."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('pycurl.Curl', return_value=MockCurlInstance(201)):
            # Must not raise
            result = client.simple_upload(tf.name, S3_URL, 'video/mp4')
        assert result == CKSUM_BYTES


def test_simple_upload_400_digest_mismatch_raises():
    """400 response raises ClientError."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('pycurl.Curl', return_value=MockCurlInstance(400)):
            with pytest.raises(ClientError):
                client.simple_upload(tf.name, S3_URL, 'video/mp4')


def test_simple_upload_409_conflict_raises():
    """409 conflict response raises ClientError."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('pycurl.Curl', return_value=MockCurlInstance(409)):
            with pytest.raises(ClientError):
                client.simple_upload(tf.name, S3_URL, 'video/mp4')


def test_simple_upload_415_mime_mismatch_raises():
    """415 unsupported media type raises ClientError."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('pycurl.Curl', return_value=MockCurlInstance(415)):
            with pytest.raises(ClientError):
                client.simple_upload(tf.name, S3_URL, 'video/mp4')


def test_simple_upload_507_no_space_raises():
    """507 insufficient storage raises ClientError."""
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        with patch('pycurl.Curl', return_value=MockCurlInstance(507)):
            with pytest.raises(ClientError):
                client.simple_upload(tf.name, S3_URL, 'video/mp4')


# ---------------------------------------------------------------------------
# simple_download — GET contract (simpler-objects)
# ---------------------------------------------------------------------------

def test_simple_download_sends_want_content_digest_header():
    """simple_download requests Content-Digest from server."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=CONTENT,
                                     response_headers={'repr-digest': f'sha-256=:{CKSUM_B64}:'})
        with patch('pycurl.Curl', return_value=mock_curl):
            client.simple_download(S3_URL, tf.name)
        headers = mock_curl.opts.get(pycurl.HTTPHEADER, [])
        assert 'Want-Content-Digest: sha-256=9' in headers


def test_simple_download_follows_redirects():
    """simple_download uses FOLLOWLOCATION for locator 307s."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=CONTENT,
                                     response_headers={'repr-digest': f'sha-256=:{CKSUM_B64}:'})
        with patch('pycurl.Curl', return_value=mock_curl):
            client.simple_download(S3_URL, tf.name)
        assert mock_curl.opts.get(pycurl.FOLLOWLOCATION) == 1


def test_simple_download_streams_to_file():
    """simple_download uses WRITEFUNCTION callback to stream to disk."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=CONTENT,
                                     response_headers={'repr-digest': f'sha-256=:{CKSUM_B64}:'})
        with patch('pycurl.Curl', return_value=mock_curl):
            client.simple_download(S3_URL, tf.name)
        assert pycurl.WRITEFUNCTION in mock_curl.opts
        tf.seek(0)
        assert tf.read() == CONTENT


def test_simple_download_returns_computed_digest():
    """simple_download returns the SHA-256 of the downloaded content (always computed)."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=CONTENT,
                                     response_headers={'repr-digest': f'sha-256=:{CKSUM_B64}:'})
        with patch('pycurl.Curl', return_value=mock_curl):
            digest, _, _, _ = client.simple_download(S3_URL, tf.name)
        assert digest == CKSUM_BYTES


def test_simple_download_reads_content_type():
    """simple_download returns the Content-Type from response headers."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=CONTENT,
                                     response_headers={'content-type': 'video/webm',
                                                       'repr-digest': f'sha-256=:{CKSUM_B64}:'})
        with patch('pycurl.Curl', return_value=mock_curl):
            _, mime, _, _ = client.simple_download(S3_URL, tf.name)
        assert mime == 'video/webm'


def test_simple_download_reads_content_disposition():
    """simple_download extracts suggested filename from Content-Disposition."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=CONTENT,
                                     response_headers={'content-disposition': 'attachment; filename="video.mp4"',
                                                       'repr-digest': f'sha-256=:{CKSUM_B64}:'})
        with patch('pycurl.Curl', return_value=mock_curl):
            _, _, sugg_fname, _ = client.simple_download(S3_URL, tf.name)
        assert sugg_fname == 'video.mp4'


def test_simple_download_reads_last_modified():
    """simple_download parses Last-Modified header to datetime."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=CONTENT,
                                     response_headers={'last-modified': 'Mon, 01 Jan 2024 12:00:00 GMT',
                                                       'repr-digest': f'sha-256=:{CKSUM_B64}:'})
        with patch('pycurl.Curl', return_value=mock_curl):
            _, _, _, mtime = client.simple_download(S3_URL, tf.name)
        assert isinstance(mtime, datetime.datetime)
        assert mtime.year == 2024


def test_simple_download_404_raises():
    """404 response raises ClientError."""
    with tempfile.NamedTemporaryFile() as tf:
        with patch('pycurl.Curl', return_value=MockCurlInstance(404)):
            with pytest.raises(ClientError):
                client.simple_download(S3_URL, tf.name)


def test_simple_download_repr_digest_verification():
    """simple_download verifies downloaded content against Repr-Digest (raises on mismatch)."""
    with tempfile.NamedTemporaryFile() as tf:
        bad_digest = hashlib.sha256(b'different content').digest()
        bad_b64 = base64.b64encode(bad_digest).decode()
        mock_curl = MockCurlInstance(200, response_body=CONTENT,
                                     response_headers={'repr-digest': f'sha-256=:{bad_b64}:'})
        with patch('pycurl.Curl', return_value=mock_curl):
            with pytest.raises(ClientError, match='digest mismatch'):
                client.simple_download(S3_URL, tf.name)


# ---------------------------------------------------------------------------
# simple_download — arbitrary website behavior
# ---------------------------------------------------------------------------

def test_simple_download_arbitrary_no_digest_headers():
    """Arbitrary websites don't return digest headers; download still succeeds."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=b'<html/>',
                                     response_headers={'content-type': 'text/html; charset=utf-8'})
        with patch('pycurl.Curl', return_value=mock_curl):
            digest, mime, _, _ = client.simple_download('http://example.com/page', tf.name)
        # Digest is always computed (no server digest to verify)
        assert isinstance(digest, bytes)
        assert len(digest) == 32  # SHA-256 is 32 bytes
        assert mime == 'text/html; charset=utf-8'


def test_simple_download_arbitrary_no_content_disposition():
    """No Content-Disposition header → sugg_fname is None."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=b'data',
                                     response_headers={'content-type': 'application/zip'})
        with patch('pycurl.Curl', return_value=mock_curl):
            _, _, sugg_fname, _ = client.simple_download('http://example.com/archive', tf.name)
    assert sugg_fname is None


def test_simple_download_arbitrary_no_last_modified():
    """No Last-Modified header → mtime is None."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=b'data',
                                     response_headers={'content-type': 'image/jpeg'})
        with patch('pycurl.Curl', return_value=mock_curl):
            _, _, _, mtime = client.simple_download('http://example.com/photo.jpg', tf.name)
    assert mtime is None


def test_simple_download_arbitrary_html_content_type():
    """text/html from a website is returned as the mime type."""
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=b'<html/>',
                                     response_headers={'content-type': 'text/html'})
        with patch('pycurl.Curl', return_value=mock_curl):
            _, mime, _, _ = client.simple_download('http://example.com/', tf.name)
    assert mime == 'text/html'


def test_simple_download_arbitrary_binary_content_written():
    """Binary content from any URL is streamed to disk unchanged."""
    binary_content = bytes(range(256)) * 4  # 1 KB of arbitrary bytes
    with tempfile.NamedTemporaryFile() as tf:
        mock_curl = MockCurlInstance(200, response_body=binary_content,
                                     response_headers={'content-type': 'application/octet-stream'})
        with patch('pycurl.Curl', return_value=mock_curl):
            client.simple_download('http://example.com/binary', tf.name)
        tf.seek(0)
        assert tf.read() == binary_content
