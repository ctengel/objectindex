"""Tests for pure/stdlib utility functions in obj_idx/client.py"""

import pathlib
import tempfile

from obj_idx.client import get_mime, is_valid_url

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
