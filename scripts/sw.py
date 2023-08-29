#!/usr/bin/env python3

"""Tools for uploading sw vid with LPM data"""

import pathlib
import string
import os
import argparse
import warnings
from obj_idx import client

LIBRARY = 'SSW'

def one_file(objidx, filename, bucket, base_url, pretend=False):
    """upload one file"""
    path = pathlib.Path(filename)
    url = base_url + path.name
    media = path.stem.removeprefix(LIBRARY.lower()).removesuffix('-HD')
    person = media.lstrip(string.digits).lstrip('-').rstrip(string.digits)
    print(filename, url, person, media)
    if pretend:
        return None
    flob = client.upload_metadata(filename=filename,
                                  obj_idx=objidx,
                                  bucket=bucket,
                                  url=url,
                                  direct=False,
                                  library=LIBRARY,
                                  person=person,
                                  media=media)
    if not flob:
        warnings.warn(f"Possible conflict for {filename}; upload failed")
        return None
    print(flob.uuid)
    return flob


def _cli():
    parser = argparse.ArgumentParser(description="Object Index SW uploader")
    parser.add_argument('-b', '--bucket', required=True)
    parser.add_argument('-p', '--pretend', action='store_true')
    parser.add_argument('-u', '--base-url', required=True)
    parser.add_argument('filename', nargs='+')
    oi_url = os.environ['OBJIDX_URL']
    oi_user = os.environ['OBJIDX_AUTH'].partition(':')[0]
    args = parser.parse_args()
    objidx = client.get_obj_idx(oi_url, oi_user)
    for filename in args.filename:
        one_file(objidx, filename, args.bucket, args.base_url, args.pretend)



if __name__ == "__main__":
    _cli()
