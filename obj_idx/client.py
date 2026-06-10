"""Combined ObjectIndex API and S3 API client library

Currently it relies on ObjectIndex for all info it needs on S3, other than bucket name
"""

import socket
import pathlib
import mimetypes
import datetime
import warnings
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit, urljoin
import os
import tempfile
import magic
from simpler_objects.client import (
    simple_upload,
    simple_download,
    file_checksum as checksum,
    parse_digest_header,
    ClientError,
)
from . import clilib
from .common import is_valid_url, reconcile_mime_ext, get_mime

SW_STRING = 'OIC-0.3.3'

def get_mime_data(file_path: pathlib.Path) -> str:
    """Determine mime type based on file data"""
    return  magic.detect_from_filename(str(file_path)).mime_type.lower()


def find_files(filename: str, obj_idx, is_url=False, must_direct=True):
    """Given a filename or URL, check if maybe we have it.

    Returns two booleans:\
    1st is checksum-based"""
    if not is_url:
        mypath = pathlib.Path(filename)
        assert mypath.exists()
        my_checksum = checksum(mypath)
        my_objects = obj_idx.search_object(my_checksum.hex())
        assert len(my_objects) <= 1
        if not my_objects:
            return []
        my_object = my_objects[0]
        assert my_object['checksum'] == my_checksum.hex()
        if not my_object['completed']:
            return []
        if my_object['deleted']:
            return []
        assert my_object['obj_size'] == mypath.stat().st_size
        assert my_object['files']
        file_objs = [obj_idx.file_obj_from_dict(f) for f in my_object['files']]
        for file_obj in file_objs:
            if not file_obj.object:
                file_obj.object = my_object.copy()
        return file_objs
    files = obj_idx.search_files({'url': filename})
    assert all(file.object for file in files)
    return [file for file in files
            if file.object['completed'] and not file.object['deleted']
            and (file.info['direct'] or not must_direct)]


def upload_core(filename: str,
                obj_idx: clilib.ObjectIndex,
                bucket: str,
                url: str,
                mtime: datetime.datetime,
                direct: bool = True,
                partial: bool = False,
                extra: dict = None,
                checksum_val: bytes = None,
                file_mime: str = None,
                key_hint: str = None) -> clilib.File:
    """Core upload function

    typically you want upload_local() or upload_remote()
    """
    if not is_valid_url(url):
        raise ValueError(f"invalid url: {url!r}")
    file_path = pathlib.Path(filename)
    file_stat = file_path.stat()
    file_checksum = checksum(file_path)
    if checksum_val:
        assert checksum_val == file_checksum
    data_mime = get_mime_data(file_path)
    if file_mime:
        if data_mime and file_mime != data_mime:
            warnings.warn(f"Given MIME type {file_mime} doesn't seem to match apparent data {data_mime}")
    else:
        file_mime = data_mime
    if not key_hint:
        key_hint = os.path.basename(urlsplit(url).path)
    key_hint, file_mime = reconcile_mime_ext(key_hint, file_mime)
    try:
        my_file = obj_idx.initiate_upload(url=url,
                                          bucket=bucket,
                                          obj_size=file_stat.st_size,
                                          # TODO timezone
                                          mtime=mtime,
                                          filename=key_hint,
                                          extra_file=extra,
                                          checksum=file_checksum,
                                          mime=file_mime,
                                          direct=direct,
                                          partial=partial)
    except clilib.requests.HTTPError as e:
        # Only 409 (upload in progress / not-yet-scrubbed failure) is retriable:
        # warn and skip so a batch keeps going. 400 (size/direct-partial
        # mismatch) and 410 (deleted) have no easy fix, so let them propagate.
        if e.response.status_code != 409:
            raise e
        conflict = e.response.json()
        warnings.warn(f"Conflict for file {url} {file_checksum.hex()}... "
                      f"existing object {conflict['object_uuid']}"
                      + (f" file {conflict['file_uuid']}"
                         if conflict.get('file_uuid') else ""))
        # TODO consider throwing an exception?
        return None

    if not my_file.exists():
        s3_url = my_file.get_s3_url()
        simple_upload(filename, s3_url, file_mime, file_checksum)
        my_file.finish_upload()
    return my_file


