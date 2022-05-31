#!/usr/bin/env python3
import os
import argparse
from obj_idx import s3lib
parser = argparse.ArgumentParser()
parser.add_argument('bucket')
parser.add_argument('filename')
args = parser.parse_args()
bucket = s3lib.get_s3_service_url(os.environ['OBJIDX']).Bucket(args.bucket)
bucket.upload_file(args.filename, args.filename)
