# Requirements Document

## Introduction

Esta spec construye el esqueleto desplegable de monitorglucosa para el usuario propietario: la API base en FastAPI
con Clean Architecture, el entorno local con Docker Compose, la infraestructura de `prod` en AWS (`sa-east-1`) con
Terraform, la identidad con Amazon Cognito y el pipeline de integración y despliegue con prueba de humo. Todavía no
guarda lecturas: deja la API desplegada, protegida y observable para que las specs de sincronización BLE y de
registro, historial y web solo añadan funcionalidad. Materializa los ADR 0002, 0003 (lado servidor), 0004 y 0005.

## Requirements

### Requirement 1 — Entorno local reproducible

**User Story:** As a desarrollador del proyecto, I want levantar la API, su base de datos y un emisor de tokens de prueba con un solo comando, so that desarrolle y pruebe igual en cualquier máquina y en CI sin depender de AWS.

#### Acceptance Criteria

1. WHEN se ejecuta `docker compose up` sobre un clon limpio THEN the system SHALL levantar la API, PostgreSQL `postgres:16` y el emisor JWT de pruebas, y la API SHALL responder 200 en `/health` cuando el healthcheck de cada servicio esté en verde.
2. WHEN se construye la imagen de la API THEN the system SHALL producir una única imagen que se ejecuta sin cambios en Compose, en CI y en Lambda (Lambda Web Adapter), sin código específico de Lambda.
3. IF el contexto de construcción contiene `.env`, secretos o datos THEN the system SHALL excluirlos con `.dockerignore`, y la imagen SHALL no contener credenciales.
4. IF falta una variable de entorno obligatoria al arrancar la API THEN the system SHALL negarse a arrancar con un mensaje que nombra la variable, sin mostrar ningún valor de configuración.

### Requirement 2 — API base, salud y errores

**User Story:** As a usuario propietario, I want una API con comprobaciones de salud, errores uniformes y logs sin datos sensibles, so that sepa si el servicio funciona sin exponer información de salud.

#### Acceptance Criteria

1. WHEN se recibe `GET /health` THEN the system SHALL responder 200 sin abrir ninguna conexión a la base de datos.
2. WHEN se recibe `GET /health/ready` THEN the system SHALL comprobar la conexión a la base de datos y responder 200 si responde, o 503 con el cuerpo de error uniforme si no responde.
3. IF una petición que llega a la API no supera la validación o produce un error THEN the system SHALL responder con el cuerpo `{ "code": "...", "message": "...", "details": [...] }`, con `code` estable en `UPPER_SNAKE_CASE`, sin trazas, detalles internos ni el valor recibido (el 422 por defecto de FastAPI se reemplaza para no devolver `input`). Las respuestas que genera API Gateway sin invocar la API (rechazos del autorizador JWT o de la firma IAM, throttling y fallos o timeouts de la integración) conservan su formato y se identifican por su código HTTP.
4. WHEN la API atiende una petición THEN the system SHALL escribir un log JSON con un identificador de correlación, método, ruta, estado y duración, sin cuerpos, tokens ni datos de salud.
5. IF un módulo importa una capa que la regla de dependencias de `structure.md` prohíbe THEN the system SHALL hacer fallar la prueba de arquitectura (import-linter) en CI.

### Requirement 3 — Autenticación en la API

**User Story:** As a usuario propietario, I want que la API solo atienda peticiones con mi identidad verificada, so that nadie más pueda leer ni escribir mis datos de salud.

#### Acceptance Criteria

1. WHILE la API corre en `prod` the system SHALL obtener la identidad de los claims del autorizador JWT que Lambda Web Adapter entrega en la cabecera `x-amzn-request-context` (`requestContext.authorizer.jwt.claims`).
2. IF una petición a una ruta protegida llega en `prod` sin esa cabecera o sin el claim de sujeto THEN the system SHALL responder 401 con el cuerpo de error uniforme, sin tratarla nunca como anónima.
3. WHILE la API corre en `local` the system SHALL validar firma, emisor, audiencia y expiración del token contra la JWKS del emisor de pruebas, y SHALL responder 401 si alguna comprobación falla.
4. IF la configuración de `prod` selecciona el adaptador local o acepta el emisor de pruebas THEN the system SHALL negarse a arrancar, y una prueba de CI SHALL verificarlo.
5. WHEN se recibe `GET /api/v1/me` con una identidad válida THEN the system SHALL responder 200 solo con el identificador de sujeto (`sub`).

