"""Tests for obj_idx/clilib.py"""

import uuid
from unittest.mock import Mock, patch
import pytest
import requests

from obj_idx.clilib import ObjectIndex, File

BASE_URL = 'http://api.test/'
OBJ_UUID = 'aaaaaaaa-0000-0000-0000-000000000001'
FILE_UUID = 'bbbbbbbb-0000-0000-0000-000000000002'


def _mock_response(body, status_code=200):
    m = Mock()
    m.json.return_value = body
    m.status_code = status_code
    return m


def _make_file_dict(file_uuid=FILE_UUID, obj_uuid=OBJ_UUID):
    return {
        'uuid': file_uuid,
        'url': 'file://host/a.txt',
        'direct': True,
        'partial': False,
        'file_object': {
            'uuid': obj_uuid,
            'checksum': 'aa' * 32,
            'bucket': 'bucket1',
            'key': 'aa' * 32 + '-a.txt',
            'completed': True,
            'deleted': False,
            'obj_size': 4,
        },
    }


def _make_upload_response(exists=False):
    """Build a POST /upload/ response body."""
    if exists:
        return {
            'exists': True,
            'download': 'http://s3.test/bucket1/existing-key',
            'file': _make_file_dict(),
        }
    return {
        'exists': False,
        'upload': {
            's3': 'http://s3.test/bucket1/upload-key',
            'finished': f'/object/{OBJ_UUID}/',
        },
        'file': _make_file_dict(),
    }


# ---------------------------------------------------------------------------
# ObjectIndex HTTP methods
# ---------------------------------------------------------------------------

def test_get_calls_requests_get():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response({'key': 'val'})
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.get.return_value = resp
        result = oi.get('object/123/')
    mock_req.get.assert_called_once_with(
        'http://api.test/object/123/', params=None, timeout=15
    )
    resp.raise_for_status.assert_called_once()
    assert result == {'key': 'val'}


def test_get_with_params():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response([])
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.get.return_value = resp
        oi.get('file/', params={'url': 'http://ex.com/'})
    mock_req.get.assert_called_once_with(
        'http://api.test/file/', params={'url': 'http://ex.com/'}, timeout=15
    )


def test_post_calls_requests_post():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response({'id': 1})
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.post.return_value = resp
        result = oi.post('upload/', {'a': 1})
    mock_req.post.assert_called_once_with(
        'http://api.test/upload/', json={'a': 1}, timeout=15
    )
    resp.raise_for_status.assert_called_once()
    assert result == {'id': 1}


def test_put_calls_requests_put():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response({'completed': True})
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.put.return_value = resp
        result = oi.put(f'object/{OBJ_UUID}/', {'completed': True})
    mock_req.put.assert_called_once_with(
        f'http://api.test/object/{OBJ_UUID}/', json={'completed': True}, timeout=15
    )
    assert result == {'completed': True}


def test_http_error_propagates():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response({}, status_code=404)
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError('404')
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.get.return_value = resp
        with pytest.raises(requests.exceptions.HTTPError):
            oi.get('object/missing/')


def test_list_objects_by_bucket():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response([])
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.get.return_value = resp
        oi.list_objects('bucket1')
    mock_req.get.assert_called_once_with(
        'http://api.test/buckets/bucket1/', params=None, timeout=15
    )


def test_put_object_puts_deleted():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response({'uuid': OBJ_UUID, 'deleted': True})
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.put.return_value = resp
        result = oi.put_object(OBJ_UUID, {'deleted': True})
    mock_req.put.assert_called_once_with(
        f'http://api.test/object/{OBJ_UUID}/', json={'deleted': True}, timeout=15
    )
    assert result == {'uuid': OBJ_UUID, 'deleted': True}


def test_search_files_returns_file_objects():
    oi = ObjectIndex(BASE_URL)
    file_dicts = [_make_file_dict('file-1', 'obj-1'), _make_file_dict('file-2', 'obj-2')]
    resp = _mock_response(file_dicts)
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.get.return_value = resp
        files = oi.search_files({'url': 'file://host/*'})
    assert len(files) == 2
    assert all(isinstance(f, File) for f in files)
    assert files[0].info['uuid'] == 'file-1'
    assert files[1].info['uuid'] == 'file-2'
    assert files[0].object is not None


def test_get_file_with_info():
    oi = ObjectIndex(BASE_URL)
    fd = _make_file_dict()
    resp = _mock_response(fd)
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.get.return_value = resp
        f = oi.get_file(FILE_UUID)
    assert isinstance(f, File)
    assert f.info['uuid'] == FILE_UUID
    assert f.object is not None


def test_search_object():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response([{'checksum': 'aa' * 32}])
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.get.return_value = resp
        result = oi.search_object('aa' * 32)
    mock_req.get.assert_called_once_with(
        'http://api.test/object/', params={'checksum': 'aa' * 32}, timeout=15
    )
    assert result == [{'checksum': 'aa' * 32}]


