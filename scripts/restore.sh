#!/bin/sh
# Restore an ObjectIndex database from a backup produced by scripts/backup.py.
#
# Bootstrap restoral: this deliberately does NOT use ObjectIndex -- it fetches
# the gzipped SQL dump straight from simpler-objects (or a local file) and loads
# it into an EMPTY Postgres database. Needs only curl + postgresql-client.
# The plain dump carries the schema, so no obj_idx.db_create is required.
#
# Usage: restore.sh <s3-url-or-local-file> <target-db-url>
#   e.g. createdb objidx_restore
#        restore.sh http://host:9000/bucket1/<key>.sql.gz postgresql:///objidx_restore

set -eu

if [ $# -ne 2 ]; then
    echo "usage: $0 <s3-url-or-local-file> <target-db-url>" >&2
    exit 2
fi

SRC=$1
DB=$2

# Fetch and decompress as discrete steps (POSIX sh lacks `pipefail`, so a
# `curl | gunzip | psql` pipeline would mask a failed download -- psql would
# happily load empty input). `set -e` aborts on any step's nonzero exit, and
# ON_ERROR_STOP turns a mid-restore SQL error into a failure too.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

case "$SRC" in
    http://*|https://*) curl -fsSL "$SRC" -o "$TMP/dump.sql.gz" ;;  # -f: fail on HTTP error
    *) cp "$SRC" "$TMP/dump.sql.gz" ;;
esac

gunzip "$TMP/dump.sql.gz"
psql -v ON_ERROR_STOP=1 -d "$DB" -f "$TMP/dump.sql"
