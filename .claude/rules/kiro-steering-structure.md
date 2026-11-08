<!-- Generado por kspec desde .kiro/steering/structure.md. No lo edites aquí: edita el original. -->

# Estructura y convenciones — monitorglucosa

> Estados: **Decidido** salvo que se marque *Propuesto*. Las propuestas se confirman en la spec correspondiente
> o en un ADR. El árbol de abajo es el **destino** hacia el que converge el repositorio (hoy `fase-1a` tiene 10 de 33 tareas completadas en `backend/`).

## Organización de carpetas

```text
monitorglucosa/
├── .python-version       # 3.13; uv la aplica a backend/ y collector/
├── .pre-commit-config.yaml # gitleaks, ruff, mypy y kspec lint antes de cada commit
├── .github/              # workflows de CI y despliegue, plantilla de PR, rulesets y ajustes (git.md)
├── backend/              # API FastAPI con Clean Architecture
│   ├── pyproject.toml · uv.lock
│   ├── Dockerfile        # imagen única: local, CI y Lambda (ADR 0005)
│   ├── openapi.json      # contrato versionado; CI falla si difiere del generado
│   ├── src/
│   │   ├── main.py               # composition root: único punto que conecta las capas
│   │   ├── config.py             # configuración tipada (pydantic-settings); solo la lee main.py
│   │   ├── domain/               # entidades y reglas de negocio, sin frameworks
│   │   │   ├── readings/         # GlucoseReading, ReadingContext, origen ble/manual, marca de control (fase 1)
│   │   │   ├── insulin/          # InsulinDose, tipos de insulina, edición/borrado y alta retroactiva (fase 2)
│   │   │   ├── inventory/        # InsulinInventoryMovement, cálculo de saldo con punto de corte T_conteo (fase 3)
│   │   │   ├── annotations/      # Annotation, categorías (medicación excluye insulina), etiquetas (fases 2 y 3)
│   │   │   ├── alerts/           # ThresholdRule, AlertNotice y evaluación de glucemia/stock/24h (fase 3)
│   │   │   └── analysis/         # bloques de 4h, tiempo en rango, comparación de periodos y 3 reglas de patrones (fase 3)
│   │   ├── application/          # casos de uso, estadística descriptiva (a1+) y puertos (interfaces)
│   │   │   ├── readings/         # sincronización por lotes, registro manual, listado y tendencias (fase 1)
│   │   │   ├── insulin/          # registro rápido/retroactivo, edición/borrado y recálculo de inventario (fases 2 y 3)
│   │   │   ├── annotations/      # CRUD con confirmación, filtros y búsqueda avanzada (fases 2 y 3)
│   │   │   ├── reports/          # agregador descriptivo (a1+) y generación de informe PDF único (fases 2 y 3)
│   │   │   ├── exports/          # exportación CSV, Excel (.xlsx) y paquete de salida total (fases 2 y 3)
│   │   │   └── analysis/         # motor de patrones, comparación de periodos y evaluación de avisos (fase 3)
│   │   ├── infrastructure/       # PostgreSQL, autenticadores, S3, generadores PDF/CSV/XLSX y proveedor de IA (fase 4)
│   │   └── api/                  # routers FastAPI (/api/v1/...) y esquemas Pydantic de entrada/salida
│   └── tests/
│       ├── unit/                 # dominio y casos de uso (@pytest.mark.req)
│       ├── integration/          # PostgreSQL 16 real
│       ├── property/             # invariantes con Hypothesis (dominio, a1+, inventario y deduplicación)
│       └── architecture/         # reglas de dependencias (import-linter)
├── collector/            # colector BLE e importador dual local; proyecto uv propio; sin imports del backend
│   ├── src/collector/
│   │   ├── main.py       # composition root y CLI del colector (sincronización BLE e importación de respaldo local)
│   │   ├── config.py     # configuración tipada (pydantic-settings)
│   │   ├── sync.py       # núcleo de sincronización e importación dual; solo depende de ports.py
│   │   ├── ports.py      # DeviceReader, LocalBackupReader, ApiClient, TokenStore, Notifier
│   │   └── adapters/
│   │       ├── bleak_gd50.py     # extractor RACP (0x2A52) y decodificador GLS (0x2A18/0x2A34) del GD50
│   │       ├── local_backup.py   # lector e importador idempotente del archivo de respaldo local (451 lecturas)
│   │       ├── http_api.py       # cliente httpx hacia /api/v1 con reintentos 503 (ADR 0009)
│   │       ├── keyring_store.py  # almacenamiento y rotación del refresh token en el keyring del SO
│   │       └── desktop_notify.py # notificación local en el escritorio de Ubuntu (fase 3)
│   └── tests/            # unit/ con fakes y tramas sintéticas; contract/ contra backend/openapi.json
├── frontend/             # Next.js con exportación estática; TypeScript strict, Recharts, Vitest y Playwright (flujo crítico)
│   └── Dockerfile · nginx.conf   # web compilada servida con nginx en local
├── mobile/               # fase 5: app Expo / React Native (TypeScript), cliente de la API (T-8)
├── dev/jwt-issuer/       # emisor JWT de pruebas, solo para el entorno local
├── scripts/
│   ├── db_bootstrap.py   # bootstrap SQL idempotente por RDS Data API (ADR 0007)
│   └── smoke_test.py     # prueba de humo post-despliegue con reintentos de reanudación de Aurora (ADR 0009)
├── compose.yaml          # entorno local: API, PostgreSQL 16, web (nginx) y emisor JWT de pruebas
├── infra/terraform/      # módulos y un único estado remoto (prod en us-east-1): local y test no tienen recursos en AWS
├── docs/
│   ├── guia-de-desarrollo.md  # reglas y comandos del repositorio
│   ├── traceability.md        # matriz requisito EARS → tarea → código → prueba (@pytest.mark.req)
│   ├── operations/
│   │   └── readiness.md       # lista de verificación operativa antes de abrir el uso real en producción (OPS07-BP02)
│   ├── runbooks/              # procedimientos paso a paso: despliegue/rollback, alarmas US$16/US$20/US$30, restauración trimestral de Aurora + supresiones, pérdida de equipo
│   ├── adr/                   # NNNN-titulo-en-kebab-case.md, título en inglés
│   └── architecture/          # diagramas como código: modelo diagrams.py → .drawio, README y svg/ (kspec diagrams)
└── .kiro/                # steering, specs, hooks y tools/kiro_diagrams.py (librería de diagramas, la gestiona kspec)
```

