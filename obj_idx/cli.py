#!/usr/bin/env python3

"""CLI for object index client"""

import argparse
import os
from . import client

def _upload(obj_idx, args):
    tags = {x.partition('=')[0]: x.partition('=')[2] for x in args.tag}
    for filename in args.filename:
        fileobj = client.upload(filename, obj_idx, args.bucket, tags)
        # TODO state whether it is a new upload?
        print(filename, fileobj.uuid)

def _download(obj_idx, args):
    for url in args.url:
        files = client.download(obj_idx, url, args.pretend)
        for file in files:
            print(url, file.info['url'], file.uuid, file.get_s3_url())

def cli():
    """CLI main function"""
    parser = argparse.ArgumentParser(description="Object Index client")
    subparsers = parser.add_subparsers()
    parser_upload = subparsers.add_parser('upload')
    parser_upload.add_argument('-b', '--bucket')
    parser_upload.add_argument('-t', '--tag', action='append', default=[])
    parser_upload.add_argument('filename', nargs='+')
    parser_upload.set_defaults(func=_upload)
    parser_download = subparsers.add_parser('download')
    parser_download.add_argument('-p', '--pretend', action='store_true')
    parser_download.add_argument('url', nargs='+')
    parser_download.set_defaults(func=_download)
    oi_url = os.environ['OBJIDX_URL']
    oi_user = os.environ['OBJIDX_AUTH'].partition(':')[0]
    args = parser.parse_args()
    args.func(client.get_obj_idx(oi_url, oi_user), args)


if __name__ == '__main__':
    cli()
