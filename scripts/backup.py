#!/usr/bin/env python3

"""Back up the ObjectIndex database into ObjectIndex itself.

Runs ``pg_dump`` against the OI Postgres database, gzips the plain-SQL dump, and
uploads it as an object via the normal upload client. The simpler-objects URL of
the stored dump is printed on stdout -- feed it to ``scripts/restore.sh`` to
rebuild an empty database without going through OI (see issue #32).

Takes a native libpq database URL on the command line (e.g.
``postgresql:///objidx`` -- not the SQLAlchemy ``+psycopg2`` form) and needs the
client env vars (``OBJIDX_URL``/``OBJIDX_AUTH``).
"""

import argparse
import datetime
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

from obj_idx import client


def pg_dump_gz(db_url, dest_path):
    """Stream ``pg_dump <db_url> | gzip`` into ``dest_path``."""
    with open(dest_path, "wb") as out:
        dump = subprocess.Popen(["pg_dump", "--dbname", db_url],
                                stdout=subprocess.PIPE)
        gzip = subprocess.Popen(["gzip"], stdin=dump.stdout, stdout=out)
        dump.stdout.close()  # let pg_dump get SIGPIPE if gzip dies
        gzip.communicate()
        dump.wait()
    if dump.returncode:
        raise SystemExit(f"pg_dump failed (exit {dump.returncode})")
    if gzip.returncode:
        raise SystemExit(f"gzip failed (exit {gzip.returncode})")


def main():
    """Dump, upload, and print the simpler-objects URL."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-b", "--bucket", required=True,
                        help="bucket to store the dump in")
    parser.add_argument("db_url",
                        help="native libpq database URL to dump, "
                             "e.g. postgresql:///objidx")
    args = parser.parse_args()

    db_url = args.db_url
    dbname = urlsplit(db_url).path.lstrip("/") or "objidx"
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # NamedTemporaryFile gives the upload a sane ".sql.gz" key suffix.
    with tempfile.NamedTemporaryFile(prefix=f"{dbname}-{stamp}-",
                                     suffix=".sql.gz") as tmp:
        pg_dump_gz(db_url, tmp.name)
        backup_url = f"pgdump://{socket.gethostname()}/{dbname}/{stamp}.sql.gz"
        obj_idx = client.get_obj_idx_env()
        fileobj = client.upload_local(tmp.name, obj_idx, args.bucket,
                                      url=backup_url,
                                      extra={"backup": "objectindex",
                                             "created": stamp})
    if not fileobj:
        raise SystemExit("upload failed")
    print(f"backup file {fileobj.uuid}", file=sys.stderr)
    print(fileobj.get_s3_url())


if __name__ == "__main__":
    main()
