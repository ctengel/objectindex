#!/usr/bin/env python3

"""Tool to generate sha256sum style check file from OI-style filenames

NOTE THIS DOES NOT ACTUALLY COMPUTE CHECKSUMS (but you can use it to verify with sha256sum -c)

Designed to be used with simpler-objects style POSIXy store
"""

import argparse
import pathlib

def file_checksum_from_name(file):
    """Pull out the checksum portion of an OI object name"""
    checksum, dash, _ = file.name.partition('-')
    assert dash == '-'
    assert len(checksum) == 64
    return checksum

def grab_checksums(bucket):
    """Grab a list of tuples of all checksums and filenames in a dir/bucket"""
    assert bucket.is_dir()
    return [(file_checksum_from_name(file), file.name) for file in bucket.iterdir()]

def format_checksums(checksums):
    """Format list of tuples into a text file"""
    return "\n".join([f"{checksum}  {filename}" for checksum, filename in checksums]) + "\n"

def bucket_checksum(bucket_name):
    """Pull all checksums from filenames and generate bucket.sha256sum file"""
    bucket = pathlib.Path(bucket_name)
    checksum_text = format_checksums(grab_checksums(bucket))
    checksum_filename = bucket.with_suffix(".sha256sum")
    assert not checksum_filename.exists()
    with open(checksum_filename, "w", encoding="utf-8") as fh:
        fh.write(checksum_text)

def cli():
    """CLI"""
    parser = argparse.ArgumentParser()
    parser.add_argument("bucket")
    args = parser.parse_args()
    bucket_checksum(args.bucket)

if __name__ == "__main__":
    cli()
