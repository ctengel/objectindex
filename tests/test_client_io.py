"""Tests for I/O and higher-level functions in obj_idx/client.py"""

import datetime
import hashlib
import socket
import tempfile
from unittest.mock import Mock, patch

import pytest
import requests

from obj_idx import client
from obj_idx.clilib import File, ObjectIndex
from simpler_objects.client import ClientError

OBJ_UUID = 'aaaaaaaa-0000-0000-0000-000000000001'
FILE_UUID = 'bbbbbbbb-0000-0000-0000-000000000002'
CONTENT = b'test content for client io'
CKSUM_HEX = hashlib.sha256(CONTENT).hexdigest()
CKSUM_BYTES = hashlib.sha256(CONTENT).digest()


def _make_object_dict(completed=True, deleted=False, cksum_hex=CKSUM_HEX):
    return {
        'uuid': OBJ_UUID,
        'checksum': cksum_hex,
        'bucket': 'bucket1',
        'key': f'{cksum_hex}-a.txt',
        'obj_size': len(CONTENT),
        'mime': 'application/octet-stream',
        'completed': completed,
        'deleted': deleted,
        'files': [{'uuid': FILE_UUID, 'url': 'file://host/a.txt'}],
    }


def _make_mock_file(completed=True, deleted=False, direct=True):
    f = Mock(spec=File)
    f.object = _make_object_dict(completed=completed, deleted=deleted)
    f.info = {'url': 'file://host/a.txt', 'direct': direct}
    f.uuid = FILE_UUID
    return f


def _mock_obj_idx():
    return Mock(spec=ObjectIndex)


# ---------------------------------------------------------------------------
# find_files — local path
# ---------------------------------------------------------------------------

def test_find_files_local_not_found():
    with tempfile.NamedTemporaryFile() as f:
        f.write(CONTENT)
        f.flush()
        mock_oi = _mock_obj_idx()
        mock_oi.search_object.return_value = []
        result = client.find_files(f.name, mock_oi)
    assert result == []


def test_find_files_local_found():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx()
        obj_dict = _make_object_dict()
        mock_oi.search_object.return_value = [obj_dict]
        mock_file = _make_mock_file()
        mock_oi.file_obj_from_dict.return_value = mock_file
        result = client.find_files(tf.name, mock_oi)
    assert len(result) == 1


def test_find_files_local_deleted_excluded():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx()
        mock_oi.search_object.return_value = [_make_object_dict(deleted=True)]
        result = client.find_files(tf.name, mock_oi)
    assert result == []


def test_find_files_local_not_completed_excluded():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx()
        mock_oi.search_object.return_value = [_make_object_dict(completed=False)]
        result = client.find_files(tf.name, mock_oi)
    assert result == []


# ---------------------------------------------------------------------------
# find_files — URL
# ---------------------------------------------------------------------------

def test_find_files_url_returns_completed_direct():
    mock_oi = _mock_obj_idx()
    good = _make_mock_file(completed=True, deleted=False, direct=True)
    bad_incomplete = _make_mock_file(completed=False)
    bad_deleted = _make_mock_file(completed=True, deleted=True)
    mock_oi.search_files.return_value = [good, bad_incomplete, bad_deleted]
    result = client.find_files('http://example.com/v.mp4', mock_oi, is_url=True)
    assert result == [good]


def test_find_files_url_must_direct_false_includes_indirect():
    mock_oi = _mock_obj_idx()
    indirect = _make_mock_file(completed=True, deleted=False, direct=False)
    mock_oi.search_files.return_value = [indirect]
    result = client.find_files('http://example.com/v.mp4', mock_oi, is_url=True, must_direct=False)
    assert result == [indirect]


def test_find_files_url_must_direct_true_excludes_indirect():
    mock_oi = _mock_obj_idx()
    indirect = _make_mock_file(completed=True, deleted=False, direct=False)
    mock_oi.search_files.return_value = [indirect]
    result = client.find_files('http://example.com/v.mp4', mock_oi, is_url=True, must_direct=True)
    assert result == []


# ---------------------------------------------------------------------------
# upload_core
# ---------------------------------------------------------------------------