- Cada componente tiene sus pruebas junto a él (`backend/tests/`, `collector/tests/`, `frontend/`), nunca dentro del código de producción.
- `backend/` y `collector/` son proyectos uv independientes, cada uno con su `pyproject.toml` y su lockfile. En `collector/` se reutilizan el extractor RACP, el decodificador GLS y los casos de prueba sintéticos ya validados en la carpeta local de investigación BLE, sin incluir jamás volcados ni lecturas reales del GD50. *(Decidido)*
- El colector, la web y la app móvil se comunican con el backend solo por HTTP (`/api/v1`). No hay imports entre ellos. El contrato compartido es el esquema OpenAPI que genera FastAPI (`backend/openapi.json`), no código.

## Regla de dependencias

Clean Architecture: las reglas de dependencias se verifican automáticamente con `import-linter`, a cambio de más estructura inicial que un script. Un import que viole esta tabla es un error de diseño y rompe CI.

| Módulo | Puede importar | Nunca importa |
| --- | --- | --- |
| `domain` | Biblioteca estándar | `application`, `infrastructure`, `api`, FastAPI, SQLAlchemy, SDK de AWS, librerías de PDF/Excel |
| `application` | `domain` | `infrastructure`, `api`, FastAPI, SQLAlchemy, `bleak`, SDK de AWS, librerías de PDF/Excel |
| `infrastructure` | `application`, `domain` | `api` |
| `api` | `application` (casos de uso, DTOs, puertos y errores) | `infrastructure`, `domain` |
| `main.py` (composition root) | Todas las capas | Es el único punto donde se conectan |
| `collector` | Biblioteca estándar, `bleak`, cliente HTTP, almacén seguro del SO (`keyring`) y notificaciones de escritorio | Cualquier módulo de `backend/` |
| `mobile` (fase 5) | Expo / React Native y cliente HTTP | Cualquier módulo de `backend/` o `collector/`; acceso directo a la base de datos |

