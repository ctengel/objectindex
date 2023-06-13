"""Combined ObjectIndex API and S3 API client library

Currently it relies on ObjectIndex for all info it needs on S3, other than bucket name
"""

from . import s3lib, clilib

def upload(filename: str, obj_idx: clilib.ObjectIndex, bucket: str, tags: dict):
    """Run an actual file upload into ObjIdx and S3"""
    # TODO calculate filename, ignoring prefix
    # TODO calculate url, likely file://[hostname?]/path
    # TODO gather data on file... obj_size, mtime, checksum, mime
    my_file = obj_idx.initiate_upload(url=None,
                                      bucket=bucket,
                                      obj_size=None,
                                      mtime=None,
                                      filename=None,
                                      extra_file=tags)
    if not my_file.exists():
        s3_url = my_file.get_s3_url()
        # TODO send checksum
        bucket = s3lib.get_s3_service_url(s3_url['server']).Bucket(s3_url['bucket'])
        bucket.upload_file(filename, s3_url['key'])
        my_file.finish_upload()
    return my_file

def get_obj_idx(url):
    """Get ObjectIndex object"""
    # TODO add in host, user, sw
    return clilib.ObjectIndex(url)