def _make_mock_initiate_file(exists=False):
    f = Mock(spec=File)
    f.exists.return_value = exists
    f.s3_url = 'http://s3.test/bucket1/upload-key'
    f.object_url = f'/object/{OBJ_UUID}/'
    f.get_s3_url.return_value = 'http://s3.test/bucket1/upload-key'
    return f


def test_upload_core_new_file():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        fname = tf.name
        mock_oi = _mock_obj_idx()
        mock_file = _make_mock_initiate_file(exists=False)
        mock_oi.initiate_upload.return_value = mock_file
        mtime = datetime.datetime(2021, 1, 1)
        with patch('obj_idx.client.simple_upload') as mock_upload:
            result = client.upload_core(fname, mock_oi, 'bucket1',
                                        'file://host/a.txt', mtime)
    mock_oi.initiate_upload.assert_called_once()
    mock_upload.assert_called_once()
    mock_file.finish_upload.assert_called_once()
    assert result is mock_file


def test_upload_core_rejects_invalid_url():
    # A bad url is caught before any network/API call (initiate_upload never runs).
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx()
        with pytest.raises(ValueError):
            client.upload_core(tf.name, mock_oi, 'bucket1',
                               'not-a-url', datetime.datetime(2021, 1, 1))
    mock_oi.initiate_upload.assert_not_called()


def test_upload_core_existing_file_skips_upload():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx()
        mock_file = _make_mock_initiate_file(exists=True)
        mock_oi.initiate_upload.return_value = mock_file
        with patch('obj_idx.client.simple_upload') as mock_upload:
            result = client.upload_core(tf.name, mock_oi, 'bucket1',
                                        'file://host/a.txt',
                                        datetime.datetime(2021, 1, 1))
    mock_upload.assert_not_called()
    mock_file.finish_upload.assert_not_called()
    assert result is mock_file


def test_upload_core_409_returns_none_with_warning():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx()
        err_resp = Mock()
        err_resp.status_code = 409
        err_resp.json.return_value = {'object_uuid': OBJ_UUID}
        http_err = requests.exceptions.HTTPError(response=err_resp)
        mock_oi.initiate_upload.side_effect = http_err
        with pytest.warns(UserWarning):
            result = client.upload_core(tf.name, mock_oi, 'bucket1',
                                        'file://host/a.txt',
                                        datetime.datetime(2021, 1, 1))
    assert result is None


def test_upload_core_non_409_reraises():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx()
        err_resp = Mock()
        err_resp.status_code = 500
        http_err = requests.exceptions.HTTPError(response=err_resp)
        mock_oi.initiate_upload.side_effect = http_err
        with pytest.raises(requests.exceptions.HTTPError):
            client.upload_core(tf.name, mock_oi, 'bucket1',
                               'file://host/a.txt',
                               datetime.datetime(2021, 1, 1))


# ---------------------------------------------------------------------------
# upload_local
# ---------------------------------------------------------------------------

def test_upload_local_constructs_file_url():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx()
        with patch('obj_idx.client.upload_core') as mock_core:
            mock_core.return_value = Mock()
            client.upload_local(tf.name, mock_oi, 'bucket1')
    called_url = mock_core.call_args[0][3]
    assert called_url.startswith('file://')
    assert socket.gethostname() in called_url


def test_upload_local_uses_provided_url():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx()
        with patch('obj_idx.client.upload_core') as mock_core:
            mock_core.return_value = Mock()
            client.upload_local(tf.name, mock_oi, 'bucket1', url='file://host/custom.txt')
    called_url = mock_core.call_args[0][3]
    assert called_url == 'file://host/custom.txt'


# ---------------------------------------------------------------------------
# upload_remote
# ---------------------------------------------------------------------------

def test_upload_remote_existing_returns_early():
    mock_oi = _mock_obj_idx()
    existing = _make_mock_file()
    with patch('obj_idx.client.find_files', return_value=[existing]):
        with pytest.warns(UserWarning):
            result = client.upload_remote('http://example.com/v.mp4', mock_oi, 'bucket1',
                                          check_exists=True)
    assert result is existing


