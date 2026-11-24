# Implementation Plan

Reglas de esta spec: un commit por tarea de primer nivel, con el trailer `Refs: fase-1a#<tarea>`. Las pruebas llevan
`@pytest.mark.req("fase-1a:N.M")` y la matriz `docs/traceability.md` se regenera con `kspec trace` en cada tarea que
añade pruebas. Los criterios que no se pueden automatizar se anotan en `manual-checks.md` (tarea 23). Los pasos
manuales del propietario (cuenta de AWS, parámetro del correo, primer `apply` local, aprobación de `prod`) están en el
runbook del diseño, no son tareas de código.

## Decisiones de arquitectura

- [x] 1. Registrar el ADR 0006: migraciones con una Lambda `migrator` dentro de la VPC (D2)
  - `kspec adr new "Database migrations with an in-VPC migrator Lambda"`; contexto, decisión, alternativas y
    consecuencias del diseño; estado Aceptado; añadirlo al índice de decisiones de `structure.md` y regenerar las copias
    con `kspec steering-sync --target cursor` y `--target claude`.
  - _Requirements: 7.4_
- [x] 2. Registrar el ADR 0007: bootstrap SQL idempotente por RDS Data API (D3)
  - Incluir la verificación bloqueante de que Data API acepta el secreto gestionado por RDS y la precisión del alcance
    del ADR 0004.
  - _Requirements: 5.3, 7.4_
- [x] 3. Registrar el ADR 0008: rol de despliegue con *permissions boundary* y pipeline público sin fugas (D4)
  - Incluir la lista de excepciones de NFR-4 y las medidas contra la exposición en los logs públicos de Actions.
  - _Requirements: 7.2, NFR-4, NFR-5_
- [x] 4. Registrar el ADR 0009: reanudación de Aurora con 503 reintentable dentro del límite de 30 s (D7)
  - Corregir la referencia rota del ADR 0005 a la documentación de Lambda Web Adapter si sigue devolviendo 404.
  - _Requirements: 2.2, 5.4, NFR-2_

## Backend

- [x] 5. Crear el proyecto `backend/` con las capas y las comprobaciones de calidad
  - `pyproject.toml` y `uv.lock` (Python 3.13, `exclude-newer` de 14 días), `src/{domain,application,infrastructure,api}`,
    `main.py`, `config.py`, pytest con el marcador `req` y cobertura, ruff, mypy estricto y los contratos de import-linter
    de `structure.md`. Hooks `mypy` y `pytest` en pre-push (`.pre-commit-config.yaml`) y reglas nuevas de `.gitignore`.
  - Subtarea de prueba de arquitectura: una importación prohibida (p. ej. `api` importando `infrastructure`) hace fallar
    `lint-imports`.
  - _Requirements: 2.5, NFR-1_
- [x] 6. Implementar `config.Settings` con validación por entorno
  - Variables y reglas de «Data Models»: `DATABASE_PASSWORD` y `LOCAL_*` prohibidas en `prod`, obligatorias en
    `local`/`test`; los errores nombran la variable sin su valor.
  - _Requirements: 1.4, 3.4_
  - [x] 6.1 Prueba basada en propiedades: la configuración de `prod` es cerrada
    - _Property: 5_
    - _Requirements: 1.4, 3.4_
- [x] 7. Implementar logs JSON, identificador de correlación y manejadores de errores
  - `JsonFormatter` con lista blanca, `RequestLogMiddleware` (ruta plantilla, `x-request-id` propio), `ErrorBody`,
    `ErrorDetail`, traducción de los tipos de error de Pydantic y manejadores de 422, 401, 404, 405, 503 y 500, sin el
    valor recibido.
  - _Requirements: 2.3, 2.4, NFR-5_
  - [x] 7.1 Prueba basada en propiedades: los errores no repiten lo recibido
    - _Property: 1_
    - _Requirements: 2.3_
  - [x] 7.2 Prueba basada en propiedades: los logs no contienen credenciales ni contenido
    - _Property: 4_
    - _Requirements: 2.4, NFR-5_
