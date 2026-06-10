"""Tests for obj_idx/cli.py and obj_idx/dlp_lpm_meta.py"""

import argparse
import datetime
import pathlib
import tempfile
from unittest.mock import Mock, patch

import pytest

from obj_idx import cli
from obj_idx.clilib import File
from obj_idx.dlp_lpm_meta import DLPMetaData, NoMediaFile, lpm2dict

FILE_UUID = 'bbbbbbbb-0000-0000-0000-000000000002'
OBJ_UUID = 'aaaaaaaa-0000-0000-0000-000000000001'


def _mock_oi():
    return Mock()


def _mock_file(uuid_val=FILE_UUID):
    f = Mock(spec=File)
    f.uuid = uuid_val
    f.info = {'url': 'file://host/a.txt'}
    f.object = {
        'uuid': OBJ_UUID,
        'mime': 'text/plain',
        'bucket': 'bucket1',
        'key': 'hash-a.txt',
    }
    f.get_s3_url.return_value = 'http://s3.test/bucket1/hash-a.txt'
    return f


# ---------------------------------------------------------------------------
# cli._upload
# ---------------------------------------------------------------------------

def test_cli_upload_local_calls_upload_local(capsys):
    mock_oi = _mock_oi()
    mock_file = _mock_file()
    args = argparse.Namespace(filename=['a.txt'], bucket='bucket1', tag=[], url=False)
    with patch('obj_idx.cli.client.upload_local', return_value=mock_file) as mock_ul:
        cli._upload(mock_oi, args)
    mock_ul.assert_called_once_with('a.txt', mock_oi, 'bucket1', extra={})
    out = capsys.readouterr().out
    assert FILE_UUID in out


def test_cli_upload_url_calls_upload_remote(capsys):
    mock_oi = _mock_oi()
    mock_file = _mock_file()
    args = argparse.Namespace(filename=['http://example.com/v.mp4'],
                              bucket='bucket1', tag=[], url=True)
    with patch('obj_idx.cli.client.upload_remote', return_value=mock_file) as mock_ur:
        cli._upload(mock_oi, args)
    mock_ur.assert_called_once_with('http://example.com/v.mp4', mock_oi, 'bucket1', extra={})


def test_cli_upload_none_result_warns(capsys):
    mock_oi = _mock_oi()
    args = argparse.Namespace(filename=['bad.txt'], bucket='bucket1', tag=[], url=False)
    with patch('obj_idx.cli.client.upload_local', return_value=None):
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            cli._upload(mock_oi, args)
    assert any('bad.txt' in str(w.message) for w in caught)


def test_cli_upload_tags_parsed(capsys):
    mock_oi = _mock_oi()
    mock_file = _mock_file()
    args = argparse.Namespace(filename=['a.txt'], bucket='bucket1',
                              tag=['key=val', 'foo=bar'], url=False)
    with patch('obj_idx.cli.client.upload_local', return_value=mock_file) as mock_ul:
        cli._upload(mock_oi, args)
    _, _, kwargs = mock_ul.mock_calls[0]
    assert kwargs['extra'] == {'key': 'val', 'foo': 'bar'}


# ---------------------------------------------------------------------------
# cli._check
# ---------------------------------------------------------------------------

def test_cli_check_not_found_prints_message(capsys):
    mock_oi = _mock_oi()
    args = argparse.Namespace(filename=['nofile.txt'], rm=False)
    with patch('obj_idx.cli.client.find_files', return_value=[]):
        cli._check(mock_oi, args)
    out = capsys.readouterr().out
    assert 'not found' in out


def test_cli_check_found_prints_object_info(capsys):
    mock_oi = _mock_oi()
    mock_file = _mock_file()
    args = argparse.Namespace(filename=['a.txt'], rm=False)
    with patch('obj_idx.cli.client.find_files', return_value=[mock_file]):
        cli._check(mock_oi, args)
    out = capsys.readouterr().out
    assert OBJ_UUID in out
    assert 'bucket1' in out


def test_cli_check_rm_unlinks_file():
    mock_oi = _mock_oi()
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        fname = tf.name
    mock_file = _mock_file()
    args = argparse.Namespace(filename=[fname], rm=True)
    with patch('obj_idx.cli.client.find_files', return_value=[mock_file]):
        cli._check(mock_oi, args)
    assert not pathlib.Path(fname).exists()


