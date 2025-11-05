#!/usr/bin/env python3

"""Script for dlp upload"""

import argparse
import warnings
from obj_idx import client, dlp_lpm_meta


def do_info_json(objidx, info_json, bucket, pretend=False, partial=False, library=None):
    """Given a .info.json file, parse it and upload with relevant metadata

    Partial should be specified for live or whenever a URL is not fully captured

    Specify library if uploader is a person
    """
    parsed_json = dlp_lpm_meta.DLPMetaData(from_file=info_json, partial=partial)
    print(parsed_json.add_lpm(library))
    if pretend:
        return
    try:
        print(parsed_json.upload(objidx, bucket).uuid)
    except dlp_lpm_meta.NoMediaFile as nmfe:
        warnings.warn(str(nmfe))


def _cli():
    parser = argparse.ArgumentParser(description="Object Index YT uploader")
    parser.add_argument('-b', '--bucket', required=True)
    parser.add_argument('-p', '--pretend', action='store_true')
    parser.add_argument('-P', '--partial', action='store_true')
    parser.add_argument('-l', '--library')
    parser.add_argument('filename', nargs='+')
    args = parser.parse_args()
    objidx = client.get_obj_idx_env()
    for filename in args.filename:
        do_info_json(objidx, filename, args.bucket, args.pretend, args.partial, args.library)


if __name__ == '__main__':
    _cli()
