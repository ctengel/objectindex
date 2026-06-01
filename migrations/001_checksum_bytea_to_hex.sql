-- Migration 001: store object.checksum as lowercase hex text instead of bytea.
--
-- Earlier releases stored the SHA-256 checksum as a 32-byte bytea. The SQLModel
-- build stores it as the 64-char lowercase hex string (varchar(64)), which is
-- what the API has always exposed on the wire, so no client change is needed.
--
-- Run once against an existing database, e.g.:
--   psql "$DATABASE" -f migrations/001_checksum_bytea_to_hex.sql
-- Take a backup first. This rewrites the object table and its checksum index.

BEGIN;

ALTER TABLE object ADD COLUMN checksum_hex varchar(64);
UPDATE object SET checksum_hex = encode(checksum, 'hex');

DROP INDEX IF EXISTS ix_object_checksum;
ALTER TABLE object DROP COLUMN checksum;
ALTER TABLE object RENAME COLUMN checksum_hex TO checksum;
CREATE INDEX ix_object_checksum ON object USING btree (checksum);

COMMIT;