- [x] 8. Implementar la autenticación: puerto, dos adaptadores y `GET /api/v1/me`
  - `Identity`, `Authenticator`, `ApiGatewayClaimsAuthenticator`, `LocalJwksAuthenticator` (PyJWT), `current_identity`
    y el router `me`; selección por `ENVIRONMENT` en `create_app`. Ambos exigen `token_use = access`. Prueba de que, con
    `ENVIRONMENT = prod`, `create_app` nunca construye `LocalJwksAuthenticator` (la otra mitad de 3.4; `Settings` ya
    cubre la configuración). `ApiGatewayClaimsAuthenticator` lee `authorizer.jwt.claims` del propio JSON de
    `x-amzn-request-context`, sin clave `requestContext` envolvente.
  - `create_app` instancia `Settings` (el proceso se niega a arrancar si falla, 1.4) y cablea lo de la tarea 7:
    `RequestLogMiddleware`, `register_error_handlers` y el log JSON con el nivel de `LOG_LEVEL`, aplicado también a
    `uvicorn.error`: Starlette relanza las excepciones no controladas tras responder el 500 y uvicorn las registra con
    su mensaje. `JsonFormatter` descarta los mensajes, así que el error de `Settings` sale por stderr con la variable
    y sin su valor. Pruebas de punta a punta de `create_app`: un 422 y un 404 reales devuelven el cuerpo uniforme y
    `x-request-id`, escriben su línea de log, y `uvicorn.error` usa `JsonFormatter`. Se repite la prueba de la
    Property 4 con una ruta autenticada, para que los claims (`x-amzn-request-context`) tampoco aparezcan en el log.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - [x] 8.1 Prueba basada en propiedades: la autenticación en `prod` falla cerrada
    - _Property: 2_
    - _Requirements: 3.1, 3.2_
  - [x] 8.2 Prueba basada en propiedades: un token alterado nunca autentica en local
    - _Property: 3_
    - _Requirements: 3.3_
- [x] 9. Implementar `/health`, `/health/ready` y el acceso async a PostgreSQL
  - `DatabaseConfig` (clase de `infrastructure` que construye `main.py` desde `Settings`) y `create_engine` con asyncpg y `NullPool` (contraseña en local, token IAM firmado por boto3 en `prod`, TLS
    `verify-full` con el bundle de CA de RDS, `connect_timeout` de 20 s), `SqlDatabaseProbe`, `CheckReadiness` y el 503
    `DATABASE_UNAVAILABLE` con `Retry-After: 5`.
  - Pruebas de integración con PostgreSQL 16 real: `/health` responde 200 con la base de datos inaccesible;
    `/health/ready` responde 200 o 503.
  - _Requirements: 2.1, 2.2, 5.3, 5.4, NFR-2_
- [x] 10. Crear `bootstrap.sql`, la base de Alembic y la app del `migrator`
  - `scripts/sql/bootstrap.sql` como un único bloque `DO $$ … $$` idempotente (roles `mg_migrator` y `mg_api`, esquema
    `app`, privilegios por defecto), Alembic async con `version_table_schema = "app"`, revisión base vacía con
    `upgrade` y `downgrade`, y `create_migrator_app` (`POST /events`, `GET /`).
  - Pruebas de integración: `upgrade head` → `downgrade base` → `upgrade head`; `mg_api` no puede `CREATE TABLE` y
    `mg_migrator` sí.
  - _Requirements: 5.3, 7.1, 7.4_
  - [x] 10.1 Prueba basada en propiedades: el bootstrap SQL es idempotente (n ejecuciones como no superusuario)
    - _Property: 7_
    - _Requirements: 5.3_
