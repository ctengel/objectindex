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

### Steps to get MinIO running

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

#### As minio user
1. `wget https://dl.min.io/server/minio/release/linux-arm64/minio`
   - alternatively `GO111MODULE=on go install github.com/minio/minio@latest` which will compile and install to `~/go/bin/minio`
   - see the [official minio docs](https://min.io/docs/minio/linux/) for more
2. `wget https://dl.min.io/server/mc/release/linux-arm64/mc`
3. `chmod a+x minio mc`
4. `MINIO_ROOT_USER=minio MINIO_ROOT_PASSWORD=password /home/minio/minio server /mnt/obj1data --address 0.0.0.0:9000 --console-address 0.0.0.0:9001`
   - can be done as a script like `./start.sh` and run in a screen session
5. actually setup buckets, users, replication, etc
   - `./mc alias set xyz http://0.0.0.0:9000 minio password`
     - for more info see the [mc docs](https://min.io/docs/minio/linux/reference/minio-mc/mc-alias-set.html)
   - `./mc admin info minio`
   - `./mc admin user add minio user password`
   - `./mc mb minio/bucket`
   - grant access from user to bucket
   - `./mc update && ./mc admin update xyz/`

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