### Requirement 4 — Identidad con Amazon Cognito

**User Story:** As a usuario propietario, I want una identidad en Cognito con MFA y un cliente para la web y otro para el colector, so that ambos clientes obtengan tokens que la API acepte.

#### Acceptance Criteria

1. THE SYSTEM SHALL crear con Terraform un user pool de Cognito (plan Essentials) en `sa-east-1` con el registro propio desactivado, MFA TOTP obligatorio, sin SMS y con protección contra borrado.
2. WHEN se da de alta al usuario propietario THEN the system SHALL permitirlo solo con credenciales de administrador y SHALL exigir que configure el TOTP en su primer inicio de sesión.
3. THE SYSTEM SHALL crear un cliente público de la web, sin secreto, con el flujo de código de autorización con PKCE y con el dominio de CloudFront del sitio como URL de callback y de cierre de sesión.
4. THE SYSTEM SHALL crear un cliente público del colector, sin secreto, con código de autorización y PKCE (S256), callback `http://localhost` según `T-7`, refresh token de 30 días, rotación activada y `RetryGracePeriodSeconds` fijado explícitamente.
5. IF API Gateway recibe un token con firma inválida, expirado, de otro emisor o cuyo `aud` o `client_id` no es uno de esos dos clientes THEN the system SHALL responder 401 sin invocar la Lambda.

### Requirement 5 — Red y base de datos en AWS

**User Story:** As a usuario propietario, I want que mis datos vivan en una base de datos cifrada, privada y que escala a cero, so that estén protegidos y el coste quede por debajo de US$20/mes.

#### Acceptance Criteria

1. THE SYSTEM SHALL crear con Terraform una VPC en `sa-east-1` sin NAT Gateway ni ruta a internet desde sus subredes privadas, con un endpoint gateway de S3.
2. THE SYSTEM SHALL crear un clúster Aurora PostgreSQL Serverless v2, versión 16.4 o superior, con `MinCapacity` 0, pausa automática tras 300 s, sin acceso público, cifrado con la clave KMS gestionada por AWS, backups de 7 días con recuperación a un punto en el tiempo, protección contra borrado y contraseña maestra gestionada por RDS en Secrets Manager.
3. WHEN la Lambda se conecta a Aurora THEN the system SHALL usar TLS y autenticación IAM con un usuario de base de datos distinto del maestro y con solo los privilegios que la API necesita.
4. WHEN la API atiende una petición que usa la base de datos THEN the system SHALL abrir una conexión y cerrarla al terminar, sin pool persistente ni RDS Proxy, para no impedir la pausa.
5. IF llega una conexión a Aurora desde un origen distinto de los grupos de seguridad de la API y de las migraciones, o sin TLS THEN the system SHALL rechazarla.

### Requirement 6 — Exposición de la API y del sitio

**User Story:** As a usuario propietario, I want la API detrás de API Gateway y el sitio detrás de CloudFront con controles de acceso, so that solo yo pueda usarlos y los abusos queden limitados.

#### Acceptance Criteria

1. THE SYSTEM SHALL desplegar la API en una Lambda dentro de la VPC a partir de una imagen de un repositorio ECR, identificada por su digest, con una política de ciclo de vida que conserva solo las últimas imágenes.
2. THE SYSTEM SHALL exponer la Lambda con una API Gateway HTTP API en la que las rutas `/api/v1/*` exigen el autorizador JWT de Cognito, `/health` es pública y `/health/ready` exige autorización IAM.
3. IF las peticiones superan 10 por segundo sostenidas o una ráfaga de 20 THEN the system SHALL responder 429 desde API Gateway sin invocar la Lambda.
4. THE SYSTEM SHALL crear un bucket S3 privado servido solo por CloudFront con control de acceso de origen y cabeceras HSTS y CSP, y SHALL denegar el acceso directo al bucket.
5. WHEN un navegador hace una petición CORS a la API THEN the system SHALL permitir solo el origen de CloudFront.

### Requirement 7 — Integración y despliegue continuo

