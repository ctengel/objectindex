#!/bin/bash

mypath=$(dirname "$0")
bucket="$1"
lpm="$2"
archive="$3"
shift
shift
shift

for url in "$@"; do
	echo yt-dlp --restrict-filenames --write-info-json --download-archive "$archive" "$url"
	echo "$mypath/yt.py" -b "$bucket" -l "$lpm" *.info.json
	echo obj-idx-client --rm *.mp4
done
