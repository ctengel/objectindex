#!/usr/bin/env python3

"""Script for dlp upload"""

import argparse
import os
import json
import pathlib
import warnings
from obj_idx import client


def read_info_json(filename):
    """Return data from a JSON file"""
    with open(filename, encoding="utf-8") as user_file:
        parsed_json = json.load(user_file)
    return parsed_json

def upload(objidx, metadata, filename, bucket, pretend=False, partial=False, library=None):
    """Upload a given file based on JSON metadata"""
    url = metadata.get('webpage_url')
    if not (url and url.startswith('http')):
        url = metadata.get('url')
    assert url.startswith('http')
    person = None
    media = None
    if library:
        person = metadata.get('uploader')
        if partial:
            assert person
            media = f'live-{person}-{starttime}-{metadata.get("id")}'
        else:
            if person:
                media = f'vid-{person}-{metadata.get("id")}'
            else:
                media = metadata.get("id")
    print(filename, url, person, media)
    if pretend:
        return None
    flob = client.upload_metadata(filename,
                                  objidx,
                                  bucket=bucket,
                                  url=url,
                                  direct=False,
                                  partial=partial,
                                  ytdl_info=metadata,
                                  library=library,
                                  person=person,
                                  media=media)
    print(flob.uuid)
    return flob

def do_info_json(objidx, info_json, bucket, pretend=False, partial=False, library=None):
    """Given a .info.json file, parse it and upload with relevant metadata

    Partial should be specified for live or whenever a URL is not fully captured

    Specify library if uploader is a person
    """
    parsed_json = read_info_json(info_json)
    if parsed_json.get('_type') == 'playlist':
        warnings.warn(f"Skipping playlist {info_json}")
        return
    extension = parsed_json.get('ext')
    assert extension
    base_file_name = info_json.removesuffix('.info.json')
    assert base_file_name != info_json
    media_file = base_file_name + "." + extension
    assert pathlib.Path(media_file).exists()
    upload(objidx, parsed_json, media_file, bucket, pretend, partial, library)


def _cli():
    parser = argparse.ArgumentParser(description="Object Index YT uploader")
    parser.add_argument('-b', '--bucket', required=True)
    parser.add_argument('-p', '--pretend', action='store_true')
    parser.add_argument('-P', '--partial', action='store_true')
    parser.add_argument('-l', '--library')
    parser.add_argument('filename', nargs='+')
    oi_url = os.environ['OBJIDX_URL']
    oi_user = os.environ['OBJIDX_AUTH'].partition(':')[0]
    args = parser.parse_args()
    objidx = client.get_obj_idx(oi_url, oi_user)
    for filename in args.filename:
        do_info_json(objidx, filename, args.bucket, args.pretend, args.partial, args.library)


if __name__ == '__main__':
    _cli()