**User Story:** As a usuario propietario, I want que cada cambio se pruebe en CI y llegue a `prod` solo con mi aprobación, con prueba de humo y vuelta atrás, so that `main` siga desplegable y un fallo no deje la API rota.

#### Acceptance Criteria

1. WHEN se abre o actualiza un PR que toca el backend, la infraestructura o Compose THEN the system SHALL ejecutar el job `ci` (ruff, mypy estricto, pytest con PostgreSQL real incluidos `upgrade` y `downgrade` de las migraciones, import-linter, comparación de `backend/openapi.json`, `terraform fmt` y `validate`, semgrep, gitleaks, dependency review y construcción de la imagen) y SHALL bloquear el merge si alguno falla.
2. WHEN GitHub Actions se autentica en AWS THEN the system SHALL usar OIDC con un rol cuya política de confianza solo acepta `sub` = `repo:ldordellygithub/monitorglucosa:environment:prod` y `aud` = `sts.amazonaws.com`, sin claves de larga duración.
3. WHEN se fusiona un cambio en `main` THEN the system SHALL construir la imagen, probarla con Compose, subirla a ECR y esperar la aprobación del revisor del entorno `prod` (declarado según `G-2`) antes de aplicar Terraform con ese digest.
4. WHEN un despliegue incluye migraciones pendientes THEN the system SHALL aplicarlas desde dentro de la VPC antes de que la Lambda sirva el nuevo digest y, si una falla, SHALL detener el despliegue sin cambiar el digest en servicio.
5. WHEN termina un despliegue THEN the system SHALL ejecutar la prueba de humo (`/health/ready` firmado con el rol OIDC responde 200 con un timeout ≥ 40 s, y una ruta de `/api/v1` sin token responde 401) y, si falla, SHALL volver a desplegar el digest anterior y marcar el despliegue como fallido.

### Requirement 8 — Infraestructura como código, coste y operación

**User Story:** As a usuario propietario, I want que toda la infraestructura esté en Terraform, etiquetada, con presupuesto y alarmas, so that controle el coste y me entere de los fallos sin revisar la consola.

#### Acceptance Criteria

1. THE SYSTEM SHALL gestionar todos los recursos de AWS con Terraform, con el estado remoto en un bucket S3 cifrado con `use_lockfile = true`, incluidos el propio bucket de estado y el rol OIDC (bootstrap).
2. THE SYSTEM SHALL etiquetar todos los recursos de AWS con `Environment`, `Project` y `Owner`.
3. WHEN el gasto real o previsto del mes supera el 80 % de US$20 THEN the system SHALL enviar un aviso por correo desde AWS Budgets, medido sobre todo el gasto de la cuenta, que es exclusiva de monitorglucosa.
4. WHEN la Lambda registra errores o API Gateway devuelve respuestas 5xx THEN the system SHALL disparar una alarma de CloudWatch que avisa por correo a una dirección configurada fuera del repositorio, sin ningún monitor que llame a la API de forma periódica.
5. THE SYSTEM SHALL fijar en 30 días la retención de todos los grupos de logs de CloudWatch que crea esta spec.

## Non-Functional Requirements

1. THE SYSTEM SHALL mantener la cobertura de pruebas en ≥ 80 % en `domain` y `application`.
2. THE SYSTEM SHALL responder `/health/ready` con 200 en ≤ 60 s sumando los reintentos cuando Aurora está en pausa (cada petición individual termina antes del límite de 30 s de API Gateway), y `GET /health` y `GET /api/v1/me` en p95 < 500 ms con la Lambda caliente.
3. THE SYSTEM SHALL mantener el coste de la infraestructura de esta spec, con uso bajo, por debajo de US$20/mes, con una estimación contra los precios de `sa-east-1` antes del primer despliegue y la factura del primer mes como validación (`T-3`).
4. THE SYSTEM SHALL no tener ninguna política IAM con `Action: "*"` ni `Resource: "*"`, salvo las acciones que AWS no permite acotar a un recurso, listadas y justificadas en el diseño; una comprobación automática sobre el código de Terraform en CI lo verifica.
5. THE SYSTEM SHALL no incluir secretos, tokens, datos de salud ni datos personales (incluido el correo de las alarmas) en el repositorio, las imágenes ni los logs; gitleaks y semgrep terminan sin hallazgos bloqueantes y el estado de Terraform no contiene la contraseña maestra de Aurora.
6. THE SYSTEM SHALL documentar cada operación de la API en un contrato OpenAPI 3.1 con `operationId`, seguridad y todas las respuestas posibles con esquema y ejemplo, incluidas las que genera API Gateway, y CI SHALL fallar si `backend/openapi.json`, el contrato `openapi.yaml` de la spec, la referencia `docs/api/README.md` o las respuestas reales de la API dejan de ser conformes entre sí.

