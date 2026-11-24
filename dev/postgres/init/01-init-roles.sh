#!/usr/bin/env bash
set -euo pipefail

# Inicialización de PostgreSQL 16 en local/Compose (ADR 0005, ADR 0007):
# 1. Como superusuario local: crea `rds_iam` (ficticio) y `mg_admin` (CREATEROLE, sin superusuario).
# 2. Como `mg_admin`: ejecuta el mismo `scripts/sql/bootstrap.sql` de producción y fija contraseñas locales.

: "${MG_ADMIN_PASSWORD:?MG_ADMIN_PASSWORD es obligatoria}"
: "${MG_MIGRATOR_PASSWORD:?MG_MIGRATOR_PASSWORD es obligatoria}"
: "${DATABASE_PASSWORD:?DATABASE_PASSWORD es obligatoria}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Creando rds_iam y mg_admin (no superusuario)..."
psql -v ON_ERROR_STOP=1 \
     -v admin_pass="$MG_ADMIN_PASSWORD" \
     -v target_db="$POSTGRES_DB" \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rds_iam') THEN
        CREATE ROLE rds_iam NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mg_admin') THEN
        CREATE ROLE mg_admin WITH LOGIN CREATEROLE;
    END IF;
    GRANT rds_iam TO mg_admin WITH ADMIN OPTION;
END
$$;
ALTER ROLE mg_admin WITH PASSWORD :'admin_pass';
ALTER DATABASE :"target_db" OWNER TO mg_admin;
SQL

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ejecutando scripts/sql/bootstrap.sql como mg_admin..."
PGPASSWORD="$MG_ADMIN_PASSWORD" psql -v ON_ERROR_STOP=1 \
     --username mg_admin \
     --dbname "$POSTGRES_DB" \
     -f /bootstrap/bootstrap.sql

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fijando contraseñas locales para mg_migrator y mg_api..."
PGPASSWORD="$MG_ADMIN_PASSWORD" psql -v ON_ERROR_STOP=1 \
     -v migrator_pass="$MG_MIGRATOR_PASSWORD" \
     -v api_pass="$DATABASE_PASSWORD" \
     --username mg_admin \
     --dbname "$POSTGRES_DB" <<'SQL'
ALTER ROLE mg_migrator WITH PASSWORD :'migrator_pass';
ALTER ROLE mg_api WITH PASSWORD :'api_pass';
SQL

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Inicialización de PostgreSQL completada."
