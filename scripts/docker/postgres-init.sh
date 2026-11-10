#!/bin/sh
# The studio's database and its two accounts, as on the studio PC (docs/database.md): scene_owner owns the tables (the
# migrations use it), scene_app only reads and writes rows (the app). Run once by the postgres image on a new volume.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<SQL
CREATE ROLE scene_owner LOGIN PASSWORD '${SCENE_OWNER_PASSWORD}';
CREATE ROLE scene_app LOGIN PASSWORD '${SCENE_APP_PASSWORD}';
CREATE DATABASE scene OWNER scene_owner;
\connect scene
ALTER SCHEMA public OWNER TO scene_owner;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
SQL