def upload_local(filename: str,
                 obj_idx: clilib.ObjectIndex,
                 bucket: str,
                 url: str = None,
                 mtime: datetime.datetime = None,
                 direct: bool = True,
                 partial: bool = False,
                 extra: dict = None,
                 checksum_val: bytes = None,
                 file_mime: str = None,
                 key_hint: str = None) -> clilib.File:
    """Upload a local file"""
    # TODO consider refactoring information gathering with mediacrawler fs.File.get_media()
    file_path = pathlib.Path(filename)
    file_stat = file_path.stat()
    if not url:
        assert direct
        assert not partial
        # TODO consider using file_path.resolve() instead?
        file_base_uri = str(file_path.absolute().as_uri())
        url = f"{file_base_uri[:7]}{socket.gethostname()}{file_base_uri[7:]}"
        if not key_hint:
            key_hint = file_path.name
    if not mtime:
        # TODO timezone
        mtime = datetime.datetime.fromtimestamp(file_stat.st_mtime)
    if not extra:
        extra = {}
    return upload_core(filename, obj_idx, bucket, url,
                       mtime=mtime,
                       direct=direct,
                       partial=partial,
                       extra=extra,
                       checksum_val=checksum_val,
                       file_mime=file_mime,
                       key_hint=key_hint)

def upload_remote(url: str,
                  obj_idx: clilib.ObjectIndex,
                  bucket: str,
                  mtime: datetime.datetime = None,
                  partial: bool = False,
                  extra: dict = None,
                  key_hint: str = None,
                  check_exists: bool = True,
                  catch_dl_err: bool = False) -> clilib.File:
    """Upload a remote file"""
    if check_exists:
        finds = find_files(url, obj_idx, is_url=True)
        if finds:
            warnings.warn(f"Already got {url} as {finds[0].uuid}")
            return finds[0]
    with tempfile.NamedTemporaryFile() as temp:
        try:
            digest, mime, new_keyhint, new_mtime = simple_download(url, temp.name)
        except ClientError as excp:
            if catch_dl_err:
                warnings.warn(str(excp))
                return None
            raise excp
        if not key_hint:
            key_hint = new_keyhint
        if not mtime:
            mtime = new_mtime
        if not mtime:
            mtime = datetime.datetime.now()
        fileobj = upload_core(temp.name, obj_idx, bucket, url,
                              mtime=mtime,
                              direct=True,
                              partial=partial,
                              extra=extra,
                              checksum_val=digest,
                              file_mime=mime,
                              key_hint=key_hint)
    return fileobj


def upload(filename: str,
           obj_idx: clilib.ObjectIndex,
           bucket: str,
           tags: dict,
           checksum_val: bytes = None,
           file_mime: str = None,
           orig_url: str = None) -> clilib.File:
    """Run an actual file upload into ObjIdx and S3"""
    warnings.warn("Deprecated use of upload; consider using upload_local.")
    return upload_local(filename, obj_idx, bucket,
                        url=orig_url,
                        extra=tags,
                        checksum_val=checksum_val,
                        file_mime=file_mime)


def get_obj_idx(url, user):
    """Get ObjectIndex object"""
    # TODO add in user and auth
    return clilib.ObjectIndex(url, host=socket.gethostname(), sw=SW_STRING, user=user)


def get_obj_idx_env():
    """Get objidx from environment"""
    oi_url = os.environ['OBJIDX_URL']
    oi_user = os.environ['OBJIDX_AUTH'].partition(':')[0]
    objidx = get_obj_idx(oi_url, oi_user)
    return objidx


