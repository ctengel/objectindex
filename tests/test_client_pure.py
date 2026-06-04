"""Tests for pure/stdlib utility functions in obj_idx/client.py"""

import base64
import datetime
import hashlib
import pathlib
import tempfile

import pytest

from obj_idx.client import (
    checksum,
    encode_digest_header,
    get_mime,
    is_valid_url,
    parse_digest_header,
    read_content_disposition,
    read_http_datetime,
)

# ---------------------------------------------------------------------------
# parse_digest_header
# ---------------------------------------------------------------------------

def test_parse_digest_header_none_input():
    assert parse_digest_header(None) is None


def test_parse_digest_header_empty_string():
    assert parse_digest_header('') is None


def test_parse_digest_header_sha256():
    expected = hashlib.sha256(b'hello').digest()
    b64 = base64.b64encode(expected).decode()
    header = f'sha-256=:{b64}:'
    result = parse_digest_header(header)
    assert result == expected


def test_parse_digest_header_ignores_non_sha256():
    result = parse_digest_header('md5=:abc:')
    assert result is None


def test_parse_digest_header_multi_algo_picks_sha256():
    expected = hashlib.sha256(b'data').digest()
    b64 = base64.b64encode(expected).decode()
    header = f'md5=:irrelevant:,sha-256=:{b64}:'
    result = parse_digest_header(header)
    assert result == expected


# ---------------------------------------------------------------------------
# encode_digest_header
# ---------------------------------------------------------------------------

def test_encode_digest_header_roundtrip():
    raw = hashlib.sha256(b'roundtrip').digest()
    encoded = encode_digest_header(raw)
    decoded = parse_digest_header(encoded)
    assert decoded == raw


def test_encode_digest_header_format():
    result = encode_digest_header(b'\x00' * 32)
    assert result.startswith('sha-256=:')
    assert result.endswith(':')


# ---------------------------------------------------------------------------
# read_content_disposition
# ---------------------------------------------------------------------------

def test_read_content_disposition_none():
    assert read_content_disposition(None) is None


def test_read_content_disposition_no_filename():
    assert read_content_disposition('inline') is None


def test_read_content_disposition_with_quoted_filename():
    result = read_content_disposition('attachment; filename="test.mp4"')
    assert result == 'test.mp4'


def test_read_content_disposition_with_unquoted_filename():
    result = read_content_disposition('attachment; filename=test.mp4')
    assert result == 'test.mp4'


# ---------------------------------------------------------------------------
# read_http_datetime
# ---------------------------------------------------------------------------

def test_read_http_datetime_none():
    assert read_http_datetime(None) is None


def test_read_http_datetime_valid():
    result = read_http_datetime('Wed, 01 Jan 2020 12:00:00 GMT')
    assert isinstance(result, datetime.datetime)
    assert result.year == 2020
    assert result.month == 1
    assert result.day == 1
    assert result.hour == 12


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
# checksum (uses real file I/O with tmpfile)
# ---------------------------------------------------------------------------

def test_checksum_known_value():
    content = b'hello world'
    expected = hashlib.sha256(content).digest()
    with tempfile.NamedTemporaryFile() as f:
        f.write(content)
        f.flush()
        result = checksum(pathlib.Path(f.name))
    assert isinstance(result, bytes)
    assert result == expected


def test_checksum_empty_file():
    expected = hashlib.sha256(b'').digest()
    with tempfile.NamedTemporaryFile() as f:
        result = checksum(pathlib.Path(f.name))
    assert result == expected


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
