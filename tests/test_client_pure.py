"""Tests for pure/stdlib utility functions in obj_idx/client.py"""

import pathlib
import tempfile
import warnings

from obj_idx.client import get_mime
from obj_idx.common import is_valid_url, reconcile_mime_ext

# ---------------------------------------------------------------------------
# is_valid_url
# ---------------------------------------------------------------------------

def test_is_valid_url_http():
    assert is_valid_url('http://example.com/path') is True


def test_is_valid_url_https():
    assert is_valid_url('https://example.com/') is True


def test_is_valid_url_not_url():
    assert is_valid_url('not-a-url') is False


def test_is_valid_url_no_netloc():
    # file:///local has no netloc (empty string), so is considered invalid
    assert is_valid_url('file:///local') is False


def test_is_valid_url_file_with_host():
    assert is_valid_url('file://myhost/path') is True


# ---------------------------------------------------------------------------
# get_mime (uses real file path — only extension matters)
# ---------------------------------------------------------------------------

def test_get_mime_text_plain():
    with tempfile.NamedTemporaryFile(suffix='.txt') as f:
        result = get_mime(pathlib.Path(f.name))
    assert result == 'text/plain'


def test_get_mime_unknown_extension():
    with tempfile.NamedTemporaryFile(suffix='.xyzunknown') as f:
        result = get_mime(pathlib.Path(f.name))
    assert result is None


# ---------------------------------------------------------------------------
# reconcile_mime_ext (filename + sniffed MIME -> stored key + MIME)
# ---------------------------------------------------------------------------

def test_reconcile_octet_stream_trusts_extension():
    # libmagic returns the catch-all octet-stream for some valid ISO-Media brands; a concrete
    # extension MIME wins, with no .bin suffix and no warning.
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        result = reconcile_mime_ext('video.mp4', 'application/octet-stream')
    assert result == ('video.mp4', 'video/mp4')


def test_reconcile_octet_stream_unknown_extension_keeps_bin():
    # Genuinely unidentifiable content (no usable extension) still gets .bin + octet-stream.
    assert reconcile_mime_ext('blob', 'application/octet-stream') == (
        'blob.bin', 'application/octet-stream')


def test_reconcile_real_mismatch_still_warns():
    # A concrete MIME that truly disagrees with the extension still warns and appends.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        result = reconcile_mime_ext('video.txt', 'video/mp4')
    assert result[1] == 'video/mp4'
    assert result[0].startswith('video.txt')
    assert result[0] != 'video.txt'
    assert any('does' in str(w.message) for w in caught)


def test_reconcile_matching_unchanged():
    assert reconcile_mime_ext('video.mp4', 'video/mp4') == ('video.mp4', 'video/mp4')