# ---------------------------------------------------------------------------
# cli.get_s3_base / cli._scrub
# ---------------------------------------------------------------------------

def _scrub_result(category, is_error, key='key.txt', detail='', clearable=False):
    r = Mock()
    r.category = category
    r.is_error = is_error
    r.detail = detail
    r.clearable = clearable
    r.cleared = False
    r.brief = {'uuid': OBJ_UUID, 'key': key}
    return r


def test_get_s3_base_from_arg_adds_slash():
    assert cli.get_s3_base('http://s3.test') == 'http://s3.test/'


def test_get_s3_base_from_env(monkeypatch):
    monkeypatch.setenv('OBJIDX_S3', 'http://env.test/')
    assert cli.get_s3_base(None) == 'http://env.test/'


def test_get_s3_base_missing_raises(monkeypatch):
    monkeypatch.delenv('OBJIDX_S3', raising=False)
    with pytest.raises(SystemExit):
        cli.get_s3_base(None)


def test_scrub_error_returns_one_and_prints(capsys):
    cat = cli.client.ScrubCategory.FAILED_OR_NEVER_STARTED
    args = argparse.Namespace(bucket=['bucket1'], all=False, clear=False, s3='http://s3.test/')
    with patch('obj_idx.cli.client.scrub_bucket',
               return_value=[_scrub_result(cat, is_error=True)]):
        rc = cli._scrub(_mock_oi(), args)
    assert rc == 1
    out = capsys.readouterr().out
    assert cat.value in out
    assert 'ERROR' in out


def test_scrub_unknown_bucket_404_is_fatal():
    import requests
    err = requests.exceptions.HTTPError()
    err.response = Mock(status_code=404)
    args = argparse.Namespace(bucket=['nope'], all=False, clear=False, s3='http://s3.test/')
    with patch('obj_idx.cli.client.scrub_bucket', side_effect=err):
        with pytest.raises(SystemExit) as excinfo:
            cli._scrub(_mock_oi(), args)
    assert 'unknown bucket' in str(excinfo.value)


def test_scrub_clear_clears_and_prints_cleared(capsys):
    cat = cli.client.ScrubCategory.FAILED_OR_NEVER_STARTED
    result = _scrub_result(cat, is_error=True, clearable=True)
    args = argparse.Namespace(bucket=['bucket1'], all=False, clear=True,
                              s3='http://s3.test/')
    oi = _mock_oi()
    with patch('obj_idx.cli.client.scrub_bucket', return_value=[result]), \
         patch('obj_idx.cli.client.clear_failed_upload') as mock_clear:
        rc = cli._scrub(oi, args)
    mock_clear.assert_called_once_with(oi, result.brief)
    assert result.cleared is True
    out = capsys.readouterr().out
    assert 'CLEARED' in out
    # re-upload still needed, so the run is nonzero
    assert rc == 1


def test_scrub_clear_skips_in_progress(capsys):
    cat = cli.client.ScrubCategory.UPLOAD_IN_PROGRESS
    result = _scrub_result(cat, is_error=True, clearable=False)
    args = argparse.Namespace(bucket=['bucket1'], all=False, clear=True,
                              s3='http://s3.test/')
    with patch('obj_idx.cli.client.scrub_bucket', return_value=[result]), \
         patch('obj_idx.cli.client.clear_failed_upload') as mock_clear:
        rc = cli._scrub(_mock_oi(), args)
    mock_clear.assert_not_called()
    assert rc == 1
    out = capsys.readouterr().out
    assert 'ERROR' in out


# ---------------------------------------------------------------------------
# lpm2dict
# ---------------------------------------------------------------------------

def test_lpm2dict_full():
    result = lpm2dict('mylib', 'person', 'media')
    assert result == {
        'lpm-lib': 'MYLIB',
        'lpm-per': 'MYLIBperson',
        'lpm-med': 'MYLIBmedia',
    }


def test_lpm2dict_no_library():
    assert lpm2dict(None, None, None) == {}


def test_lpm2dict_library_uppercased():
    result = lpm2dict('lower', 'p', 'm')
    assert result['lpm-lib'] == 'LOWER'


# ---------------------------------------------------------------------------
# DLPMetaData
# ---------------------------------------------------------------------------