def head_locator(s3_base: str, bucket: str, key: str, timeout: int = clilib.TIMEOUT):
    """HEAD an object on the simpler-objects locator, following its 307.

    Returns the raw requests.Response. 200 means present, 503 an upload is in
    progress, 404 absent; the caller interprets these (we do not raise).
    ``allow_redirects`` is required: the locator answers a hit with a 307 to the
    backend, whose reply carries the ``Repr-Digest`` and ``Content-Type``.
    """
    url = urljoin(s3_base, f"{bucket}/{key}")
    return clilib.requests.head(url, allow_redirects=True, timeout=timeout)


class ScrubCategory(str, Enum):
    """How a scrubbed object compares between ObjectIndex and simpler-objects."""

    FAILED_OR_NEVER_STARTED = "failed or never started"
    UPLOAD_IN_PROGRESS = "upload in progress"
    BROKEN_INCOMPLETE = "complete in simpler-objects but broken/incomplete in objindex"
    READY_FOR_REUPLOAD = "ready for re-upload-attempt"
    MISMATCH = "mismatch in simpler-objects"
    CTYPE_WARNING = "content-type mismatch"


@dataclass
class ScrubResult:
    """One anomaly (or warning) found while scrubbing a bucket."""

    category: ScrubCategory
    brief: dict  # the ObjectBrief; carries uuid so --clear can act
    detail: str = ""
    is_error: bool = False  # True => contributes to a nonzero exit
    cleared: bool = False  # set once --clear's PUT deleted=True succeeds

    @property
    def clearable(self) -> bool:
        """Whether ``--clear`` may auto-delete this failed upload.

        Only an incomplete object whose bytes are absent (404) or present but
        unregistered (307/200) is safe to clear. 503 (upload in progress) needs
        a simpler-objects scrub first; READY_FOR_REUPLOAD is already deleted;
        MISMATCH/CTYPE_WARNING concern completed objects.
        """
        return self.category in (ScrubCategory.FAILED_OR_NEVER_STARTED,
                                 ScrubCategory.BROKEN_INCOMPLETE)


def clear_failed_upload(obj_idx: clilib.ObjectIndex, brief: dict) -> dict:
    """PUT deleted=True for a failed upload, readying it for re-upload.

    Returns the updated object. Raises on any HTTP failure (incl. 409) so the
    caller can treat it as fatal. Also raises if the object came back not
    deleted: the API refuses to delete an object that *completed* between our
    HEAD and this PUT (returning it unchanged), and we must not claim a clear
    that did not happen.
    """
    updated = obj_idx.put_object(brief['uuid'], {"deleted": True})
    if not updated.get('deleted'):
        raise clilib.requests.HTTPError(
            f"object {brief['uuid']} not deleted (completed in the meantime?)")
    return updated


def _scrub_completed(brief: dict, s3_base: str, timeout: int) -> list[ScrubResult]:
    """Verify a completed object actually matches in simpler-objects (--all)."""
    resp = head_locator(s3_base, brief['bucket'], brief['key'], timeout)
    if resp.status_code != 200:
        return [ScrubResult(ScrubCategory.MISMATCH, brief,
                            detail=f"HTTP {resp.status_code}", is_error=True)]
    out = []
    digest = parse_digest_header(resp.headers.get('Repr-Digest')
                                 or resp.headers.get('Content-Digest'))
    if digest is None or digest.hex() != brief['checksum']:
        out.append(ScrubResult(
            ScrubCategory.MISMATCH, brief,
            detail=f"checksum {digest.hex() if digest else None} != {brief['checksum']}",
            is_error=True))
    clen = resp.headers.get('Content-Length')
    if clen is not None and int(clen) != brief['obj_size']:
        out.append(ScrubResult(ScrubCategory.MISMATCH, brief,
                               detail=f"size {clen} != {brief['obj_size']}",
                               is_error=True))
    # Content-type is warn-only: the object server infers it from the key's
    # extension and need not byte-match the stored mime.
    ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
    if ctype and brief.get('mime') and ctype != brief['mime'].lower():
        out.append(ScrubResult(ScrubCategory.CTYPE_WARNING, brief,
                               detail=f"content-type {ctype} != {brief['mime']}",
                               is_error=False))
    return out