- Los puertos se definen en `application`. Las implementaciones del backend (repositorios PostgreSQL, autenticadores, almacenamiento S3 de informes y supresiones, generadores de PDF con `fpdf2`/`ReportLab` y `.xlsx` con `openpyxl`, proveedor de IA en fase 4) viven en `infrastructure`. El BLE y la lectura del archivo de respaldo local viven solo en `collector/`.
- Los esquemas HTTP (Pydantic) viven en `api/`. Los casos de uso reciben DTOs de `application`, no modelos HTTP ni entidades de ORM.
- `application` expone los errores que `api` traduce a códigos HTTP; `api` nunca ve entidades ni excepciones de `domain`. *(Decidido)*
- El ensamblado de dependencias ocurre una sola vez, en `main.py`.
- En el colector, `sync.py` solo depende de `ports.py`; los adaptadores (`bleak`, archivo de respaldo local, `httpx`, `keyring`, notificaciones) se conectan en su propio `main.py`. Las pruebas sustituyen cada puerto por un fake, sin tocar `bleak`. *(Decidido)*
- Una prueba de arquitectura (`import-linter`) falla en CI si un import viola la tabla.

## Idioma del código

- Identificadores en inglés (`GlucoseReading`, `InsulinDose`, `InsulinInventoryMovement`, `sync_readings`). *(Decidido: `P-4`)*
- Interfaz de usuario, mensajes al usuario, nombres de campos visibles, informes PDF y glosario en español. *(Decidido: `P-4`)*
- Tildes y ñ: prohibidas en identificadores, permitidas en cadenas visibles y comentarios de dominio.

## Convenciones de nombres

| Elemento | Convención | Ejemplo |
| --- | --- | --- |
| Archivos y módulos Python | `snake_case` | `glucose_reading.py`, `insulin_dose.py` |
| Clases | `PascalCase` | `GlucoseReading`, `InsulinDose` |
| Funciones y variables | `snake_case` | `sync_readings`, `recalculate_inventory_balance` |
| Constantes | `UPPER_SNAKE_CASE` | `MAX_BATCH_SIZE` |
| Excepciones | Sufijo `Error` | `ReadingAlreadyExistsError` |
| Códigos de error de la API | `UPPER_SNAKE_CASE`, estables | `READING_BATCH_TOO_LARGE`, `DATABASE_UNAVAILABLE` |
| Campos JSON de la API | `snake_case`, iguales a los esquemas Pydantic y a las columnas | `measured_at`, `administered_at` |
| Tablas | `snake_case`, plural | `glucose_readings`, `insulin_doses`, `annotations` |
| Columnas | `snake_case` | `measured_at`, `units_applied` |
| Restricciones e índices | `naming_convention` de SQLAlchemy: `pk_<tabla>`, `uq_<tabla>_<columnas>`, `fk_<tabla>_<columna>_<referida>`, `ix_<tabla>_<columnas>`, `ck_<tabla>_<regla>` | `uq_glucose_readings_idempotency_key` |
| Migraciones de Alembic | `AAAAMMDD_<slug>.py`, siempre con `downgrade()` | `20261115_create_glucose_readings.py` |
| Endpoints | Recursos en plural, minúsculas | `GET /api/v1/readings`, `POST /api/v1/insulin-doses` |
| Variables de entorno | `UPPER_SNAKE_CASE` | `DATABASE_URL`, `DATABASE_CONNECT_TIMEOUT_S` |
| Ramas | `feature/<spec>`, `fix/<spec>`, `hotfix/<tema>`; `main` es la rama desplegable ([git.md](git.md)) | `feature/fase-1b-sincronizacion-ble` |
| Commits | Conventional Commits **(Decidido)**, uno por tarea con `Refs: <spec>#<tarea>`. Scopes: `backend`, `collector`, `frontend`, `mobile`, `infra`, `ci`, `docs`, `steering` | `feat(collector): read stored readings` |
| Pull Requests | Título en Conventional Commits; una spec (una ola si es grande); merge por rebase | `feat(collector): sincronizar lecturas del GD50` |
| Carpetas de spec | `fase-<N><letra>-<tema-en-kebab-case>`, en español | `.kiro/specs/fase-1a-infraestructura-y-auth/` |
| ADRs | `NNNN-titulo-en-kebab-case.md`, título en inglés; contenido en español | `docs/adr/0010-descriptive-statistics-without-clinical-recommendations.md` |

