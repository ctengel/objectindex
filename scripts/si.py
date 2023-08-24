#!/usr/bin/env python3

"""Script for certian kind of file upload"""

import datetime
import argparse
import os
import json
import string
from obj_idx import client

LIBRARY = 'VSI'


def upload(objidx, metadata, bucket, base_url, pretend=False):
    """Upload a given file based on JSON metadata"""
    filename = metadata['siteName'] + ' ' + metadata['videoName'] + '.mp4'
    qualmod = ''
    if not metadata['versionHigh']:
        qualmod = 'low/'
    url = base_url + qualmod + filename
    person = metadata['videoName'].rstrip(string.digits).rstrip().removesuffix(' all').removesuffix(' car').removesuffix(' Interview').removeprefix('Images ')
    if person in ['Early Models', 'UK', 'Volume']:
        person = None
    media = metadata['siteName'] + '-' + metadata['videoName'].replace(" ", "")
    mtime = None
    if metadata['updatedDate']:
        mtime = datetime.datetime.fromisoformat(metadata['updatedDate'])
    print(person, media)
    if pretend:
        return None
    flob = client.upload_metadata(filename,
                                  objidx,
                                  bucket=bucket,
                                  url=url,
                                  library=LIBRARY,
                                  person=person,
                                  media=media,
                                  extra={f"{LIBRARY}-info": metadata},
                                  mtime=mtime)
    print(flob.uuid)
    return flob

def _cli():
    parser = argparse.ArgumentParser(description="Object Index SI uploader")
    parser.add_argument('-b', '--bucket')
    parser.add_argument('-u', '--base-url',)
    parser.add_argument('-p', '--pretend', action='store_true')
    parser.add_argument('filename')
    oi_url = os.environ['OBJIDX_URL']
    oi_user = os.environ['OBJIDX_AUTH'].partition(':')[0]
    args = parser.parse_args()

    with open(args.filename, encoding="utf-8") as user_file:
        parsed_json = json.load(user_file)
    objidx = client.get_obj_idx(oi_url, oi_user)
    for media in parsed_json:
        upload(objidx, media, args.bucket, args.base_url, args.pretend)


if __name__ == '__main__':
    _cli()
