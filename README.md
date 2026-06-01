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
- RESTful API (FastAPI): `uvicorn obj_idx.api:app --host=0.0.0.0` (configured via `OBJIDX_*` env vars, see below)
  - need simpler-objects running
  - need postgres running and setup
    - see `python3 -m obj_idx.db_create` (with the same `OBJIDX_*` env vars set)
  - interactive API docs at `/docs`
- GUI: `FLASK_APP=obj_idx.gui OBJIDX_GUI_SETTINGS=/path/to/gui.cfg flask run --port 5001 --host=0.0.0.0`
  - need GUI config file (see below)
- CLI client: `obj-idx-client`


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

Install simpler objects

#### systemd example

`$ systemctl list-units | grep '/path/to/objectstore' | awk '{ print $1 }'`

`/etc/systemd/system/minio.service`:

```
[Unit]
Description=MinIO Object Storage Service
After=network-online.target objectstoremountpoint.mount

[Service]
ExecStart=/home/minio/start.sh
WorkingDirectory=/home/minio
User=minio
Group=minio

[Install]
WantedBy=multi-user.target
```

```
$ sudo systemctl start minio
$ sudo systemctl status minio
$ sudo systemctl enable minio
```

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
OBJIDX_DATABASE_URL=postgresql+psycopg2:///DB OBJIDX_S3=... OBJIDX_BUCKETS='["bucket1"]' python3 -m obj_idx.db_create
pg_dump --schema-only DB > schema.sql
```

The `db_create.py` script will empty a database and create tables in the schema, and uses the same `OBJIDX_*` environment configuration as the API.

#### Migrations

Schema changes ship as plain SQL files under `migrations/`, applied once with
`psql` (take a backup first):

```
psql "$DATABASE" -f migrations/001_checksum_bytea_to_hex.sql
```

`001_checksum_bytea_to_hex.sql` converts `object.checksum` from `bytea` to the
64-char lowercase hex `varchar(64)` used by the SQLModel build (the API already
exposed the checksum as hex, so clients are unaffected).

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
OBJIDX_S3=http://user:pass@localhost:9000/
OBJIDX_BUCKETS=["bucket1"]
```

- `OBJIDX_DATABASE_URL` is the SQLAlchemy database URL (include the driver).
- `OBJIDX_S3` is a special URL for S3.
- `OBJIDX_BUCKETS` is a JSON list of buckets that may be used.

Previous releases used a Flask `.cfg` file referenced by `OBJIDX_SETTINGS`;
the API no longer uses it (the GUI still does — see below).

### GUI

```
DEBUG = True
OBJIDX_URL="http://127.0.0.1:5000/"  # change if running on a different host
OBJIDX_AUTH="user"  # currently just username as no auth yet at API level, ideally pass thru in fut
```

## Testing

The API has a black-box contract test suite under `tests/`. It exercises the
FastAPI app (now backed by SQLModel) over HTTP and pins the REST wire contract.
(The frozen legacy Flask app in `tests/oilegacy/` is kept for reference, but the
cross-check is disabled on this branch because the checksum column changed from
`bytea` to hex text; drop-in parity was already proven on the SQLAlchemy branch.)

The tests need a real PostgreSQL (the suite relies on JSONB and `LIKE`-escaping,
which SQLite can't reproduce). Point `TEST_DATABASE_URL` at any database you can
create/drop tables in — the suite recreates the two tables before every test:

```bash
pip install -e '.[test]'
TEST_DATABASE_URL=postgresql+psycopg2:///objidx_test python3 -m pytest tests/
```

Use `-k fastapi` (or `-k flask`) to run a single implementation.

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

Failed upload must be first cleared by PUT/PATCHing the object `/object/<object-uuid>/` with `{"deleted": true}` to signify that upload has stopped.

Essentially, the lifecycle state machine of an object looks something like this:
1. Initial POST upload - new status (completed: false; deleted: false) - assumed upload to object store to initiate shortly - subsequent upload attempts will fail
2. Successful object upload
3. PUT object completed=True signifying completion - normal status (completed: true, deleted: false)

The initial client may retry step 2 as many times as needed; however to start from scratch the object needs to be put in "retry" mode (completed: false, deleted: true) as described above.

Finally, once an object is in normal state, the object may be noted as permenantly deleted intentionally (i.e. so no option/desire for retry) by putting it in deleted state (completed: true, deleted: true) - putting it in this state doesn't actually delete it from object store though.

### slow json lookups

Add an index! See schema-79.sql