def test_get_presigned():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response({'presigned': 'http://s3.test/bucket1/key'})
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.get.return_value = resp
        url = oi.get_presigned(OBJ_UUID)
    called_url = mock_req.get.call_args[0][0]
    assert called_url.endswith('/download')
    assert OBJ_UUID in called_url
    assert url == 'http://s3.test/bucket1/key'


# ---------------------------------------------------------------------------
# initiate_upload
# ---------------------------------------------------------------------------

def test_initiate_upload_new_file():
    oi = ObjectIndex(BASE_URL)
    checksum_bytes = bytes(range(32))
    resp = _mock_response(_make_upload_response(exists=False))
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.post.return_value = resp
        f = oi.initiate_upload(
            url='file://host/a.txt',
            bucket='bucket1',
            obj_size=4,
            checksum=checksum_bytes,
            filename='a.txt',
        )
    payload = mock_req.post.call_args[1]['json']
    assert payload['checksum'] == checksum_bytes.hex()
    assert payload['url'] == 'file://host/a.txt'
    assert payload['bucket'] == 'bucket1'
    assert payload['obj_size'] == 4
    assert f.exists() is False
    assert f.s3_url == 'http://s3.test/bucket1/upload-key'
    assert f.object_url == f'/object/{OBJ_UUID}/'


def test_initiate_upload_existing_file():
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response(_make_upload_response(exists=True))
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.post.return_value = resp
        f = oi.initiate_upload(
            url='file://host/a.txt',
            bucket='bucket1',
            obj_size=4,
            checksum=bytes(32),
            filename='a.txt',
        )
    assert f.exists() is True
    assert f.s3_url == 'http://s3.test/bucket1/existing-key'
    assert f.object_url is None


def test_initiate_upload_optional_fields():
    oi = ObjectIndex(BASE_URL, user='alice', sw='mysw', host='myhost')
    resp = _mock_response(_make_upload_response())
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.post.return_value = resp
        oi.initiate_upload(
            url='file://host/a.txt',
            bucket='bucket1',
            obj_size=4,
            checksum=bytes(32),
            filename='a.txt',
            mime='video/mp4',
            extra_file={'tag': 'x'},
            extra_object={'note': 'y'},
        )
    payload = mock_req.post.call_args[1]['json']
    assert payload['ul_user'] == 'alice'
    assert payload['ul_sw'] == 'mysw'
    assert payload['ul_host'] == 'myhost'
    assert payload['mime'] == 'video/mp4'
    assert payload['extra_file'] == {'tag': 'x'}
    assert payload['extra_object'] == {'note': 'y'}


def test_initiate_upload_no_optional_fields_absent():
    """When user/sw/host/mime/extra not provided, they must not appear in payload."""
    oi = ObjectIndex(BASE_URL)
    resp = _mock_response(_make_upload_response())
    with patch('obj_idx.clilib.requests') as mock_req:
        mock_req.post.return_value = resp
        oi.initiate_upload(
            url='file://host/a.txt',
            bucket='bucket1',
            obj_size=4,
            checksum=bytes(32),
            filename='a.txt',
        )
    payload = mock_req.post.call_args[1]['json']
    for absent in ('ul_user', 'ul_sw', 'ul_host', 'mime', 'extra_file', 'extra_object'):
        assert absent not in payload


# ---------------------------------------------------------------------------
# File state machine
# ---------------------------------------------------------------------------

def _make_file(object_url=None):
    oi = Mock()
    f = File(oi, uuid.UUID(FILE_UUID))
    if object_url:
        f.object_url = object_url
    return f


def test_file_set_info_copies_object():
    f = _make_file()
    original = _make_file_dict()
    f.set_info(original)
    original['url'] = 'mutated'
    assert f.info['url'] == 'file://host/a.txt'
    assert f.object is not None
    assert f.object['uuid'] == OBJ_UUID


def test_file_set_info_without_object():
    f = _make_file()
    f.set_info({'uuid': FILE_UUID, 'url': 'file://host/a.txt'})
    assert f.object is None


def test_file_exists_raises_before_set():
    f = _make_file()
    with pytest.raises(AssertionError):
        f.exists()


def test_file_exists_after_set_upload_true():
    f = _make_file()
    f.set_upload(exists=True, s3_url='http://s3/key')
    assert f.exists() is True


def test_file_exists_after_set_upload_false():
    f = _make_file()
    f.set_upload(exists=False, s3_url='http://s3/upload', object_url='/object/x/')
    assert f.exists() is False


def test_file_get_object_url_from_set_upload():
    f = _make_file(object_url='/object/the-uuid/')
    assert f.get_object_url() == '/object/the-uuid/'


def test_file_get_object_url_fallback_from_info():
    f = _make_file()
    f.set_info(_make_file_dict())
    url = f.get_object_url()
    assert url == f'/object/{OBJ_UUID}/'


def test_file_finish_upload():
    f = _make_file(object_url=f'/object/{OBJ_UUID}/')
    f.oio.put.return_value = {'completed': True}
    f.finish_upload()
    f.oio.put.assert_called_once_with(f'/object/{OBJ_UUID}/', json={'completed': True})
    assert f.object == {'completed': True}
