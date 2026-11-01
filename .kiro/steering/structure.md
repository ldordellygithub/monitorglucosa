---
inclusion: always
---

# Estructura y convenciones — monitorglucosa

> Estados: **Decidido** salvo que se marque *Propuesto*. Las propuestas se confirman en la primera
> spec o en un ADR. El repositorio aún no tiene código: el árbol de abajo es el **destino**, no el estado actual.

## Organización de carpetas

```text
monitorglucosa/
├── .python-version       # 3.13; uv la aplica a backend/ y collector/
├── .github/workflows/    # CI: lint, tipos, pruebas, semgrep, Docker, despliegue y prueba de humo
├── backend/              # API FastAPI con Clean Architecture
│   ├── pyproject.toml · uv.lock
│   ├── Dockerfile        # imagen única: local, CI y Lambda (ADR 0005)
│   ├── openapi.json      # contrato versionado; CI falla si difiere del generado
│   ├── src/
│   │   ├── main.py               # composition root: único punto que conecta las capas
│   │   ├── config.py             # configuración tipada (pydantic-settings); solo la lee main.py
│   │   ├── domain/               # entidades y reglas de negocio, sin frameworks
│   │   ├── application/          # casos de uso y puertos (interfaces)
│   │   ├── infrastructure/       # PostgreSQL, autenticadores, S3 y proveedor de AI
│   │   └── api/                  # routers FastAPI y esquemas de entrada/salida
│   └── tests/
│       ├── unit/                 # dominio y casos de uso
│       ├── integration/          # PostgreSQL real
│       └── architecture/         # reglas de dependencias
├── collector/            # colector BLE local; proyecto uv propio; sin imports del backend
│   ├── src/collector/
│   │   ├── main.py       # composition root del colector
│   │   ├── config.py     # configuración tipada (pydantic-settings)
│   │   ├── sync.py       # núcleo de la sesión de sincronización; solo depende de los puertos
│   │   ├── ports.py      # DeviceReader, ApiClient, TokenStore, Notifier
│   │   └── adapters/     # bleak (GD50), httpx, keyring, notificaciones de escritorio
│   └── tests/            # unit/ con fakes; contract/ contra backend/openapi.json
├── frontend/             # Next.js con exportación estática; TypeScript strict, Vitest y Playwright (flujo crítico)
│   └── Dockerfile · nginx.conf   # web compilada servida con nginx en local
├── mobile/               # fase 5: app Expo / React Native (TypeScript), cliente de la API (T-8)
├── dev/jwt-issuer/       # emisor JWT de pruebas, solo para el entorno local
├── scripts/smoke_test.py # prueba de humo tras cada despliegue
├── compose.yaml          # entorno local: API, PostgreSQL 16, web (nginx) y emisor JWT de pruebas
├── infra/terraform/      # módulos y un único estado remoto (prod): local y test no tienen recursos en AWS
├── docs/
│   ├── adr/              # NNNN-titulo-en-kebab-case.md, título en inglés
│   └── architecture/     # diagramas como código: modelo diagrams.py → .drawio, README y svg/ (kspec diagrams)
└── .kiro/                # steering, specs, hooks y tools/kiro_diagrams.py (librería de diagramas, la gestiona kspec)
```

- Cada componente tiene sus pruebas junto a él (`backend/tests/`, `collector/tests/`, `frontend/`), nunca dentro del código de producción.
- `backend/` y `collector/` son proyectos uv independientes, cada uno con su `pyproject.toml` y su lockfile. *(Decidido)*
- El colector, la web y la app móvil se comunican con el backend solo por HTTP. No hay imports entre ellos. El contrato compartido es el esquema OpenAPI que genera FastAPI, no código.

## Regla de dependencias

Clean Architecture: las reglas de dependencias se pueden verificar, a cambio de más código inicial que un script. Un import que viole esta tabla es un error de diseño.

