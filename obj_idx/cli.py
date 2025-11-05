#!/usr/bin/env python3

"""CLI for object index client"""

import argparse
import pathlib
from . import client

def _upload(obj_idx, args):
    tags = {x.partition('=')[0]: x.partition('=')[2] for x in args.tag}
    for filename in args.filename:
        if args.url:
            fileobj = client.upload_remote(filename, obj_idx, args.bucket,
                                           extra=tags)
        else:
            fileobj = client.upload_local(filename, obj_idx, args.bucket,
                                          extra=tags)
        # TODO state whether it is a new upload?
        print(filename, fileobj.uuid)

def _download(obj_idx, args):
    for url in args.url:
        files = client.download(obj_idx, url, args.pretend)
        for file in files:
            print(url, file.info['url'], file.uuid, file.get_s3_url())

def _check(obj_idx, args):
    for filename in args.filename:
        files = client.find_files(filename, obj_idx)
        if not files:
            print(filename, 'not found')
            continue
        my_object = files[0].object
        print(my_object['uuid'], my_object['mime'], my_object['bucket'], my_object['key'],
              filename,
              [(f.uuid, f.info['url']) for f in files])
        if args.rm:
            pathlib.Path(filename).unlink()


def cli():
    """CLI main function"""
    parser = argparse.ArgumentParser(description="Object Index client")
    subparsers = parser.add_subparsers()
    parser_upload = subparsers.add_parser('upload')
    parser_upload.add_argument('-b', '--bucket')
    parser_upload.add_argument('-t', '--tag', action='append', default=[])
    parser_upload.add_argument('-u', '--url', action='store_true')
    parser_upload.add_argument('filename', nargs='+')
    parser_upload.set_defaults(func=_upload)
    parser_download = subparsers.add_parser('download')
    parser_download.add_argument('-p', '--pretend', action='store_true')
    parser_download.add_argument('url', nargs='+')
    parser_download.set_defaults(func=_download)
    parser_check = subparsers.add_parser('check')
    parser_check.add_argument('-r', '--rm', action='store_true')
    parser_check.add_argument('filename', nargs='+')
    parser_check.set_defaults(func=_check)
    args = parser.parse_args()
    args.func(client.get_obj_idx_env(), args)


if __name__ == '__main__':
    cli()