- [x] 11. Construir y publicar el contrato OpenAPI y la referencia de la API
  - `api.openapi.build_openapi()`, `backend/tools/export_openapi.py [--check]`, `backend/openapi.json`,
    `docs/api/README.md`, desactivar `/docs`, `/redoc` y `/openapi.json` en `prod`, y las pruebas de contrato: validez
    OpenAPI 3.1, conformidad con los `openapi.yaml` de las specs y Schemathesis.
  - _Requirements: 2.3, 7.1, NFR-6_
  - [x] 11.1 Prueba basada en propiedades: la API cumple su contrato (Schemathesis y comparador)
    - _Property: 8_
    - _Requirements: 2.3, NFR-6_
- [x] 12. Crear la imagen, `compose.yaml`, el emisor JWT de pruebas y el arranque local
  - `backend/Dockerfile` (multi-etapa, LWA 1.1.0 por digest, CA de RDS, usuario sin privilegios, `CMD` de uvicorn con `--no-access-log`, `linux/amd64` con
    `--provenance=false --sbom=false`), `.dockerignore`, `compose.yaml` con healthchecks, `dev/postgres/init/`,
    `dev/jwt-issuer/` (proyecto uv propio con sus pruebas) y `.env.example`.
  - Pruebas de punta a punta contra Compose: `up --wait` y `/health`; la imagen responde con el `CMD` de Lambda; un
    `.env` ficticio no entra en la imagen; `GET /api/v1/me` con un token del emisor → 200 y con uno alterado → 401.
  - _Requirements: 1.1, 1.2, 1.3, 3.3_
- [x] 13. Checkpoint: ejecutar las pruebas del backend, `ruff`, `mypy`, `lint-imports` y `kspec trace`
  - Cobertura ≥ 80 % en `domain` y `application` con `pytest --cov` (el umbral solo actúa con esa opción); matriz generada sin pruebas huérfanas.

## Despliegue e infraestructura

- [x] 14. Implementar `deploy.py`, `db_bootstrap.py` y `smoke_test.py`
  - `Runner` inyectable; secuencia en dos fases con comprobación de `D_prev` en ECR, espera `function-active-v2`,
    migración, humo con reintentos (hasta 120 s, `Retry-After`) y vuelta atrás; enmascaramiento del ID de cuenta.
  - _Requirements: 7.4, 7.5, NFR-2_
  - [x] 14.1 Prueba basada en propiedades: nunca se sirve un digest sin sus migraciones
    - _Property: 6_
    - _Requirements: 7.4, 7.5_
- [x] 15. Crear la raíz de Terraform y el módulo `bootstrap`
  - Versiones fijadas (Terraform 1.16.6, proveedor AWS 6.69.1 en `us-east-1`), `default_tags`, backend S3 con `use_lockfile = true`,
    bucket del estado, proveedor OIDC, rol `monitorglucosa-deploy` con su política (`aws:RequestedRegion = us-east-1`, ADR 0008, ADR 0011) y el *permissions boundary*, y ECR
    (etiquetas inmutables, escaneo, 10 imágenes). `terraform test` con proveedores simulados.
  - _Requirements: 6.1, 7.2, 8.1, 8.2_
- [x] 16. Crear los módulos `network` y `database`
  - VPC en `us-east-1` (`us-east-1a` y `us-east-1b`) sin NAT ni IGW, endpoint gateway de S3, grupos de seguridad, Aurora PostgreSQL Serverless v2 (0–2 ACU, pausa de
    300 s, TLS forzado, IAM, Data API, backups de 7 días, protección contra borrado, contraseña gestionada por RDS).
  - _Requirements: 5.1, 5.2, 5.5_
- [x] 17. Crear el módulo `identity`
  - User pool Essentials en `us-east-1` con MFA TOTP, sin registro propio, clientes `web` (refresh de 1 día) y `collector` (30 días,
    rotación y `retry_grace_period_seconds`), dominio de prefijo y usuario propietario con correo de Parameter Store.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
- [x] 18. Crear los módulos `api` y `site`
  - Lambdas `api` y `migrator` por digest, HTTP API con autorizador JWT y ámbito `openid`, ruta IAM para
    `/health/ready`, throttling 10/20, CORS, logs de acceso, permisos con `source_arn`, y S3 + CloudFront con OAC, HSTS
    y CSP.
  - _Requirements: 4.5, 6.1, 6.2, 6.3, 6.4, 6.5_