## Reglas Git (resumen)

Detalle, motivos y comandos en [git.md](git.md) y `docs/guia-de-desarrollo.md`.

- `main` siempre desplegable: nada directo; todo por PR con CI en verde y merge por rebase.
- Una rama por spec y un commit por tarea con `Refs: <spec>#<tarea>`, siempre con tu confirmación explícita.
- Repositorio público con doble barrera de privacidad: nunca secretos, `.env`, lecturas reales del GD50 (incluidas las 451 históricas), respaldos (`registros.csv`, `resumen.json`) ni exportaciones reales (CSV, `.xlsx`, PDF); viven fuera del árbol del repositorio bajo cifrado de disco.
- Cada despliegue a `prod` espera tu aprobación manual en GitHub, fuera de la ventana crítica diaria (`20:00–23:00` COT).

## Convenciones de API

- Versionado en la ruta: `/api/v1/...`. Un cambio incompatible requiere `/api/v2`.
- Fechas en ISO 8601 con zona horaria. Se guardan siempre en **UTC** y se muestran y analizan (incluidos los seis bloques fijos de 4 horas del motor de patrones) en la **zona horaria configurada por el usuario**: por defecto `America/Bogota` (`UTC−5`). El informe PDF indica explícitamente la zona horaria usada. *(Decidido)*
- La glucemia viaja siempre en mg/dL, junto con la unidad preferida del usuario. La web, la app y el PDF convierten con una regla única documentada en OpenAPI: $\text{mmol/L} = \text{mg/dL} \div 18{,}016$, un decimal, redondeo a la mitad hacia arriba. *(Decidido)*
- Campos JSON en `snake_case`, sin alias. Los clientes TypeScript usan los tipos generados desde el esquema OpenAPI (`backend/openapi.json`). *(Decidido)*
- Errores con un cuerpo uniforme `{ "code": "...", "message": "...", "details": [...] }`, sin detalles internos, trazas ni el valor recibido (`input`).
- Cuando Aurora Serverless v2 está reanudándose desde `MinCapacity = 0` y se agota el `connect_timeout` (20 s), la API responde **503 `DATABASE_UNAVAILABLE`** con cabecera `Retry-After: 5` ([ADR 0009](../../docs/adr/0009-aurora-resume-as-a-retryable-503-within-30-seconds.md)).
- Lotes de lecturas atómicos: si una lectura es inválida, la API responde 422 `READING_INVALID` y no guarda nada del lote. Cada entrada de `details` indica la posición, el campo y el problema, por ejemplo `{ "index": 12, "field": "value", "problem": "fuera de rango" }`. *(Decidido)*
- Listados de lecturas y eventos: paginación por cursor opaco; `limit` de 100 por defecto y 500 como máximo; orden por instante descendente; filtros `start` y `end` en ISO 8601 como intervalo semiabierto `[start, end)`. *(Decidido)*
- Escrituras de lecturas idempotentes mediante la clave descrita en [tech.md](tech.md#flujos-críticos) (`T-9`). La clave se deriva de los datos, no de un identificador que genere el cliente. Una restricción `UNIQUE` lo garantiza en PostgreSQL, así que la deduplicación no depende del código ni del orden de llegada.
- El esquema OpenAPI generado por FastAPI es el contrato de referencia: `backend/openapi.json` se commitea y CI lo regenera y falla si difiere. Las pruebas de contrato del colector y los tipos de la web se generan a partir de él. *(Decidido)*

## Decisiones de arquitectura vigentes

Índice. El detalle vive en [tech.md](tech.md#decisiones-abiertas) y en `docs/adr/`; si hay discrepancia, mandan ellos.

| Decisión | Fuente |
| --- | --- |
| Stack Python 3.13 + FastAPI + Aurora PostgreSQL 16 + Next.js estático | [tech.md · Stack](tech.md#stack) |
| Terraform para toda la infraestructura; región exclusiva **`us-east-1`** | [tech.md · Restricciones](tech.md#restricciones) · [ADR 0011](../../docs/adr/0011-aws-region-us-east-1-for-cost-optimization.md) |
| Colector BLE e importador dual local, separado del backend | `T-2` · [ADR 0001](../../docs/adr/0001-ble-collector-location.md) |
| API en Lambda y Aurora PostgreSQL Serverless v2 con escala a cero (`MinCapacity = 0`) en `us-east-1` | `T-3` · [ADR 0002](../../docs/adr/0002-serverless-compute-and-database.md) · [ADR 0011](../../docs/adr/0011-aws-region-us-east-1-for-cost-optimization.md) |
| Cognito: web con MFA TOTP; colector con refresh token rotatorio en el almacén seguro del SO | `T-4`, `T-7` · [ADR 0003](../../docs/adr/0003-collector-authentication.md) |
| Next.js estático en S3 + CloudFront | `T-5` |
| App móvil Expo / React Native (fase 5; autenticación por validar) | `T-8` |
| API Gateway HTTP API y Lambda en VPC sin NAT Gateway; configuración por variables de entorno | `T-10`, `T-11` · [ADR 0004](../../docs/adr/0004-api-network-without-nat.md) |
| Docker Compose en local y CI; imagen única de la API en ECR | [ADR 0005](../../docs/adr/0005-containerized-local-environment.md) |
| Migraciones con una Lambda `migrator` dentro de la VPC, misma imagen que la API | [ADR 0006](../../docs/adr/0006-database-migrations-with-an-in-vpc-migrator-lambda.md) |
| Roles de base de datos con un bootstrap SQL idempotente por RDS Data API desde el pipeline | [ADR 0007](../../docs/adr/0007-idempotent-sql-bootstrap-through-rds-data-api.md) |
| Rol de despliegue acotado con *permissions boundary* (`aws:RequestedRegion = us-east-1`) y pipeline público sin fugas | [ADR 0008](../../docs/adr/0008-scoped-deployment-role-and-leak-free-pipeline.md) |
| Aurora en pausa: 503 `DATABASE_UNAVAILABLE` con `Retry-After`, reintento de los clientes hasta 60 s | [ADR 0009](../../docs/adr/0009-aurora-resume-as-a-retryable-503-within-30-seconds.md) |
| Estadística descriptiva (`a1+`), saldo de inventario y patrones objetivos permitidos; diagnóstico, adherencia y dosis prohibidos (`P-5`) | `P-5` · [ADR 0010](../../docs/adr/0010-descriptive-statistics-without-clinical-recommendations.md) |
| Cambio de región de AWS de `sa-east-1` a `us-east-1` manteniendo toda la arquitectura de ahorro (`< US$20/mes`) | `T-3`, `T-10` · [ADR 0011](../../docs/adr/0011-aws-region-us-east-1-for-cost-optimization.md) |
| Estrategia Git y GitHub: GitHub Flow, rebase, repo público con doble barrera de privacidad, `prod` con aprobación manual | [git.md](git.md) |
| Clean Architecture, composition root en `main.py`, idempotencia por `UNIQUE` | Este documento: [Regla de dependencias](#regla-de-dependencias) y [Convenciones de API](#convenciones-de-api) |

Toda decisión nueva o que cambie una de estas se registra como ADR en `docs/adr/` y se añade a este índice. Los cambios de componentes, regiones, entidades o flujos actualizan también el diagrama en `docs/architecture/` (`docs/architecture/diagrams.py`).

## Reglas para generar specs

Mantienen las specs cortas, verificables y revisables:

- Un requisito = una capacidad que se pueda probar. Máximo **8 requisitos** por spec.
- Máximo **5 criterios de aceptación** por requisito, en formato EARS:
  `WHEN <evento> THEN the system SHALL <respuesta>`.
- El diseño nombra solo los componentes que existirán. No inventes capas «por si acaso».
- Las tareas son cambios pequeños y verificables; máximo **25 tareas** por spec (salvo excepción ya aprobada en `fase-1a`), cada una con `_Requirements: X.Y_`.
- Una spec no resuelve una decisión abierta (`P-n`, `T-n`, `D-n`) por su cuenta: la cita y pide aprobación.
- **Gobierno de dependencias externas (`R4.1`):** una dependencia externa como la validación médica de umbrales (`P-2`, `D-2`) solo bloquea el cierre formal de dicha validación personalizada; nunca bloquea el diseño ni la implementación de las specs del MVP, que avanzan usando umbrales configurables por el usuario y valores iniciales de una guía clínica citada con descargo visible.
- Si una spec supera estos límites, propón dividirla. Una fase puede tener varias specs (`fase-1a-…`, `fase-1b-…`, `fase-2a-…`, `fase-2b-…`); su criterio de «hecho» se comprueba al cerrar la última.
- Toda spec documenta su impacto arquitectónico: `### Architecture Views` en el diseño, decisiones «→ ADR» registradas con `kspec adr new` y `kspec diagrams check` en verde. La última spec de una fase comprueba la cobertura completa del catálogo. `kspec lint`, `/spec-converge` y CI lo bloquean.
- Ninguna spec de fase 2 o posterior empieza mientras la fase anterior no cumpla su criterio de «hecho» en [product.md](product.md#alcance-del-mvp).

## Definición de hecho (por tarea)

- [ ] Pruebas escritas, en verde y con marcador `@pytest.mark.req("<spec>#<X.Y>")` para cada criterio EARS verificado (`kspec trace check`); cobertura mínima de [tech.md](tech.md#estándares-de-calidad).
- [ ] Lint, formato y chequeo de tipos sin errores (`ruff`, `mypy`, `ESLint`, `TypeScript strict`).
- [ ] Sin violaciones de la [regla de dependencias](#regla-de-dependencias) (`lint-imports`).
- [ ] Migraciones reversibles cuando cambia el esquema.
- [ ] La imagen Docker se construye y `docker compose` levanta el entorno local, si la tarea toca el backend o la web.
- [ ] El esquema OpenAPI versionado (`backend/openapi.json`) está al día y los clientes pasan sus pruebas de contrato, si cambia un endpoint.
- [ ] `pre-commit`, `gitleaks`, `semgrep` y el escaneo de secretos y dependencias, sin hallazgos bloqueantes.
- [ ] Documentación de la API actualizada si cambia un endpoint; ADR registrado y Aceptado si cambia una decisión de arquitectura o materializa una decisión «→ ADR» del diseño; diagramas actualizados si cambia un componente, región, flujo o entidad (modelo `docs/architecture/diagrams.py`, `kspec diagrams export` y `kspec diagrams check` en verde).
- [ ] Pruebas con datos sintéticos; nunca lecturas reales del GD50, respaldos (`registros.csv`) ni exportaciones reales en el repositorio o en artefactos de CI.
- [ ] Sin secretos, `.env` ni datos de salud en el diff ni en los logs.

## Mantenimiento del steering

- Tamaño total de los `.md` de `.kiro/steering/` ≤ **~220 000 caracteres** (hoy ~205 300 caracteres sumando `discovery.md`, `product.md`, `tech.md`, `structure.md` y `git.md`, de los cuales ~198 000 corresponden a los cuatro documentos `inclusion: always`). Luis decidió conservar todo el steering por encima de los 74 000 caracteres (ampliando los topes previos de ~30 000 → ~40 000 → ~60 000 → ~70 000 → ~220 000) con `inclusion: always` en `discovery.md`, `product.md`, `tech.md` y `structure.md` para que todos sus agentes de IA dispongan del contexto íntegro del proyecto sin perder ni recortar ningún detalle. **Prohibido recortar o resumir contenido aprobado sin pedirlo explícitamente a Luis.**
- El tope del kit (`ALWAYS_STEERING_LIMIT`, ampliado a **240 000** en `~/.cursor/kiro/lib/kirolib.py`) debe ser siempre mayor que este límite para que Codex, opencode y Copilot reciban el steering completo sin truncamiento.
- Tras editar un steering, regenerar las copias con `kspec steering-sync --target cursor` y `kspec steering-sync --target claude`. No editar a mano `.cursor/rules/kiro-steering-*.mdc` ni `.claude/rules/kiro-steering-*.md`.