| Módulo | Puede importar | Nunca importa |
| --- | --- | --- |
| `domain` | Biblioteca estándar | `application`, `infrastructure`, `api`, FastAPI, SQLAlchemy, SDK de AWS |
| `application` | `domain` | `infrastructure`, `api`, FastAPI, SQLAlchemy, bleak, SDK de AWS |
| `infrastructure` | `application`, `domain` | `api` |
| `api` | `application` (casos de uso, DTOs, puertos y errores) | `infrastructure`, `domain` |
| `main.py` (composition root) | Todas las capas | Es el único punto donde se conectan |
| `collector` | Biblioteca estándar, `bleak`, cliente HTTP, almacén seguro del SO (keyring) y notificaciones de escritorio | Cualquier módulo de `backend/` |
| `mobile` (fase 5) | Expo / React Native y cliente HTTP | Cualquier módulo de `backend/` o `collector/`; acceso directo a la base de datos |

- Los puertos se definen en `application`. Las implementaciones del backend (repositorios, autenticadores, almacenamiento de informes, proveedor de AI) viven en `infrastructure`. El BLE vive solo en `collector/`.
- Los esquemas HTTP (Pydantic) viven en `api/`. Los casos de uso reciben DTOs de `application`, no modelos HTTP ni entidades de ORM.
- `application` expone los errores que `api` traduce a códigos HTTP; `api` nunca ve entidades ni excepciones de `domain`. *(Decidido)*
- El ensamblado de dependencias ocurre una sola vez, en `main.py`.
- En el colector, `sync.py` solo depende de `ports.py`; los adaptadores se conectan en su propio `main.py`. Las pruebas sustituyen cada puerto por un fake, sin tocar `bleak`. *(Decidido)*
- Una prueba de arquitectura (import-linter) falla en CI si un import viola la tabla.

## Idioma del código

- Identificadores en inglés (`GlucoseReading`, `sync_readings`). *(Decidido: `P-4`)*
- Interfaz de usuario, mensajes al usuario, nombres de campos visibles y glosario en español. *(Decidido: `P-4`)*
- Tildes y ñ: prohibidas en identificadores, permitidas en cadenas visibles y comentarios de dominio.

## Convenciones de nombres

| Elemento | Convención | Ejemplo |
| --- | --- | --- |
| Archivos y módulos Python | `snake_case` | `glucose_reading.py` |
| Clases | `PascalCase` | `GlucoseReading` |
| Funciones y variables | `snake_case` | `sync_readings` |
| Constantes | `UPPER_SNAKE_CASE` | `MAX_BATCH_SIZE` |
| Excepciones | Sufijo `Error` | `ReadingAlreadyExistsError` |
| Códigos de error de la API | `UPPER_SNAKE_CASE`, estables | `READING_BATCH_TOO_LARGE` |
| Campos JSON de la API | `snake_case`, iguales a los esquemas Pydantic y a las columnas | `measured_at` |
| Tablas | `snake_case`, plural | `glucose_readings` |
| Columnas | `snake_case` | `measured_at` |
| Restricciones e índices | `naming_convention` de SQLAlchemy: `pk_<tabla>`, `uq_<tabla>_<columnas>`, `fk_<tabla>_<columna>_<referida>`, `ix_<tabla>_<columnas>`, `ck_<tabla>_<regla>` | `uq_glucose_readings_idempotency_key` |
| Migraciones de Alembic | `AAAAMMDD_<slug>.py`, siempre con `downgrade()` | `20261115_create_glucose_readings.py` |
| Endpoints | Recursos en plural, minúsculas | `GET /api/v1/readings` |
| Variables de entorno | `UPPER_SNAKE_CASE` | `DATABASE_URL` |
| Ramas | `feature/`, `fix/`, `hotfix/`; `main` es la rama desplegable | `feature/ble-sync` |
| Commits | Conventional Commits **(Decidido: el historial inicial ya los usa)**. Scopes: `backend`, `collector`, `frontend`, `mobile`, `infra`, `ci`, `docs`, `steering` | `feat(collector): read stored readings` |
| Carpetas de spec | `fase-<N><letra>-<tema-en-kebab-case>`, en español | `.kiro/specs/fase-1a-infraestructura-y-auth/` |
| ADRs | `NNNN-titulo-en-kebab-case.md`, título en inglés; contenido en español | `docs/adr/0001-ble-collector-location.md` |

