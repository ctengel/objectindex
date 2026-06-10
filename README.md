# objectindex
Index your objects

The purpose of this project is to allow using cheap Single Board Computers with
one or two cheap HDDs each to store important data. No RAID, it only works well
with expensive disks and still has a single point of failure in the controller,
and is difficult to recover. No NAS/NFS; doing a cluster is too difficult.
HTTP-based object store is the way to go.

The goal is *not* to try to replicate POSIX/NFS but to store WORM large files
with basic metadata in a way that is **better** than a POSIX filesystem.

Inspired by projects like:

- [NODE Mini Server](https://n-o-d-e.net/node_mini_server.html)
- [WD PiDrive Node Zero](https://magpi.raspberrypi.com/articles/wd-pidrive-node-zero-review)

Consume S3 API(s) (from MinIO or the like) and expose a rich metadata store.

## Setup and usage

`pip3 install https://github.com/ctengel/objectindex/archive/refs/heads/main.zip`

There are then a few different ways to use this:
- RESTful API (FastAPI): `uvicorn obj_idx.api:app --host=0.0.0.0 --port 29161` (configured via `OBJIDX_*` env vars, see below)
  - need simpler-objects running
  - need postgres running and setup
    - see `python3 -m obj_idx.db_create` (with the same `OBJIDX_*` env vars set)
  - interactive API docs at `/docs`
- GUI: `FLASK_APP=obj_idx.gui OBJIDX_GUI_SETTINGS=/path/to/gui.cfg flask run --port 29159 --host=0.0.0.0`
  - need GUI config file (see below)
- CLI client: `obj-idx-client`


## Upgrading to 0.3.0 (Flask → FastAPI)

The flagship change in 0.3.0 is that the **REST API is now FastAPI** (served by
uvicorn) instead of Flask‑RESTX. The **database schema is 100% unchanged** and
the **GUI and CLI are unchanged**. Most of the REST contract is identical; the
differences are limited to error responses and a few stricter validations,
called out under "For API consumers" below.

### For operators

- **No database migration.** The Postgres schema (tables, columns, indexes, the
  `bytea` `checksum`) is byte‑for‑byte identical. Point 0.3.0 at your existing
  database as‑is — no `db_create`, no `ALTER` required.
- **New/changed dependencies.** `flask-restx`, `flask-sqlalchemy` and the
  `sqlalchemy < 2` pin are gone; the API now uses `fastapi`, `uvicorn`,
  `pydantic-settings`, `sqlmodel` and `sqlalchemy 2.0`. Reinstall the package
  (`pip install -e .`) to pull them. (Flask itself is still a dependency — the
  GUI is still Flask.)
- **Invocation changed (WSGI → ASGI).** Start the API with
  `uvicorn obj_idx.api:app --host 0.0.0.0 --port 29161`. Update any
  systemd unit / process manager that previously launched the Flask app.
- **Configuration moved from a file to environment variables.** Earlier
  releases used a Flask `.cfg` Python file referenced by `OBJIDX_SETTINGS`; the
  API no longer reads it. Configuration is now environment variables (or a
  `.env` file), all prefixed `OBJIDX_`:

  | Old `.cfg` key | New env var | Notes |
  |----------------|-------------|-------|
  | `SQLALCHEMY_DATABASE_URI` | `OBJIDX_DATABASE_URL` | include the driver, e.g. `postgresql+psycopg2:///objidx` |
  | `OBJIDX_S3` | `OBJIDX_S3` | unchanged meaning |
  | `OBJIDX_BUCKETS` | `OBJIDX_BUCKETS` | **now comma‑separated** (`bucket1,bucket2`), not a Python/JSON list |

  The old Flask‑only keys `DEBUG` and `SQLALCHEMY_TRACK_MODIFICATIONS` are
  obsolete and can be dropped. See `sample.env` and the
  [API config section](#api) below.
- **The GUI is unchanged.** It is still Flask and still configured via
  `OBJIDX_GUI_SETTINGS` pointing at a `.cfg` file (`OBJIDX_URL`, `OBJIDX_AUTH`).
- **Interactive API docs** are now the OpenAPI UI at `/docs` (raw spec at
  `/openapi.json`); the old Flask‑RESTX Swagger page is gone.
- **Default ports** Now 29161 (API) and 29159 (GUI)

### For API consumers

The wire contract is **mostly identical** — same routes and methods, same
request bodies, same success response shapes (`checksum` is still a lowercase
hex string; a `File` embeds the full `file_object`, an `Object` embeds brief
`files` of `{uuid, url}`), and `POST /upload/` still returns **201**. The upload
state machine and SHA‑256 dedup are unchanged.

The differences are in **error responses** (mostly turning previous `500`
crashes into proper `4xx`) and a couple of **stricter validations**:

| Endpoint / case | 0.2.x (Flask) | 0.3.0 (FastAPI) |
|---|---|---|
| Unknown bucket on `POST /upload/` | `400`, body `{message, bucket}` (recently `500`) | **`404`**, body `{detail}` |
| Same checksum, different `obj_size` | `500` | **`409`** `{message, object_uuid}` |
| Reupload of a permanently‑deleted object | `500` | **`409`** `{message, object_uuid}` |
| Existing file, different `direct`/`partial` | `500` | **`409`** `{message, file_uuid, object_uuid}` |
| Upload may be in progress | `409` `{message, object_uuid}` | **`409`** (unchanged) |
| Non‑hex `checksum` (`/upload/`, `/object/`) | `500` | **`400`** `{detail}` |
| Missing required body field | `500` | **`422`** |
| Missing `filename` on `/upload/` | `500` | **`422`** (now explicitly required) |
| `GET /file/` with neither `url` nor `extra` | `500` | **`400`** `{detail}` |
| Malformed UUID in a path | `500` | **`422`** |
| `GET /object/{uuid}/download`, object deleted | `200` (returned a URL) | **`410`** |
| `GET /object/{uuid}/download`, upload not finished | `200` (returned a URL) | **`503`** |
| `PUT /object/{uuid}/` with both `completed` + `deleted` | `500` | **`400`** `{detail}` |

Notes for client authors:

- **Error body shape.** Validation and most errors use FastAPI's standard
  `{"detail": ...}`. The `POST /upload/` conflict (`409`) responses keep the
  historical flat shape `{"message", "object_uuid"}` (plus `file_uuid` for the
  direct/partial case), so existing clients that read `object_uuid` on a 409
  keep working.
- **Behavioral changes most likely to bite:** if your client treats unknown
  bucket as `400` or reads the `bucket` field, switch to `404` / `detail`; and
  if it assumes `…/download` always returns a URL, handle `410` (deleted) and
  `503` (in progress).
- **Everything else** simply converts a former `500` into a precise `4xx`/`422`,
  so a well‑behaved client that never triggered those crashes is unaffected.


## Interim infrastructure

Hardware and such:

- Raspberry Pi 3B, 3B+, 400
  - starting specifically with 3B+
  - tuning may be needed for Pis older than 4/400
- External USB hard drive with SMR
  - note that HDDs like this don't play well with having additional USB devices plugged in like an SSD; if you want to do this you will need to have an extra power source like a USB hub
- ext4 format
  - strongly considering xfs
- standalone/non erasure
  - note that single node single drive MinIO has been deprecated in late 2022 - single drive erasure coding has been introduced so using that now
- 32GB mini SDHC
  - keep the swap here; putting on USB just overloads USB power/traffic

### Steps to get object storage running

#### On another machine
1. Download `2022-04-04-raspios-bullseye-arm64-lite.img.xz` or similar from https://www.raspberrypi.com/software/operating-systems/ 
2. `xzcat 2022-04-04-raspios-bullseye-arm64-lite.img.xz | sudo dd of=/dev/sda bs=4096`

#### On the pi
1. Boot
2. sudo raspi-config
   - ssh
   - hostname
   - disable autologin
   - locale
   - handle wifi killswitch?
   - etc
3. `/etc/dhcpcd.conf`

        interface eth0
        static ip_address=192.168.1.254/24
        static routers=192.168.1.1
        static domain_name_servers=192.168.1.1

4. `sudo apt update; sudo apt upgrade`
5. `sudo parted -a optimal /dev/sdX`

		$ sudo parted -a optimal /dev/sdX
		GNU Parted 3.4
		Using /dev/sdX
		Welcome to GNU Parted! Type 'help' to view a list of commands.
		(parted) help    
		...                                                         
		(parted) mklabel                                                          
		New disk label type? gpt
		Warning: The existing disk label on /dev/sdb will be destroyed and all data on this disk will be lost. Do you want to continue?
		Yes/No? y                                                                 
		(parted) mkpart                                                           
		Partition name?  []? ...
		File system type?  [ext2]? ext4                                           
		Start? 0%                                                                  
		End? 100%                                                                 
		(parted) print                                                            
		Model: ...
		Disk /dev/sdb: 2000GB
		Sector size (logical/physical): 512B/512B
		Partition Table: gpt
		Disk Flags: 

		Number  Start   End     Size    File system  Name          Flags
		 1      1049kB  2000GB  2000GB  ext4         ...

		(parted) quit   




		Model: Seagate BUP Portable (scsi)
		Disk /dev/sda: 5001GB
		Sector size (logical/physical): 512B/4096B
		Partition Table: gpt
		Disk Flags: 

		Number  Start   End     Size    File system  Name      Flags
		 1      1049kB  5001GB  5001GB  ext4         obj1data

6. `sudo mkfs.ext4 /dev/sda1`
7. `sudo mkdir /mnt/obj1data`
8. `sudo blkid -s PARTUUID /dev/sda1`
9. `/etc/fstab`: `PARTUUID= /mnt/obj1data ext4 defaults,noatime 0 2`
   - set noauto to prevent attempt to mount at boot, if swapping removable drives
10. `sudo useradd -mU minio`
   - alternatively `groupadd -g 1234 minio; useradd -m -u 1234 -g 1234 minio` may be used to set a certain UID/GID
   - `userdel -r minio` can be used to uninstall`
11. `sudo chown minio:minio /mnt/obj1data`
12. `sudo apt install screen`

We need to periodically monitor and tune hardware:
- `/usr/bin/vcgencmd measure_temp`
- see https://www.blackmoreops.com/2014/09/22/linux-kernel-panic-issue-fix-hung_task_timeout_secs-blocked-120-seconds-problem/
  - `echo 1440 | sudo tee /sys/block/sda/device/timeout`
  - `echo 720 | sudo tee /sys/block/sda/device/eh_timeout`
  - see `/etc/sysctl.d`
- check SMART for the disk `sudo smartctl -a /dev/sda`
- other articles -
  - https://unix.stackexchange.com/questions/541463/how-to-prevent-disk-i-o-timeouts-which-cause-disks-to-disconnect-and-data-corrup
  - https://www.snia.org/sites/default/files/SDC15_presentations/smr/HannesReinecke_Strategies_for_running_unmodified_FS_SMR.pdf
  - https://www.usenix.org/system/files/login/articles/login_summer17_03_aghayev.pdf
- `sudo shutdown -r now; exit`

#### Object Storage install

Install simpler objects (README there includes systemd and ansible instructions)

### Postgres

Some info on getting PostgreSQL running on Fedora:

- https://developer.fedoraproject.org/tech/database/postgresql/about.html
  - https://docs.fedoraproject.org/en-US/quick-docs/postgresql/
  - `/usr/share/doc/postgresql/README.rpm-dist`

Initial steps to be performed as a sudoer:
```
sudo dnf install postgresql-server
sudo postgresql-setup --initdb
sudo systemctl start postgresql
sudo su -c "createuser -P USER" postgres  # note you will be prompted to create a password
sudo su -c "createdb -O USER DB" postgres
```

Note also that modifying `/var/lib/pgsql/data/pg_hba.conf` to include `scram-sha-256` instead of `ident` etc may be needed.

Following steps to be run as user who will run the API.
```
OBJIDX_DATABASE_URL=postgresql+psycopg2:///DB OBJIDX_S3=... OBJIDX_BUCKETS=bucket1 python3 -m obj_idx.db_create
pg_dump --schema-only DB > schema.sql
```

The `db_create.py` script will empty a database and create tables in the schema, and uses the same `OBJIDX_*` environment configuration as the API.

#### Moving/deleting buckets

Moving

```
update object set bucket='new' where bucket='old';
```

Deleting

```
delete from file using object where file.obj_uuid=object.uuid and object.bucket='old';
objidx1d=> delete from object where bucket='old';
```

## Config files


### API

The API (FastAPI) is configured by environment variables, all prefixed
`OBJIDX_` (a `.env` file in the working directory is also read). See
`sample.env`:

```
OBJIDX_DATABASE_URL=postgresql+psycopg2:///objidx
OBJIDX_S3=http://localhost:29164/
OBJIDX_BUCKETS=bucket1
```

- `OBJIDX_DATABASE_URL` is the SQLAlchemy database URL (include the driver).
- `OBJIDX_S3` is the URL for Simpler Objects Locator.
- `OBJIDX_BUCKETS` is a comma-separated list of buckets that may be used
  (e.g. `bucket1,bucket2`).

Previous releases used a Flask `.cfg` file referenced by `OBJIDX_SETTINGS`;
the API no longer uses it (the GUI still does — see below).

### GUI

```
DEBUG = True
OBJIDX_URL="http://127.0.0.1:29161/"  # change if running on a different host
OBJIDX_AUTH="user"  # currently just username as no auth yet at API level, ideally pass thru in fut
```

## Testing

The API has a black-box contract test suite under `tests/`. It drives the
FastAPI app in-process via Starlette's `TestClient` (no server process) and pins
the REST wire contract.

The tests still need a real PostgreSQL (the suite relies on JSONB, `bytea` and
`LIKE`-escaping, which SQLite can't reproduce — `TestClient` only replaces the
HTTP transport, not the database). Point `TEST_DATABASE_URL` at any database you
can create/drop tables in — the suite recreates the two tables before every test:

```bash
pip install -e '.[test]'
TEST_DATABASE_URL=postgresql+psycopg2:///objidx_test python3 -m pytest tests/
```

### Spinning up a throwaway PostgreSQL

If you don't already have a database handy, you can run a disposable one from a
local data directory without touching any system service:

```bash
# 1. Initialize a fresh data dir (trust auth, your OS user as superuser)
initdb -D "$PWD/pgdata" -U "$USER" --auth=trust

# 2. Start it with a socket in /tmp (avoids needing /var/run/postgresql)
pg_ctl -D "$PWD/pgdata" -o "-k /tmp -p 5432" -l "$PWD/pgdata/pg.log" start

# 3. Create the test database
createdb -h /tmp -U "$USER" objidx_test

# 4. Run the suite against it
TEST_DATABASE_URL="postgresql+psycopg2://$USER@/objidx_test?host=/tmp" python3 -m pytest tests/

# Tear down when done
pg_ctl -D "$PWD/pgdata" stop && rm -rf "$PWD/pgdata"
```

(Add `pgdata/` to your local ignores, or put it outside the repo, so the data
directory isn't accidentally committed.)

## Issues

### Failed upload

Failed upload must be first cleared by PUT/PATCHing the object `/object/<object-uuid>/` with `{"deleted": true}` to signify that upload has stopped. `obj-idx-client scrub --clear <bucket>` automates this for every failed upload it finds (bytes absent, or present but never registered); uploads still in progress (HEAD 503) are skipped and need an object-store scrub first.

Essentially, the lifecycle state machine of an object looks something like this:
1. Initial POST upload - new status (completed: false; deleted: false) - assumed upload to object store to initiate shortly - subsequent upload attempts will fail
2. Successful object upload
3. PUT object completed=True signifying completion - normal status (completed: true, deleted: false)

The initial client may retry step 2 as many times as needed; however to start from scratch the object needs to be put in "retry" mode (completed: false, deleted: true) as described above.

Finally, once an object is in normal state, the object may be noted as permenantly deleted intentionally (i.e. so no option/desire for retry) by putting it in deleted state (completed: true, deleted: true) - putting it in this state doesn't actually delete it from object store though.

### slow json lookups

`GET /file/?extra=ytdl-id=...` does a JSONB lookup on `extra->>'ytdl-id'`, which
is **not** indexed by default — `db_create` deliberately omits it, because the
expression index only pays off for deployments dominated by `ytdl-id` files and
is wasted space otherwise.

If many of your files carry a `ytdl-id`, an operator can add the index at any
time (initial deployment or later, on a live table). The simple form is in
`scripts/schema-79.sql`:

```
psql -d objidx -f scripts/schema-79.sql
```

If you also store a significant number of *non*-ytdl files, prefer a **partial**
index so it only covers rows that actually have a `ytdl-id` — smaller and
cheaper to maintain. Equality lookups (`extra->>'ytdl-id' = '...'`) imply
`NOT NULL`, so the planner still uses it:

```sql
CREATE INDEX CONCURRENTLY ix_file_extra_ytdl_id
    ON file ((extra ->> 'ytdl-id'))
    WHERE (extra ->> 'ytdl-id') IS NOT NULL;
```

(`CONCURRENTLY` avoids blocking writes while the index builds on a live table;
it cannot run inside a transaction block.)