MINIMAL_DATA = {
    'webpage_url': 'https://www.youtube.com/watch?v=abc123',
    'extractor_key': 'Youtube',
    'id': 'abc123',
    'uploader': 'SomeChannel',
    'timestamp': 1700000000,
    'ext': 'mp4',
}


def test_dlpmetadata_from_dict():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    assert meta.data['id'] == 'abc123'
    assert meta.partial is False


def test_dlpmetadata_from_dict_isolates_copy():
    d = MINIMAL_DATA.copy()
    meta = DLPMetaData(from_dict=d)
    d['id'] = 'mutated'
    assert meta.data['id'] == 'abc123'


def test_dlpmetadata_get_url_from_webpage_url():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    assert meta.get_url() == 'https://www.youtube.com/watch?v=abc123'


def test_dlpmetadata_get_url_fallback():
    data = {**MINIMAL_DATA, 'webpage_url': None, 'url': 'https://fallback.example/v'}
    meta = DLPMetaData(from_dict=data)
    assert meta.get_url() == 'https://fallback.example/v'


def test_dlpmetadata_get_mtime():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    mtime = meta.get_mtime()
    assert isinstance(mtime, datetime.datetime)


def test_dlpmetadata_get_mtime_no_timestamp():
    data = {k: v for k, v in MINIMAL_DATA.items() if k != 'timestamp'}
    meta = DLPMetaData(from_dict=data)
    assert meta.get_mtime() is None


def test_dlpmetadata_export_extra_keys():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    meta.add_lpm('VID')
    extra = meta.export_extra()
    assert 'ytdl-info' in extra
    assert extra['ytdl-extractor'] == 'youtube'
    assert extra['ytdl-id'] == 'youtube abc123'
    assert 'lpm-lib' in extra
    assert 'lpm-per' in extra
    assert 'lpm-med' in extra


def test_dlpmetadata_export_extra_no_lpm():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    # No add_lpm call — lpm fields should be absent (lpm2dict returns {} for None lib)
    extra = meta.export_extra()
    assert 'lpm-lib' not in extra


def test_dlpmetadata_add_lpm_full():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    lib, person, media = meta.add_lpm('VID')
    assert lib == 'VID'
    assert person == 'SomeChannel'
    assert media == 'vid-SomeChannel-abc123'


def test_dlpmetadata_add_tags_merges_into_extra():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    meta.add_tags({'show': 'My Show', 'season': '2'})
    extra = meta.export_extra()
    assert extra['show'] == 'My Show'
    assert extra['season'] == '2'


def test_dlpmetadata_add_tags_returns_and_accumulates():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    assert meta.add_tags({'a': '1'}) == {'a': '1'}
    assert meta.add_tags({'b': '2'}) == {'a': '1', 'b': '2'}


def test_dlpmetadata_always_tags_uploader_without_lpm():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    # No add_lpm call — uploader must still land as a flat searchable tag
    extra = meta.export_extra()
    assert extra['ytdl-uploader'] == 'SomeChannel'
    assert 'lpm-per' not in extra


def test_dlpmetadata_uploader_tag_prefers_creator():
    data = {**MINIMAL_DATA, 'creator': 'RealName'}
    meta = DLPMetaData(from_dict=data)
    assert meta.export_extra()['ytdl-uploader'] == 'RealName'


def test_dlpmetadata_caller_tags_override_derived():
    meta = DLPMetaData(from_dict=MINIMAL_DATA)
    meta.add_tags({'ytdl-uploader': 'Override'})
    assert meta.export_extra()['ytdl-uploader'] == 'Override'


def test_dlpmetadata_requires_one_source():
    with pytest.raises(AssertionError):
        DLPMetaData()


def test_dlpmetadata_rejects_both_sources():
    with pytest.raises(AssertionError):
        DLPMetaData(from_dict=MINIMAL_DATA, from_file=pathlib.Path('/dev/null'))


def test_dlpmetadata_get_media_file_from_filename():
    data = {**MINIMAL_DATA, 'filename': '/path/to/video.mp4'}
    meta = DLPMetaData(from_dict=data)
    assert meta.get_media_file() == pathlib.Path('/path/to/video.mp4')


def test_dlpmetadata_playlist_raises_no_media():
    data = {**MINIMAL_DATA, '_type': 'playlist'}
    meta = DLPMetaData(from_dict=data)
    with pytest.raises(NoMediaFile):
        meta.get_media_file()
