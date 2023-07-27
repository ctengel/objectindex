"""Combined ObjectIndex API and S3 API client library

Currently it relies on ObjectIndex for all info it needs on S3, other than bucket name
"""

import socket
import pathlib
import hashlib
import mimetypes
import datetime
from . import s3lib, clilib

SW_STRING = 'OIC-0.1'
BLOCK_SIZE = 16777216

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

def upload(filename: str, obj_idx: clilib.ObjectIndex, bucket: str, tags: dict):
    """Run an actual file upload into ObjIdx and S3"""
    # TODO consider refactoring information gathering with mediacrawler fs.File.get_media()
    file_path = pathlib.Path(filename)
    file_stat = file_path.stat()
    file_checksum = checksum(file_path)
    file_mime = get_mime(file_path)
    # TODO consider using file_path.resolve() instead?
    my_file = obj_idx.initiate_upload(url=f"file://{socket.gethostname()}{file_path.absolute()}",
                                      bucket=bucket,
                                      obj_size=file_stat.st_size,
                                      # TODO timezone
                                      mtime=datetime.datetime.fromtimestamp(file_stat.st_mtime),
                                      filename=file_path.name,
                                      extra_file=tags,
                                      checksum=file_checksum,
                                      mime=file_mime)
    if not my_file.exists():
        s3_url = my_file.get_s3_url()
        bucket = s3lib.get_s3_service_url(s3_url['server']).Bucket(s3_url['bucket'])
        # TODO send checksum; see https://github.com/boto/boto3/issues/3604
        bucket.upload_file(filename, s3_url['key'])
        my_file.finish_upload()
    return my_file

def get_obj_idx(url, user):
    """Get ObjectIndex object"""
    # TODO add in user and auth
    return clilib.ObjectIndex(url, host=socket.gethostname(), sw=SW_STRING, user=user)

def download(obj_idx: clilib.ObjectIndex, url: str, pretend: bool = False):
    """Download a file with given original URL"""
    files = obj_idx.search_files({'url': url})
    if pretend:
        return files
    for file in files:
        s3_url = file.get_s3_url()
        bucket = s3lib.get_s3_service_url(s3_url['server']).Bucket(s3_url['bucket'])
        # TODO allow selecting target
        bucket.download_file(s3_url['key'], s3_url['key'])
    # TODO verify
    return files
