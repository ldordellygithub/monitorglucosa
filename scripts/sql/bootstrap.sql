-- Bootstrap SQL idempotente para monitorglucosa (ADR 0007, Requisito 5.3).
-- Un único bloque DO $$ ... $$ para compatibilidad con RDS Data API (una sola sentencia).
-- Se ejecuta como el usuario maestro de Aurora (no superusuario, con CREATEROLE y miembro
-- de rds_iam con ADMIN OPTION) o como `mg_admin` en local/CI.
-- Nunca crea tablas de negocio ni toca datos.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mg_migrator') THEN
        CREATE ROLE mg_migrator WITH LOGIN;
    ELSE
        ALTER ROLE mg_migrator WITH LOGIN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mg_api') THEN
        CREATE ROLE mg_api WITH LOGIN;
    ELSE
        ALTER ROLE mg_api WITH LOGIN;
    END IF;

    -- Autenticación IAM de RDS/Aurora (en local existe el rol ficticio rds_iam).
    GRANT rds_iam TO mg_migrator;
    GRANT rds_iam TO mg_api;

    -- En PostgreSQL 16 un no-superusuario con CREATEROLE necesita membresía en mg_migrator
    -- para transferirle la propiedad del esquema y fijar sus privilegios por defecto.
    EXECUTE format('GRANT mg_migrator TO %I', current_user);

    CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION mg_migrator;
    ALTER SCHEMA app OWNER TO mg_migrator;

    -- Endurecer el esquema public y acotar el acceso a app.
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;
    REVOKE ALL ON SCHEMA app FROM PUBLIC;
    GRANT USAGE ON SCHEMA app TO mg_api;

    -- Garantizar que mg_api solo tenga DML sobre tablas y secuencias creadas por mg_migrator.
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO mg_api;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO mg_api;

    ALTER DEFAULT PRIVILEGES FOR ROLE mg_migrator IN SCHEMA app
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mg_api;
    ALTER DEFAULT PRIVILEGES FOR ROLE mg_migrator IN SCHEMA app
        GRANT USAGE, SELECT ON SEQUENCES TO mg_api;

    -- Fijar search_path en app para ambos roles (sin depender de public).
    ALTER ROLE mg_migrator SET search_path = app;
    ALTER ROLE mg_api SET search_path = app;
END
$$;