## Convenciones de API

- Versionado en la ruta: `/api/v1/...`. Un cambio incompatible requiere `/api/v2`.
- Fechas en ISO 8601 con zona horaria. Se guardan en UTC y se muestran en la zona configurada por el usuario: por defecto `America/Bogota` (UTC−5). El PDF indica la zona usada. *(Decidido)*
- La glucemia viaja siempre en mg/dL, junto con la unidad preferida del usuario. La web, la app y el PDF convierten con una regla única documentada en OpenAPI: mmol/L = mg/dL ÷ 18,016, un decimal, redondeo a la mitad hacia arriba. *(Decidido)*
- Campos JSON en `snake_case`, sin alias. Los clientes TypeScript usan los tipos generados desde el esquema OpenAPI. *(Decidido)*
- Errores con un cuerpo uniforme `{ "code": "...", "message": "...", "details": [...] }`, sin detalles internos, trazas ni el valor recibido.
- Lotes de lecturas atómicos: si una lectura es inválida, la API responde 422 `READING_INVALID` y no guarda nada del lote. Cada entrada de `details` indica la posición, el campo y el problema, por ejemplo `{ "index": 12, "field": "value", "problem": "fuera de rango" }`. *(Decidido)*
- Listados de lecturas: paginación por cursor opaco; `limit` de 100 por defecto y 500 como máximo; orden por instante descendente; filtros `start` y `end` en ISO 8601 como intervalo semiabierto `[start, end)`. *(Decidido)*
- Escrituras de lecturas idempotentes mediante la clave descrita en [tech.md](tech.md#flujos-críticos). La clave se deriva de los datos, no de un identificador que genere el cliente. Una restricción `UNIQUE` lo garantiza, así que la deduplicación no depende del código ni del orden de llegada.
- El esquema OpenAPI generado por FastAPI es el contrato de referencia: `backend/openapi.json` se commitea y CI lo regenera y falla si difiere. Las pruebas de contrato del colector y los tipos de la web se generan a partir de él. *(Decidido)*

## Decisiones de arquitectura vigentes

Índice. El detalle vive en [tech.md](tech.md#decisiones-abiertas) y en `docs/adr/`; si hay discrepancia, mandan ellos.

| Decisión | Fuente |
| --- | --- |
| Stack Python + FastAPI + PostgreSQL + Next.js | [tech.md · Stack](tech.md#stack) |
| Terraform para toda la infraestructura; región `sa-east-1` | [tech.md · Restricciones](tech.md#restricciones) |
| Colector BLE local, separado del backend | `T-2` · [ADR 0001](../../docs/adr/0001-ble-collector-location.md) |
| API en Lambda y Aurora PostgreSQL Serverless v2 con escala a cero | `T-3` · [ADR 0002](../../docs/adr/0002-serverless-compute-and-database.md) |
| Cognito: web con MFA TOTP; colector con refresh token en el almacén seguro del SO | `T-4`, `T-7` · [ADR 0003](../../docs/adr/0003-collector-authentication.md) |
| Next.js estático en S3 + CloudFront | `T-5` |
| App móvil Expo / React Native (fase 5; autenticación por validar) | `T-8` |
| API Gateway HTTP API y Lambda en VPC sin NAT; configuración por variables de entorno | `T-10`, `T-11` · [ADR 0004](../../docs/adr/0004-api-network-without-nat.md) |
| Docker Compose en local y CI; imagen de la API en ECR | [ADR 0005](../../docs/adr/0005-containerized-local-environment.md) |
| Fase 5 solo informativa, sin diagnóstico, tratamiento ni dosis | `P-5` · [product.md](product.md#decisiones-abiertas) |
| Clean Architecture, composition root en `main.py`, idempotencia por `UNIQUE` | Este documento: [Regla de dependencias](#regla-de-dependencias) y [Convenciones de API](#convenciones-de-api) |

Toda decisión nueva o que cambie una de estas se registra como ADR en `docs/adr/` y se añade a este índice. Los cambios de componentes o de flujos actualizan también el diagrama en `docs/architecture/`.

## Reglas para generar specs

Mantienen las specs cortas, verificables y revisables:

- Un requisito = una capacidad que se pueda probar. Máximo **8 requisitos** por spec.
- Máximo **5 criterios de aceptación** por requisito, en formato EARS:
  `WHEN <evento> THEN the system SHALL <respuesta>`.
- El diseño nombra solo los componentes que existirán. No inventes capas "por si acaso".
- Las tareas son cambios pequeños y verificables; máximo **25 tareas** por spec, cada una con
  `_Requirements: X.Y_`.
- Una spec no resuelve una decisión abierta (`P-n`, `T-n`) por su cuenta: la cita y pide aprobación.
- Si una spec supera estos límites, propón dividirla. Una fase puede tener varias specs (`fase-1a-…`, `fase-1b-…`); su criterio de "hecho" se comprueba al cerrar la última.
- Toda spec documenta su impacto arquitectónico: `### Architecture Views` en el diseño, decisiones «→ ADR» registradas con `kspec adr new` y `kspec diagrams check` en verde. La última spec de una fase comprueba la cobertura completa del catálogo. `kspec lint`, `/spec-converge` y CI lo bloquean.
- Ninguna spec de fase 2 o posterior empieza mientras la fase anterior no cumpla su criterio de "hecho" en [product.md](product.md#alcance-del-mvp).

## Definición de hecho (por tarea)

- [ ] Pruebas escritas y en verde; cobertura mínima de [tech.md](tech.md#estándares-de-calidad).
- [ ] Lint, formato y chequeo de tipos sin errores.
- [ ] Sin violaciones de la [regla de dependencias](#regla-de-dependencias).
- [ ] Migraciones reversibles cuando cambia el esquema.
- [ ] La imagen Docker se construye y `docker compose` levanta el entorno local, si la tarea toca el backend o la web.
- [ ] El esquema OpenAPI versionado está al día y los clientes pasan sus pruebas de contrato, si cambia un endpoint.
- [ ] semgrep y el escaneo de secretos y dependencias, sin hallazgos bloqueantes.
- [ ] Documentación de la API actualizada si cambia un endpoint; ADR si cambia una decisión de arquitectura; diagramas actualizados si cambia un componente, un flujo o una entidad (modelo `docs/architecture/diagrams.py`, `kspec diagrams export` y `kspec diagrams check` en verde).
- [ ] ADR registrado y Aceptado si la tarea materializa una decisión «→ ADR» del diseño.
- [ ] Pruebas con datos sintéticos; nunca lecturas reales del GD50 en el repositorio.
- [ ] Sin secretos, `.env` ni datos de salud en el diff ni en los logs.

## Mantenimiento del steering

- Tamaño total de los `.md` de `.kiro/steering/` ≤ ~70 000 caracteres. Luis amplió el límite (antes ~60 000 y ~40 000; referencia inicial ~30 000) para completar el steering, que es la base de todas las fases. No recortar contenido aprobado sin pedirlo.
- El tope del kit (`ALWAYS_STEERING_LIMIT`, hoy 74 000 en `kirolib.py`) debe ser siempre mayor que este límite. Si no, Codex, opencode y Copilot reciben el steering recortado sin aviso.
- Tras editar un steering, regenerar las copias con `kspec steering-sync --target cursor` y `kspec steering-sync --target claude`. No editar a mano `.cursor/rules/kiro-steering-*.mdc` ni `.claude/rules/kiro-steering-*.md`.
