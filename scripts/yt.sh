#!/bin/bash

mypath=$(dirname "$0")
bucket="$1"
lpm="$2"
archive="$3"
shift
shift
shift

for url in "$@"; do
	yt-dlp --restrict-filenames --write-info-json --download-archive "$archive" "$url"
	"$mypath/yt.py" -b "$bucket" -l "$lpm" *.info.json
	obj-idx-client check --rm *.mp4
done
