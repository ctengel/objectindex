#!/usr/bin/env python3

"""CLI for object index client"""

import argparse
import os
import pathlib
import sys
import warnings
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
        if fileobj:
            # TODO state whether it is a new upload?
            print(filename, fileobj.uuid)
        else:
            warnings.warn(f"Issue with file {filename}")

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


def get_s3_base(cli_value=None):
    """Resolve the simpler-objects base URL from --s3 or OBJIDX_S3"""
    base = cli_value or os.environ.get('OBJIDX_S3')
    if not base:
        raise SystemExit("requires --s3 or the OBJIDX_S3 environment variable")
    return base if base.endswith('/') else base + '/'


def _delete(obj_idx, args):
    s3_base = get_s3_base(args.s3)
    any_error = False
    if args.url:
        objids = []
        for url in args.item:
            files = obj_idx.search_files({'url': url})
            found = [f.object['uuid'] for f in files if f.object]
            if not found:
                print(url, 'NOT-FOUND')
                any_error = True
            objids.extend(found)
        # A URL's files may share an object with another URL's; delete once.
        objids = list(dict.fromkeys(objids))
    else:
        objids = args.item
    for objid in objids:
        try:
            done = client.delete_object_data(obj_idx, objid, s3_base)
        except (client.clilib.requests.RequestException, ValueError) as exc:
            print(objid, 'ERROR', exc)
            any_error = True
            continue
        if done:
            print(objid, 'DELETED')
        else:
            print(objid, 'RETRY-LATER')
            any_error = True
    return 1 if any_error else 0


def _scrub(obj_idx, args):
    s3_base = get_s3_base(args.s3)
    any_error = False
    for bucket in args.bucket:
        try:
            results = client.scrub_bucket(obj_idx, bucket, s3_base, check_all=args.all)
        except client.clilib.requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                raise SystemExit(f"{bucket}: unknown bucket") from exc
            raise
        for result in results:
            # Interleave clearing with printing so every object cleared before a
            # later fatal failure is still reported -- the operator needs that
            # list to re-upload.
            if args.clear and result.clearable:
                try:
                    client.clear_failed_upload(obj_idx, result.brief)
                except client.clilib.requests.HTTPError as exc:
                    raise SystemExit(
                        f"{bucket} {result.brief['uuid']}: clear failed: {exc}"
                    ) from exc
                result.cleared = True
            status = ('CLEARED' if result.cleared
                      else 'ERROR' if result.is_error else 'WARN')
            print(bucket, result.brief['uuid'], result.brief['key'],
                  result.category.value, status, result.detail)
            if result.is_error:
                any_error = True
    return 1 if any_error else 0


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
    parser_delete = subparsers.add_parser('delete')
    parser_delete.add_argument('-u', '--url', action='store_true',
                               help='arguments are original URLs, not object UUIDs')
    parser_delete.add_argument('--s3')
    parser_delete.add_argument('item', nargs='+')
    parser_delete.set_defaults(func=_delete)
    parser_scrub = subparsers.add_parser('scrub')
    parser_scrub.add_argument('bucket', nargs='+')
    parser_scrub.add_argument('--all', action='store_true')
    parser_scrub.add_argument('--clear', action='store_true')
    parser_scrub.add_argument('--s3')
    parser_scrub.set_defaults(func=_scrub)
    args = parser.parse_args()
    rc = args.func(client.get_obj_idx_env(), args)
    sys.exit(rc or 0)


if __name__ == '__main__':
    cli()
