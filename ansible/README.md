# Ansible deploy for the ObjectIndex API

Installs and runs the ObjectIndex FastAPI API as a **rootless systemd user
service**. Ansible is the only supported deploy path. The playbook never
escalates (`become = False`); the root-level prerequisites below are *asserted*
by the role, not performed.

This deploy does **not** set up PostgreSQL. The connection string is a parameter
(`objidx_database_url`), and the role actively verifies the database is
reachable (a real `SELECT 1`) before starting the service.

> The GUI and any scheduled/cron jobs are intentionally out of scope for now.

## Prerequisites (root, done once out of band)

These are OS-level concerns an administrator handles before the first run; the
role only checks they are in place:

1. **OS packages** — a Python 3 interpreter with the `venv` module, plus
   `python3-packaging` (used by Ansible's pip module):
   - Fedora: `dnf install -y python3 python3-packaging`
   - Debian/Ubuntu: `apt install -y python3 python3-venv python3-packaging`
2. **A service user** to own the venv, config, and unit (e.g. `objectindex`);
   set it as `ansible_user` in inventory.
3. **Linger**, so the user's units run without an active login session:
   `loginctl enable-linger objectindex`.
4. **A reachable PostgreSQL database** — create the database/role and use its
   SQLAlchemy URL as `objidx_database_url`.
5. **An initialized schema.** This deploy does **not** create or migrate the
   schema; it only verifies the `object`/`file` tables exist and fails if they
   don't. On a brand-new empty database, create them once:
   ```bash
   OBJIDX_DATABASE_URL=... OBJIDX_S3=... OBJIDX_BUCKETS=... \
     ~/venv/bin/python -m obj_idx.db_create
   ```
   **Warning:** `db_create` is **destructive** — it drops all tables first. Run
   it only against an empty database; for an existing schema, leave it alone.
6. **A running simpler-objects server** reachable at `objidx_s3` (`OBJIDX_S3`) —
   the API proxies all uploads/downloads to it. The role probes its `/health`
   endpoint and fails if it is down.

## What it does

A single role, `objectindex_api`, run by `site.yml` against the
`objectindex_api` inventory group:

1. Asserts the root prereqs are in place (python3 + venv + packaging, linger).
2. Asserts `objidx_database_url` is set.
3. Builds/repairs a Python venv in `~/venv` and installs ObjectIndex from the
   `objectindex_version` git tag tarball.
4. Verifies the Postgres DB is reachable via the venv's sqlalchemy/psycopg2.
5. Verifies the schema (the `object`/`file` tables) exists — fails with a clear
   message if missing. It never creates or migrates the schema.
6. Verifies the simpler-objects backend is reachable (`GET /health`).
7. Renders `~/.config/objectindex/api.env` (mode 0600).
8. Installs the `objectindex-api.service` user unit and enables/starts it.

## Usage

```bash
cp inventory/hosts.example.yml inventory/hosts.yml
$EDITOR inventory/hosts.yml        # set objidx_database_url / objidx_s3 / objidx_buckets

ansible-lint                        # optional
ansible-playbook site.yml --syntax-check
ansible-playbook site.yml --check   # dry run
ansible-playbook site.yml           # deploy
```

Verify on the host:
```bash
systemctl --user status objectindex-api
curl http://localhost:29161/docs
```

## Upgrading

Bump `objectindex_version` in the inventory and re-run `ansible-playbook
site.yml`. pip reinstalls at the new tag and notifies the restart handler; every
other task is a no-op when nothing changed.

## Configuration

| Inventory var          | Required | Maps to / purpose                                  |
|------------------------|----------|----------------------------------------------------|
| `objidx_database_url`  | yes      | `OBJIDX_DATABASE_URL` (SQLAlchemy URL of an existing Postgres DB) |
| `objidx_s3`            | yes      | `OBJIDX_S3` (base URL of the simpler-objects server) |
| `objidx_buckets`       | yes      | `OBJIDX_BUCKETS` (YAML list; joined to a comma list) |
| `objectindex_version`  | no       | git tag to install (default in role defaults)      |
| `objectindex_host`     | no       | uvicorn bind host (default `0.0.0.0`)              |
| `objectindex_port`     | no       | uvicorn port (default `29161`)                     |
| `objectindex_workers`  | no       | uvicorn worker count (default `1`)                 |
| `ansible_user`         | yes      | the unprivileged service user to deploy as         |
