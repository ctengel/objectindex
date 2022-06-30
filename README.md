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

## Interim infrastructure

Hardware and such:

- Raspberry Pi 3B, 3B+, 400
- External USB hard drive with SMR
- ext4 format
  - strongly considering xfs
- standalone/non erasure
- 32GB mini SDHC

### Steps

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
   - etc
3. `/etc/dhcpcd.conf`

        interface eth0
        static ip_address=192.168.1.254/24
        static routers=192.168.1.1
        static domain_name_servers=192.168.1.1

4. `sudo apt update; sudo apt upgrade`
5. `sudo parted`

		Model: Seagate BUP Portable (scsi)
		Disk /dev/sda: 5001GB
		Sector size (logical/physical): 512B/4096B
		Partition Table: gpt
		Disk Flags: 

		Number  Start   End     Size    File system  Name      Flags
		 1      1049kB  5001GB  5001GB  ext4         obj1data

6. `sudo mkfs.ext4 /dev/sda1`
7. `sudo mkdir /mnt/obj1data`
8. `/etc/fstab`: `PARTUUID= /mnt/obj1data ext4 defaults,noatime 0 2`
9. `sudo useradd -mU minio`
10. `sudo chown minio:minio /mnt/obj1data`
11. `sudo apt install screen`

#### As minio user
1. `wget https://dl.min.io/server/minio/release/linux-arm64/minio`
2. `wget https://dl.min.io/server/mc/release/linux-arm64/mc`
3. `chmod a+x minio mc`
4. `MINIO_ROOT_USER=minio MINIO_ROOT_PASSWORD=password /home/minio/minio server /mnt/obj1data --address 0.0.0.0:9000 --console-address 0.0.0.0:9001`

### Postgres

Some info on getting PostgreSQL running on Fedora:

- https://developer.fedoraproject.org/tech/database/postgresql/about.html
  - https://docs.fedoraproject.org/en-US/quick-docs/postgresql/
  - `/usr/share/doc/postgresql/README.rpm-dist`

```
sudo dnf install postgresql-server
sudo postgresql-setup --initdb
sudo systemctl start postgresql
sudo su -c "createuser USER" postgres
sudo su -c "createdb -O USER DB" postgres
OBJIDX_SETTINGS=../samp.cfg python3 -m obj_idx.db_create
pg_dump --schema-only DB > schema.sql
```

The `db_create.py` script will empty a database and create tables in the schema, and uses the same config file as the web app.

## Config file

```
DEBUG = True
SQLALCHEMY_DATABASE_URI = 'postgresql:///objidx'
SQLALCHEMY_TRACK_MODIFICATIONS = False
OBJIDX_S3 = 'http://user:pass@localhost:9000/'
OBJIDX_BUCKETS = ['bucket1']
```

- `OBJIDX_S3` is a special URL for S3
- `OBJIDX_BUCKETS` is a list of buckets that may be used.
- The rest are standard Flask and sqlalchemy options
