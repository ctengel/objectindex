"""Combined ObjectIndex API and S3 API client library

Currently it relies on ObjectIndex for all info it needs on S3, other than bucket name
"""

import socket
import pathlib
import hashlib
import mimetypes
import datetime
import warnings
import base64
from urllib.parse import urlsplit, urlparse
import os
import tempfile
import requests
from . import clilib

SW_STRING = 'OIC-0.2'
BLOCK_SIZE = 16777216

def parse_digest_header(header_value: str) -> bytes:
    """Read SHA256 binary value from HTTP Content-Digest value"""
    if not header_value:
        return None
    for pair in header_value.split(','):
        algo, equals, digest = pair.partition('=')
        assert equals == '='
        if not algo == 'sha256':
            continue
        return base64.b64decode(digest.strip(':'))
    return None

def encode_digest_header(checksum_val: bytes) -> str:
    """Encode SHA256 digest into an HTTP Content-Digest value"""
    return f"sha256=:{base64.b64encode(checksum_val)}:"

def simple_upload(filename, url, file_mime, checksum_val=None):  #, fh=False):
    """Simpler Objects upload"""
    headers = {'Content-Type': file_mime}
    if checksum_val:
        headers['Content-Digest'] = encode_digest_header(checksum_val)
    #if fh:
    #    response = requests.put(url, data=filename, headers=headers)
    #    response.raise_for_status()
    #    return
    with open(filename, 'rb') as f:
        response = requests.put(url, data=f, headers=headers)
        response.raise_for_status()

def read_content_disposition(header_value: str) -> str:
    """Read filename from HTTP Content-Disposition"""
    # TODO use pyrfc6266
    if not header_value:
        return None
    if "filename=" not in header_value:
        return None
    filename_start = header_value.find("filename=") + len("filename=")
    filename = header_value[filename_start:].strip('";')
    return filename

def read_http_datetime(header_value: str) -> datetime.datetime:
    """Given an HTTP date (like for Last-Modified), return Python object"""
    # TODO use dateutil
    if not header_value:
        return None
    return datetime.datetime.strptime(header_value, '%a, %d %b %Y %X %Z')

def simple_download(url, filename):
    """Simpler Objects download"""
    result = requests.get(url, stream=True, headers={'Want-Content-Digest': 'sha-256=9'})
    result.raise_for_status()
    digest = parse_digest_header(result.headers.get('Content-Digest'))
    mime = result.headers.get('Content-Type')
    sugg_fname = read_content_disposition(result.headers.get('Content-Disposition'))
    mtime = read_http_datetime(result.headers.get('Last-Modified'))
    with open(filename, 'wb') as f:
        for chunk in result.iter_content(chunk_size=BLOCK_SIZE):
            if chunk: # Filter out keep-alive new chunks
                f.write(chunk)
    return digest, mime, sugg_fname, mtime


def checksum(file_path: pathlib.Path) -> bytes:
    """Get SHA256 checksum of a given path"""
    check = hashlib.sha256()
    with open(file_path, "rb") as file_obj:
        while True:
            data = file_obj.read(BLOCK_SIZE)
            if len(data) == 0:
                break
            check.update(data)
    return check.digest()

def get_mime(file_path: pathlib.Path) -> str:
    """Determine MIME type of a given path"""
    # TODO add magic from mediacrawler
    return mimetypes.guess_type(file_path)[0]

# TODO consider moving/removing
def is_valid_url(url_string):
    """True if URL, False if not"""
    try:
        result = urlparse(url_string)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

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
    file_path = pathlib.Path(filename)
    file_stat = file_path.stat()
    file_checksum = checksum(file_path)
    if checksum_val:
        assert checksum_val == file_checksum
    if not file_mime:
        file_mime = get_mime(file_path)
    if not key_hint:
        key_hint = os.path.basename(urlsplit(url).path)

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
        if e.response.status_code != 409:
            raise e
        warnings.warn(f"Conflict for file {url} {file_checksum.hex()}... "
                      f"existing object {e.response.json()['object_uuid']}")
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
                  check_exists: bool = True) -> clilib.File:
    """Upload a remote file"""
    if check_exists:
        finds = find_files(url, obj_idx, is_url=True)
        if finds:
            return finds[0]
    with tempfile.NamedTemporaryFile() as temp:
        digest, mime, new_keyhint, new_mtime = simple_download(url, temp.name)
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
    return upload_local(filename, obj_idx, bucket,
                        url=orig_url,
                        extra=tags,
                        checksum_val=checksum_val,
                        file_mime=file_mime)


def get_obj_idx(url, user):
    """Get ObjectIndex object"""
    # TODO add in user and auth
    return clilib.ObjectIndex(url, host=socket.gethostname(), sw=SW_STRING, user=user)

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
            assert file.object['checksum'] == dl_cksum
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
        if not mtime:
            mtime = datetime.datetime.fromtimestamp(ytdl_info['timestamp'])
    else:
        extra['ytdl-info'] = None
    return upload_local(filename, obj_idx, bucket,
                        url=url,
                        mtime=mtime,
                        direct=direct,
                        partial=partial,
                        extra=extra)
