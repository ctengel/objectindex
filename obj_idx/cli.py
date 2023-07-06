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
        print(args.filename, fileobj.uuid)

def cli():
    """CLI main function"""
    parser = argparse.ArgumentParser(description="Object Index client")
    subparsers = parser.add_subparsers()
    parser_upload = subparsers.add_parser('upload')
    parser_upload.add_argument('-b', '--bucket')
    parser_upload.add_argument('-t', '--tag', action='append')
    parser_upload.add_argument('filename', nargs='+')
    parser_upload.set_defaults(func=_upload)
    oi_url = os.environ['OBJIDX_URL']
    args = parser.parse_args()
    args.func(client.get_obj_idx(oi_url), args)


if __name__ == '__main__':
    cli()