def scrub_bucket(obj_idx: clilib.ObjectIndex,
                 bucket: str,
                 s3_base: str,
                 check_all: bool = False,
                 timeout: int = clilib.TIMEOUT) -> list[ScrubResult]:
    """Cross-check every object in a bucket against simpler-objects.

    Returns a list of anomalies/warnings (no output here). Objects that are
    completed+deleted (and, without ``check_all``, completed+not-deleted) are
    skipped and yield nothing; a completed object that fully matches under
    ``check_all`` also yields nothing.
    """
    results = []
    for brief in obj_idx.list_objects(bucket):
        completed, deleted = brief['completed'], brief['deleted']
        if completed and deleted:
            continue
        if not completed and deleted:
            results.append(ScrubResult(ScrubCategory.READY_FOR_REUPLOAD, brief,
                                       is_error=True))
            continue
        if not completed:  # and not deleted
            resp = head_locator(s3_base, brief['bucket'], brief['key'], timeout)
            if resp.status_code == 404:
                category = ScrubCategory.FAILED_OR_NEVER_STARTED
            elif resp.status_code == 503:
                category = ScrubCategory.UPLOAD_IN_PROGRESS
            else:
                # 200 (or anything unexpected): bytes exist but the index never
                # marked the object complete.
                category = ScrubCategory.BROKEN_INCOMPLETE
            results.append(ScrubResult(category, brief,
                                       detail=f"HTTP {resp.status_code}",
                                       is_error=True))
            continue
        # completed and not deleted
        if check_all:
            results.extend(_scrub_completed(brief, s3_base, timeout))
    return results


def download(obj_idx: clilib.ObjectIndex, url: str, pretend: bool = False) -> list[clilib.File]:
    """Download a file with given original URL"""
    files = obj_idx.search_files({'url': url})
    if pretend:
        return files
    for file in files:
        s3_url = file.get_s3_url()
        # TODO allow selecting target
        tgt_filename = s3_url.rsplit('/', 1)[-1]
        dl_cksum, _, _, _ = simple_download(s3_url, tgt_filename)
        if dl_cksum:
            assert file.object['checksum'] == dl_cksum.hex()
        assert file.object['checksum'] == checksum(tgt_filename).hex()
    return files

def upload_metadata(filename: str,
                    obj_idx: clilib.ObjectIndex,
                    bucket: str,
                    url: str,
                    mtime: datetime.datetime = None,
                    direct: bool = True,
                    partial: bool = False,
                    library: str = None,
                    person: str = None,
                    media: str = None,
                    ytdl_info: dict = None,
                    extra: dict = None) -> clilib.File:
    """Upload file with metadata"""
    warnings.warn("Deprecated use of upload_metadata; consider using upload_local or dlp_meta.")
    if not extra:
        extra = {}
    if library:
        library = library.upper()
        if person:
            person = f"{library}{person.lower()}"
        if media:
            media = f"{library}{media.lower()}"
        extra['lpm-lib'] = library
        extra['lpm-per'] = person
        extra['lpm-med'] = media
    else:
        assert not person
        assert not media
    if ytdl_info:
        extra['ytdl-info'] = ytdl_info
        extra['ytdl-extractor'] = ytdl_info['extractor_key'].lower()
        extra['ytdl-id'] = f"{ytdl_info['extractor_key'].lower()} {ytdl_info['id']}"
        if not mtime and ytdl_info.get('timestamp'):
            mtime = datetime.datetime.fromtimestamp(ytdl_info['timestamp'])
    else:
        extra['ytdl-info'] = None
    return upload_local(filename, obj_idx, bucket,
                        url=url,
                        mtime=mtime,
                        direct=direct,
                        partial=partial,
                        extra=extra)
