# Matriz de trazabilidad

> Generado por `kspec trace` (`.kiro/tools/kiro_trace.py generate`) a partir de las specs y de las etiquetas de las pruebas. No lo edites a mano: CI falla si no coincide con lo generado.

Estado: ✅ prueba etiquetada y tareas hechas · 📝 verificación manual justificada y tareas hechas · ⚠️ falta la prueba o la tarea · ❌ sin prueba ni tarea hecha. Tareas: ✓ hecha · ○ pendiente.

## Resumen

| Fase | Spec | Estado | Criterios | Con prueba | Manuales | Sin verificar | Cobertura |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [fase-1a-infraestructura-y-auth](#fase-1a-infraestructura-y-auth) | en curso | 45 | 0 | 0 | 45 | 0 % |

| Fase | Specs | Criterios verificados |
| --- | --- | --- |
| 1 | 1 | 0/45 (0 %) |

## fase-1a-infraestructura-y-auth

[Requisitos](../.kiro/specs/fase-1a-infraestructura-y-auth/requirements.md) · [Diseño](../.kiro/specs/fase-1a-infraestructura-y-auth/design.md) · [Tareas](../.kiro/specs/fase-1a-infraestructura-y-auth/tasks.md) · 0/45 criterios verificados (0 %) · en curso · tareas 1/33

| Requisito | Criterio | Componentes | Decisiones | Tareas | Pruebas | Estado |
| --- | --- | --- | --- | --- | --- | --- |
| **1** · Entorno local reproducible | 1.1 | `compose.yaml`, `backend/Dockerfile`, `backend/.dockerignore`, `dev/jwt-issuer`, `dev/postgres/init` | D10, D15, ADR 0005 | 12 ○ | — | ❌ |
| 1 | 1.2 | `compose.yaml`, `backend/Dockerfile`, `backend/.dockerignore`, `dev/jwt-issuer`, `dev/postgres/init` | D10, D15, ADR 0005 | 12 ○ | — | ❌ |
| 1 | 1.3 | `compose.yaml`, `backend/Dockerfile`, `backend/.dockerignore`, `dev/jwt-issuer`, `dev/postgres/init` | D10, D15, ADR 0005 | 12 ○ | — | ❌ |
| 1 | 1.4 | `config.Settings` | D9 | 6 ○, 6.1 ○ | — | ❌ |
| **2** · API base, salud y errores | 2.1 | `api.routers.health`, `CheckReadiness`, `SqlDatabaseProbe` | D7 | 9 ○ | — | ❌ |
| 2 | 2.2 | `api.routers.health`, `CheckReadiness`, `SqlDatabaseProbe` | D7 | 4 ○, 9 ○ | — | ❌ |
| 2 | 2.3 | `api.errors`, `api.openapi.build_openapi`, `openapi.yaml` | D6, D16 | 7 ○, 7.1 ○, 11 ○, 11.1 ○ | — | ❌ |
| 2 | 2.4 | `RequestLogMiddleware`, `JsonFormatter` | — | 7 ○, 7.2 ○ | — | ❌ |
| 2 | 2.5 | Contratos de import-linter | — | 5 ○ | — | ❌ |
| **3** · Autenticación en la API | 3.1 | `ApiGatewayClaimsAuthenticator`, `LocalJwksAuthenticator`, `current_identity`, `api.routers.me`, `config.Settings`, `main.create_app` | D9, ADR 0005 | 8 ○, 8.1 ○ | — | ❌ |
| 3 | 3.2 | `ApiGatewayClaimsAuthenticator`, `LocalJwksAuthenticator`, `current_identity`, `api.routers.me`, `config.Settings`, `main.create_app` | D9, ADR 0005 | 8 ○, 8.1 ○ | — | ❌ |
| 3 | 3.3 | `ApiGatewayClaimsAuthenticator`, `LocalJwksAuthenticator`, `current_identity`, `api.routers.me`, `config.Settings`, `main.create_app` | D9, ADR 0005 | 8 ○, 8.2 ○, 12 ○ | — | ❌ |
| 3 | 3.4 | `ApiGatewayClaimsAuthenticator`, `LocalJwksAuthenticator`, `current_identity`, `api.routers.me`, `config.Settings`, `main.create_app` | D9, ADR 0005 | 6 ○, 6.1 ○ | — | ❌ |
| 3 | 3.5 | `ApiGatewayClaimsAuthenticator`, `LocalJwksAuthenticator`, `current_identity`, `api.routers.me`, `config.Settings`, `main.create_app` | D9, ADR 0005 | 8 ○ | — | ❌ |
| **4** · Identidad con Amazon Cognito | 4.1 | Módulo `identity`, autorizador JWT del módulo `api` | D11, D12, ADR 0003, T-7 | 17 ○ | — | ❌ |
| 4 | 4.2 | Módulo `identity`, autorizador JWT del módulo `api` | D11, D12, ADR 0003, T-7 | 17 ○, 23 ○ | — | ❌ |
| 4 | 4.3 | Módulo `identity`, autorizador JWT del módulo `api` | D11, D12, ADR 0003, T-7 | 17 ○ | — | ❌ |
| 4 | 4.4 | Módulo `identity`, autorizador JWT del módulo `api` | D11, D12, ADR 0003, T-7 | 17 ○ | — | ❌ |
| 4 | 4.5 | Módulo `identity`, autorizador JWT del módulo `api` | D11, D12, ADR 0003, T-7 | 18 ○, 23 ○, 24 ○ | — | ❌ |
| **5** · Red y base de datos en AWS | 5.1 | Módulos `network` y `database` | D13, ADR 0002, ADR 0004 | 16 ○, 24 ○ | — | ❌ |
| 5 | 5.2 | Módulos `network` y `database` | D13, ADR 0002, ADR 0004 | 16 ○ | — | ❌ |
| 5 | 5.3 | `infrastructure.db.engine`, `scripts/sql/bootstrap.sql`, `scripts/db_bootstrap.py` | D3, D8 | 2 ○, 9 ○, 10 ○, 10.1 ○ | — | ❌ |
| 5 | 5.4 | `infrastructure.db.engine`, `SqlDatabaseProbe` | D8, ADR 0004 | 4 ○, 9 ○, 23 ○ | — | ❌ |
| 5 | 5.5 | Módulos `network` y `database` | D13, ADR 0002, ADR 0004 | 16 ○ | — | ❌ |
| **6** · Exposición de la API y del sitio | 6.1 | Módulos `api` y `site`, `bootstrap` (ECR) | D13, ADR 0004, ADR 0005 | 15 ○, 18 ○ | — | ❌ |
| 6 | 6.2 | Módulos `api` y `site`, `bootstrap` (ECR) | D13, ADR 0004, ADR 0005 | 18 ○, 24 ○ | — | ❌ |
| 6 | 6.3 | Módulos `api` y `site`, `bootstrap` (ECR) | D13, ADR 0004, ADR 0005 | 18 ○, 23 ○ | — | ❌ |
| 6 | 6.4 | Módulos `api` y `site`, `bootstrap` (ECR) | D13, ADR 0004, ADR 0005 | 18 ○ | — | ❌ |
| 6 | 6.5 | Módulos `api` y `site`, `bootstrap` (ECR) | D13, ADR 0004, ADR 0005 | 18 ○ | — | ❌ |
| **7** · Integración y despliegue continuo | 7.1 | `.github/workflows/ci.yml`, `.github/rulesets/main.json`, `backend/tools/export_openapi.py` | D15 | 10 ○, 11 ○, 21 ○ | — | ❌ |
| 7 | 7.2 | Módulo `bootstrap` (OIDC), `.github/workflows/deploy.yml` | D1, D4, G-2 | 3 ○, 15 ○, 22 ○ | — | ❌ |
| 7 | 7.3 | Módulo `bootstrap` (OIDC), `.github/workflows/deploy.yml` | D1, D4, G-2 | 22 ○, 23 ○ | — | ❌ |
| 7 | 7.4 | `scripts/deploy.py`, `main.create_migrator_app`, `infrastructure.db.migrations`, `scripts/db_bootstrap.py`, `scripts/smoke_test.py` | D2, D3, D5, D7 | 1 ✓, 2 ○, 10 ○, 14 ○, 14.1 ○, 22 ○ | — | ❌ |
| 7 | 7.5 | `scripts/deploy.py`, `main.create_migrator_app`, `infrastructure.db.migrations`, `scripts/db_bootstrap.py`, `scripts/smoke_test.py` | D2, D3, D5, D7 | 14 ○, 14.1 ○, 22 ○, 24 ○ | — | ❌ |
| **8** · Infraestructura como código, coste y operación | 8.1 | Módulo `bootstrap`, `default_tags` del proveedor | D1 | 15 ○ | — | ❌ |
| 8 | 8.2 | Módulo `bootstrap`, `default_tags` del proveedor | D1 | 15 ○ | — | ❌ |
| 8 | 8.3 | Módulo `operations` | D11, D14 | 19 ○, 23 ○ | — | ❌ |
| 8 | 8.4 | Módulo `operations` | D11, D14 | 19 ○, 23 ○, 24 ○ | — | ❌ |
| 8 | 8.5 | Módulo `operations` | D11, D14 | 19 ○ | — | ❌ |
| **NFR** · No funcionales | NFR-1 | Transversal (pytest-cov) | — | 5 ○ | — | ❌ |
| NFR | NFR-2 | `infrastructure.db.engine`, Lambda `api`, `scripts/smoke_test.py` | D7, D8 | 4 ○, 9 ○, 14 ○, 23 ○ | — | ❌ |
| NFR | NFR-3 | Módulo `operations`, estimación de coste | D13, D14, T-3 | 19 ○, 23 ○ | — | ❌ |
| NFR | NFR-4 | Políticas IAM de los módulos, checkov | D4 | 3 ○, 21 ○ | — | ❌ |
| NFR | NFR-5 | `JsonFormatter`, `RequestLogMiddleware`, `.dockerignore`, `deploy.yml`, `deploy.py` | D3, D4, D11 | 3 ○, 7 ○, 7.2 ○, 21 ○ | — | ❌ |
| NFR | NFR-6 | `openapi.yaml`, `api.openapi.build_openapi`, `backend/tools/export_openapi.py`, `docs/api/README.md`, pruebas de contrato | D16, D17 | 11 ○, 11.1 ○, 23 ○ | — | ❌ |

## Pruebas huérfanas

Etiquetas y verificaciones manuales que no apuntan a un criterio existente. Siempre bloquean: corrige la etiqueta o el criterio.

Ninguna.