def test_upload_remote_downloads_and_uploads():
    mock_oi = _mock_obj_idx()
    mock_file = Mock()
    mtime = datetime.datetime(2022, 6, 1)
    with patch('obj_idx.client.find_files', return_value=[]):
        with patch('obj_idx.client.simple_download',
                   return_value=(None, 'video/mp4', 'video.mp4', mtime)) as mock_dl:
            with patch('obj_idx.client.upload_core', return_value=mock_file) as mock_core:
                result = client.upload_remote('http://example.com/v.mp4', mock_oi,
                                              'bucket1', check_exists=True)
    mock_dl.assert_called_once()
    mock_core.assert_called_once()
    assert result is mock_file


def test_upload_remote_keyhint_from_content_disposition():
    """When the download response carries a Content-Disposition filename and no
    explicit key_hint is given, that filename is forwarded to upload_core."""
    mock_oi = _mock_obj_idx()
    mock_file = Mock()
    mtime = datetime.datetime(2022, 6, 1)
    with patch('obj_idx.client.find_files', return_value=[]):
        with patch('obj_idx.client.simple_download',
                   return_value=(None, 'video/mp4', 'server-name.mp4', mtime)):
            with patch('obj_idx.client.upload_core', return_value=mock_file) as mock_core:
                client.upload_remote('http://example.com/dl', mock_oi, 'bucket1',
                                     check_exists=False)
    _, kwargs = mock_core.call_args
    assert kwargs.get('key_hint') == 'server-name.mp4'


def test_upload_remote_explicit_keyhint_overrides_server():
    """A caller-supplied key_hint takes precedence over Content-Disposition."""
    mock_oi = _mock_obj_idx()
    mock_file = Mock()
    mtime = datetime.datetime(2022, 6, 1)
    with patch('obj_idx.client.find_files', return_value=[]):
        with patch('obj_idx.client.simple_download',
                   return_value=(None, 'video/mp4', 'server-name.mp4', mtime)):
            with patch('obj_idx.client.upload_core', return_value=mock_file) as mock_core:
                client.upload_remote('http://example.com/dl', mock_oi, 'bucket1',
                                     check_exists=False, key_hint='my-name.mp4')
    _, kwargs = mock_core.call_args
    assert kwargs.get('key_hint') == 'my-name.mp4'


def test_upload_remote_no_mtime_falls_back_to_now():
    """When the server returns no Last-Modified and caller passes no mtime,
    upload_remote falls back to datetime.now() so upload_core always gets a mtime."""
    mock_oi = _mock_obj_idx()
    mock_file = Mock()
    with patch('obj_idx.client.find_files', return_value=[]):
        with patch('obj_idx.client.simple_download',
                   return_value=(None, 'text/plain', None, None)):
            with patch('obj_idx.client.upload_core', return_value=mock_file) as mock_core:
                client.upload_remote('http://example.com/doc', mock_oi, 'bucket1',
                                     check_exists=False)
    _, kwargs = mock_core.call_args
    assert isinstance(kwargs.get('mtime'), datetime.datetime)


def test_upload_remote_catch_dl_err_returns_none():
    mock_oi = _mock_obj_idx()
    dl_err = ClientError('download failed', status=404)
    with patch('obj_idx.client.find_files', return_value=[]):
        with patch('obj_idx.client.simple_download', side_effect=dl_err):
            with pytest.warns(UserWarning):
                result = client.upload_remote('http://example.com/v.mp4', mock_oi,
                                              'bucket1', check_exists=False,
                                              catch_dl_err=True)
    assert result is None


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

def test_download_pretend_returns_files_no_io():
    mock_oi = _mock_obj_idx()
    mock_files = [_make_mock_file(), _make_mock_file()]
    mock_oi.search_files.return_value = mock_files
    with patch('obj_idx.client.simple_download') as mock_dl:
        result = client.download(mock_oi, 'http://example.com/v.mp4', pretend=True)
    mock_dl.assert_not_called()
    assert result == mock_files


@pytest.mark.parametrize('dl_digest', [CKSUM_BYTES, None],
                         ids=['digest-present', 'digest-none'])
