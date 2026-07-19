"""Tests for the scrub classification logic in obj_idx/client.py"""

import base64
from unittest.mock import Mock, patch

import pytest

from obj_idx import client
from obj_idx.client import (
    ScrubCategory,
    ScrubResult,
    scrub_bucket,
    clear_failed_upload,
)

S3_BASE = 'http://s3.test/'
CKSUM = 'aa' * 32  # lowercase hex sha-256


def _repr_digest(hex_cksum):
    """Build a Repr-Digest header value from a hex checksum."""
    return 'sha-256=:' + base64.b64encode(bytes.fromhex(hex_cksum)).decode() + ':'


def _brief(completed, deleted, key='key.txt', checksum=CKSUM,
           obj_size=4, mime='text/plain'):
    return {
        'uuid': 'obj-uuid',
        'bucket': 'bucket1',
        'key': key,
        'obj_size': obj_size,
        'checksum': checksum,
        'mime': mime,
        'completed': completed,
        'deleted': deleted,
    }


def _head_resp(status_code=200, repr_digest=None, content_length=None,
               content_type=None):
    resp = Mock()
    resp.status_code = status_code
    headers = {}
    if repr_digest is not None:
        headers['Repr-Digest'] = repr_digest
    if content_length is not None:
        headers['Content-Length'] = str(content_length)
    if content_type is not None:
        headers['Content-Type'] = content_type
    resp.headers = headers
    return resp


def _mock_oi(briefs):
    oi = Mock()
    oi.list_objects.return_value = briefs
    return oi


# ---------------------------------------------------------------------------
# scrub_bucket: skip / non-HEAD cases
# ---------------------------------------------------------------------------

def test_completed_deleted_skipped():
    oi = _mock_oi([_brief(completed=True, deleted=True)])
    assert scrub_bucket(oi, 'bucket1', S3_BASE) == []


def test_completed_not_deleted_skipped_without_all():
    oi = _mock_oi([_brief(completed=True, deleted=False)])
    assert scrub_bucket(oi, 'bucket1', S3_BASE) == []


def test_incomplete_deleted_ready_for_reupload():
    oi = _mock_oi([_brief(completed=False, deleted=True)])
    results = scrub_bucket(oi, 'bucket1', S3_BASE)
    assert len(results) == 1
    assert results[0].category is ScrubCategory.READY_FOR_REUPLOAD
    assert results[0].is_error is True


# ---------------------------------------------------------------------------
# scrub_bucket: incomplete (not deleted) -> HEAD mapping
# ---------------------------------------------------------------------------

def test_incomplete_404_failed():
    oi = _mock_oi([_brief(completed=False, deleted=False)])
    with patch('obj_idx.client.head_locator', return_value=_head_resp(404)):
        results = scrub_bucket(oi, 'bucket1', S3_BASE)
    assert results[0].category is ScrubCategory.FAILED_OR_NEVER_STARTED
    assert results[0].is_error is True


def test_incomplete_503_in_progress():
    oi = _mock_oi([_brief(completed=False, deleted=False)])
    with patch('obj_idx.client.head_locator', return_value=_head_resp(503)):
        results = scrub_bucket(oi, 'bucket1', S3_BASE)
    assert results[0].category is ScrubCategory.UPLOAD_IN_PROGRESS
    assert results[0].is_error is True


def test_incomplete_200_broken():
    oi = _mock_oi([_brief(completed=False, deleted=False)])
    with patch('obj_idx.client.head_locator', return_value=_head_resp(200)):
        results = scrub_bucket(oi, 'bucket1', S3_BASE)
    assert results[0].category is ScrubCategory.BROKEN_INCOMPLETE
    assert results[0].is_error is True


def test_head_gets_obj_idx_credentials():
    # Both HEAD paths (incomplete probe and --all verification) authenticate
    # to the locator with the ObjectIndex's key/CA bundle.
    oi = _mock_oi([_brief(completed=False, deleted=False),
                   _brief(completed=True, deleted=False)])
    oi.api_key = 'sekrit'
    oi.ca_bundle = '/ca.pem'
    with patch('obj_idx.client.head_locator',
               return_value=_head_resp(404)) as mock_head:
        scrub_bucket(oi, 'bucket1', S3_BASE, check_all=True)
    assert mock_head.call_count == 2
    for call in mock_head.call_args_list:
        assert call.kwargs['api_key'] == 'sekrit'
        assert call.kwargs['ca_bundle'] == '/ca.pem'


# ---------------------------------------------------------------------------
# scrub_bucket: --all verification of completed objects
# ---------------------------------------------------------------------------

def test_all_completed_matching_yields_nothing():
    oi = _mock_oi([_brief(completed=True, deleted=False)])
    resp = _head_resp(200, repr_digest=_repr_digest(CKSUM),
                      content_length=4, content_type='text/plain')
    with patch('obj_idx.client.head_locator', return_value=resp):
        results = scrub_bucket(oi, 'bucket1', S3_BASE, check_all=True)
    assert results == []


def test_all_completed_checksum_mismatch():
    oi = _mock_oi([_brief(completed=True, deleted=False)])
    resp = _head_resp(200, repr_digest=_repr_digest('bb' * 32),
                      content_length=4, content_type='text/plain')
    with patch('obj_idx.client.head_locator', return_value=resp):
        results = scrub_bucket(oi, 'bucket1', S3_BASE, check_all=True)
    assert any(r.category is ScrubCategory.MISMATCH and r.is_error
               for r in results)


# ---------------------------------------------------------------------------
# ScrubResult.clearable
# ---------------------------------------------------------------------------

def test_clearable_categories():
    clearable = {ScrubCategory.FAILED_OR_NEVER_STARTED,
                 ScrubCategory.BROKEN_INCOMPLETE}
    for cat in ScrubCategory:
        result = ScrubResult(cat, _brief(completed=False, deleted=False))
        assert result.clearable is (cat in clearable)


# ---------------------------------------------------------------------------
# clear_failed_upload
# ---------------------------------------------------------------------------

def test_clear_failed_upload_puts_deleted():
    oi = Mock()
    oi.put_object.return_value = {'uuid': 'obj-uuid', 'deleted': True}
    brief = _brief(completed=False, deleted=False)
    result = clear_failed_upload(oi, brief)
    oi.put_object.assert_called_once_with('obj-uuid', {'deleted': True})
    assert result['deleted'] is True


def test_clear_failed_upload_raises_when_not_deleted():
    # The object completed between our HEAD and the PUT: API returns it
    # unchanged (deleted False) rather than deleting it.
    oi = Mock()
    oi.put_object.return_value = {'uuid': 'obj-uuid', 'completed': True,
                                  'deleted': False}
    with pytest.raises(client.clilib.requests.HTTPError):
        clear_failed_upload(oi, _brief(completed=False, deleted=False))