## Out of Scope

- Lecturas del GD50, su modelo de datos y la clave de idempotencia (`T-9`): spec de sincronización BLE.
- Inicio de sesión del colector (PKCE, keyring, rotación en el cliente) y la validación del callback `http://localhost` de `T-7`: spec del colector. Aquí solo se crea su cliente de Cognito.
- La aplicación web (Next.js), su inicio de sesión, historial, gráfica y unidades: spec de la web. Aquí solo se crea el hosting vacío.
- Registro manual de lecturas, umbrales, alertas, informes, exportación y la app móvil.
- Registro de supresiones en S3 y prueba trimestral de restauración: llegan con el primer borrado de datos.
- Ampliar `kspec github apply` para declarar el revisor del entorno `prod` (`G-2`): se hace en el kit, antes de la tarea de despliegue.
- Crear la cuenta de AWS: requisito previo del bootstrap.
- Staging, dominio propio, ACM, NAT Gateway, RDS Proxy y RDS Data API como ruta de datos de la API (el pipeline solo la usa para el bootstrap SQL de roles: D3, ADR 0007).

## Clarifications

- 2026-11-01: ¿Qué entra en esta spec? → El esqueleto desplegable: API base, entorno local, Terraform de `prod`, autenticación en la API y CI/CD con prueba de humo; sin lecturas, web ni colector.
- 2026-11-01: ¿Qué clientes de Cognito y qué hosting crea esta spec? → Los dos clientes (web y colector) y el bucket S3 con CloudFront vacío, para fijar el callback de la web y el origen CORS desde el inicio.
- 2026-11-01: ¿Cómo se resuelve `G-2`? → Ampliando el kit para que `kspec github apply` declare el revisor del entorno `prod`, fuera de esta spec y antes de la tarea de despliegue.
- 2026-11-01: ¿En qué cuenta de AWS se despliega? → Todavía no existe; crearla es requisito previo del bootstrap.
- 2026-11-01: ¿La cuenta nueva será exclusiva de monitorglucosa? → Sí: el presupuesto mide toda la cuenta, sin filtro por etiqueta (8.3).
- 2026-11-01: HTTP API no permite personalizar sus respuestas de error (solo las REST API tienen *gateway responses*). ¿Se mantiene 2.3 literal? → No: el cuerpo uniforme aplica a lo que responde la API; lo que genera API Gateway conserva su formato (2.3 reformulado).
- 2026-11-01: HTTP API corta las integraciones a los 30 s y Aurora tarda 30 s o más en reanudar tras más de 24 h en pausa. ¿Cómo se mide NFR-2? → 200 en ≤ 60 s sumando los reintentos, con cada petición por debajo de 30 s (NFR-2 reformulado).
- 2026-11-01: ¿Cuánto dura el refresh token del cliente web? → 1 día (el del colector sigue en 30 días por `T-7`).
- 2026-11-01: ¿La spec documenta el contrato de la API? → Sí: contrato OpenAPI 3.1 de la spec (`openapi.yaml`), conforme con el que genera FastAPI, y referencia publicada en `docs/api/` (NFR-6).
- 2026-11-01: Corrección de 2.3: AWS no documenta el código exacto que devuelve HTTP API por timeout ni el cuerpo de un rechazo IAM; la redacción ya no fija esos códigos y la verificación manual registra los observados.
- 2026-11-02: El pipeline usa RDS Data API para el bootstrap SQL. ¿Contradice el Out of Scope? → No: queda fuera como ruta de datos de la API (ADR 0004); el pipeline la usa solo para crear roles, el esquema y permisos (D3, ADR 0007).