def test_download_verifies_checksum(dl_digest):
    """download() works whether simple_download returns a digest (streaming-hash
    impl, or header-only impl when the server reported one) or None (header-only
    impl with no server digest). When present it's compared as hex; either way
    the file is re-hashed from disk via checksum() and compared to the expected."""
    mock_oi = _mock_obj_idx()
    mock_file = _make_mock_file()
    mock_file.object = _make_object_dict()  # checksum is hex string
    mock_file.get_s3_url.return_value = 'http://s3.test/bucket1/key.mp4'
    mock_oi.search_files.return_value = [mock_file]

    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tf:
        tf.write(CONTENT)
        tf.flush()

    with patch('obj_idx.client.simple_download',
               return_value=(dl_digest, 'video/mp4', 'key.mp4', None)):
        with patch('obj_idx.client.checksum', return_value=CKSUM_BYTES):
            # digest-present: dl_cksum.hex() == file.object['checksum']
            # digest-none: the `if dl_cksum:` guard is skipped; disk re-hash verifies
            client.download(mock_oi, 'http://example.com/v.mp4')


# ---------------------------------------------------------------------------
# api_key / ca_bundle threading to simpler_objects
# ---------------------------------------------------------------------------

def _mock_obj_idx_with_creds():
    mock_oi = _mock_obj_idx()
    mock_oi.api_key = 'sekrit'
    mock_oi.ca_bundle = '/ca.pem'
    return mock_oi


def test_upload_core_passes_credentials_to_simple_upload():
    with tempfile.NamedTemporaryFile() as tf:
        tf.write(CONTENT)
        tf.flush()
        mock_oi = _mock_obj_idx_with_creds()
        mock_oi.initiate_upload.return_value = _make_mock_initiate_file(exists=False)
        with patch('obj_idx.client.simple_upload') as mock_upload:
            client.upload_core(tf.name, mock_oi, 'bucket1',
                               'file://host/a.txt', datetime.datetime(2021, 1, 1))
    assert mock_upload.call_args.kwargs['api_key'] == 'sekrit'
    assert mock_upload.call_args.kwargs['ca_bundle'] == '/ca.pem'


def test_download_passes_credentials_to_simple_download():
    mock_oi = _mock_obj_idx_with_creds()
    mock_file = _make_mock_file()
    mock_file.get_s3_url.return_value = 'http://s3.test/bucket1/key.mp4'
    mock_oi.search_files.return_value = [mock_file]
    with patch('obj_idx.client.simple_download',
               return_value=(None, 'video/mp4', 'key.mp4', None)) as mock_dl:
        with patch('obj_idx.client.checksum', return_value=CKSUM_BYTES):
            client.download(mock_oi, 'http://example.com/v.mp4')
    assert mock_dl.call_args.kwargs['api_key'] == 'sekrit'
    assert mock_dl.call_args.kwargs['ca_bundle'] == '/ca.pem'


def test_upload_remote_source_download_has_no_credentials():
    # The source URL is an arbitrary third-party host: the shared OI/SO key
    # must never ride along, nor the private CA bundle.
    mock_oi = _mock_obj_idx_with_creds()
    with patch('obj_idx.client.find_files', return_value=[]):
        with patch('obj_idx.client.simple_download',
                   return_value=(None, 'video/mp4', 'v.mp4',
                                 datetime.datetime(2022, 6, 1))) as mock_dl:
            with patch('obj_idx.client.upload_core', return_value=Mock()):
                client.upload_remote('http://example.com/v.mp4', mock_oi,
                                     'bucket1', check_exists=False)
    assert 'api_key' not in mock_dl.call_args.kwargs
    assert 'ca_bundle' not in mock_dl.call_args.kwargs


def test_head_locator_sends_bearer_and_verify():
    with patch('obj_idx.clilib.requests') as mock_req:
        client.head_locator('http://s3.test/', 'bucket1', 'key.txt',
                            api_key='sekrit', ca_bundle='/ca.pem')
    kwargs = mock_req.head.call_args.kwargs
    assert kwargs['headers'] == {'Authorization': 'Bearer sekrit'}
    assert kwargs['verify'] == '/ca.pem'
    assert kwargs['allow_redirects'] is True


def test_head_locator_no_credentials_no_extra_kwargs():
    with patch('obj_idx.clilib.requests') as mock_req:
        client.head_locator('http://s3.test/', 'bucket1', 'key.txt')
    kwargs = mock_req.head.call_args.kwargs
    assert 'headers' not in kwargs
    assert 'verify' not in kwargs
