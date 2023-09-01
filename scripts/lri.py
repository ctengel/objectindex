#!/usr/bin/env python3

"""Script for dlp upload"""

import argparse
import os
import json
import pathlib
import warnings
import datetime
from obj_idx import client


def read_info_json(filename):
    """Return data from a JSON file"""
    with open(filename, encoding="utf-8") as user_file:
        parsed_json = json.load(user_file)
    return parsed_json["id"], parsed_json, datetime.datetime.fromisoformat(parsed_json["timestamp"]), parsed_json["models"]

def upload(objidx,
           metadata,
           filename,
           bucket,
           mtime=None,
           pretend=False,
           library=None,
           person=None,
           media=None,
           base_url=None):
    """Upload a given file based on JSON metadata"""
    url = base_url + str(filename)
    print(filename, url, person, media)
    if pretend:
        return None
    flob = client.upload_metadata(str(filename),
                                  objidx,
                                  bucket=bucket,
                                  url=url,
                                  direct=False,
                                  extra={f"{library}-info": metadata},
                                  mtime=mtime,
                                  library=library,
                                  person=person,
                                  media=media)
    if not flob:
        warnings.warn(f"Possible conflict for {filename}; upload failed")
        return None
    print(flob.uuid)
    return flob

def do_info_json(objidx,
                 info_json,
                 bucket,
                 base_url,
                 pretend=False,
                 library=None,
                 sub_library=None):
    """Given a .json file, parse it and upload with relevant metadata"""
    dirid, extra, mtime, persons = read_info_json(info_json)
    pers = "-".join(persons).replace(" ", "")
    media = sub_library + str(dirid)
    dirf = pathlib.Path(str(dirid))
    zipf = dirf.with_suffix(".zip")
    did_something = False
    if zipf.is_file():
        if upload(objidx, extra, zipf, bucket,  mtime, pretend, library, pers, media, base_url):
            did_something = True
    if dirf.is_dir():
        for subf in dirf.iterdir():
            if upload(objidx, extra, subf, bucket,  mtime, pretend, library, pers, media, base_url):
                did_something = True
    if not did_something:
        warnings.warn(f"Skipping nonexistant {media}")

def _cli():
    parser = argparse.ArgumentParser(description="Object Index YT uploader")
    parser.add_argument('-b', '--bucket', required=True)
    parser.add_argument('-p', '--pretend', action='store_true')
    parser.add_argument('-l', '--library')
    parser.add_argument('-s', '--sub-library')
    parser.add_argument('-u', '--url-base')
    parser.add_argument('filename', nargs='+')
    oi_url = os.environ['OBJIDX_URL']
    oi_user = os.environ['OBJIDX_AUTH'].partition(':')[0]
    args = parser.parse_args()
    objidx = client.get_obj_idx(oi_url, oi_user)
    for filename in args.filename:
        do_info_json(objidx, filename, args.bucket, args.url_base, args.pretend, args.library, args.sub_library)


if __name__ == '__main__':
    _cli()