- [x] 19. Crear el módulo `operations`
  - Tema SNS, las cuatro alarmas, presupuesto de US$20 con avisos al 80 % (US$16) y al 100 % (US$20) y retención de 30 días en los grupos de logs.
  - _Requirements: 8.3, 8.4, 8.5, NFR-3_
- [x] 20. Checkpoint: `terraform fmt -check`, `validate`, `terraform test` y checkov en verde

## Pipeline y documentación

- [x] 21. Crear `ci.yml` y añadir el check `ci` al ruleset
  - Jobs `changes`, `backend` (con `pytest --cov`), `compose`, `infra` y el resumen `ci`; acciones fijadas por SHA; semgrep, gitleaks,
    dependency review, comparación de `openapi.json` y checkov; editar `.github/rulesets/main.json` (se aplica con
    `kspec github apply`, con confirmación del propietario).
  - _Requirements: 7.1, NFR-4, NFR-5_
- [x] 22. Crear `deploy.yml`
  - Jobs `build` (sin AWS) y `deploy` (`environment: prod`, `concurrency`, OIDC) que ejecuta `scripts/deploy.py`. Depende
    de que `G-2` (revisor del entorno `prod`) esté resuelta en el kit.
  - _Requirements: 7.2, 7.3, 7.4, 7.5_
- [ ] 23. Documentar el runbook, los comandos reales y las verificaciones manuales
  - `docs/guia-de-desarrollo.md` (primer despliegue en `us-east-1`, avisos de Budgets al 80 % = US$16 y 100 % = US$20 con techo puntual de alerta de US$30/mes, Swagger UI en local), `tech.md · Comandos habituales`, NFR de
    latencia (≤ 60 s sumando reintentos) y flujo de despliegue con migraciones (con aprobación del propietario y
    `kspec steering-sync`), y `manual-checks.md` con los criterios no automatizables, incluidas las verificaciones
    del primer despliegue de los ADR 0007 (Data API), 0008 (log público) y 0011 (región `us-east-1` y factura del primer mes), y que el `requestId` real de API Gateway
    cumple `[A-Za-z0-9._=-]{1,128}` (si no, el `request_id` caería a un UUID y se perdería la correlación).
  - _Requirements: 4.2, 4.5, 5.3, 5.4, 6.3, 7.3, 8.3, 8.4, NFR-2, NFR-3, NFR-5, NFR-6_
- [ ] 24. Actualizar las vistas de arquitectura
  - Modelo `docs/architecture/diagrams.py` según «Architecture Views» (vistas 02, 03, 04, 08, 09, 10 y la nueva 13),
    `kspec diagrams export` y `kspec diagrams check` en verde.
  - _Requirements: 4.5, 5.1, 6.2, 7.5, 8.4_
- [ ] 25. Checkpoint final: todas las pruebas, `kspec lint`, `kspec trace check` y `kspec diagrams check` en verde
  - Todos los criterios con prueba etiquetada o verificación manual.

## Execution Order

Las tareas de una misma ola no dependen entre sí y pueden hacerse en paralelo.

| Ola | Tareas | Depende de |
| --- | --- | --- |
| 1 | 1, 2, 3, 4, 5, 15 | nada |
| 2 | 6, 7, 16, 17 | ola 1 (5 para 6 y 7; 15 para 16 y 17) |
| 3 | 8, 9 | ola 2 |
| 4 | 10, 11, 14 | ola 3 (14 usa el `bootstrap.sql` de la tarea 10, que va en la misma ola: se hace después de ella) |
| 5 | 12 | ola 4 |
| 6 | 13 | ola 5 |
| 7 | 18, 21 | olas 5 y 2 (la imagen y los módulos de red e identidad) |
| 8 | 19, 22 | ola 7 |
| 9 | 20, 23 | ola 8 |
| 10 | 24 | ola 9 |
| 11 | 25 | ola 10 |
