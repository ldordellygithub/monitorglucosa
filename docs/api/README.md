<!-- Archivo generado por backend/tools/export_openapi.py. No editar a mano. -->

# monitorglucosa API (`v0.1.0`)

> API personal de seguimiento de glucemia. Fase 1a, plataforma y autenticación.

- **Contrato OpenAPI 3.1 (fuente de verdad):** [`backend/openapi.json`](../../backend/openapi.json)
- **Swagger UI / ReDoc:** disponibles en `/docs` y `/redoc` en `local` y `test`; desactivados en `prod` (D17).

API de un solo usuario (el propietario). Esta versión no maneja lecturas de glucemia: expone las comprobaciones de salud y la identidad autenticada, sobre las que se construyen las specs siguientes.

## Autenticación
- Las rutas de `/api/v1` exigen un **access token de Amazon Cognito** en `Authorization: Bearer <token>`. API Gateway valida firma, emisor, `client_id` (clientes `web` y `collector`), expiración y el ámbito `openid`, y la API exige además `token_use = access`: un ID token nunca sirve de credencial.
- `GET /health/ready` exige una firma **AWS SigV4** (servicio `execute-api`). Solo la usa la prueba de humo.
- `GET /health` es pública y nunca toca la base de datos.

## Errores
- Lo que responde la API usa siempre el cuerpo `ErrorBody` (`code`, `message`, `details`). Los códigos son estables y nunca incluyen el valor recibido, trazas ni detalles internos.
- Lo que responde **API Gateway sin invocar la API** (rechazo del autorizador o de la firma, throttling, fallo o timeout de la integración) usa el cuerpo `ApiGatewayMessage`. Los clientes lo distinguen por el código HTTP y por la ausencia de `x-request-id`.
- Una ruta inexistente dentro de `/api/v1` con token válido responde 404 `NOT_FOUND`, y un método no soportado responde 405 `METHOD_NOT_ALLOWED`, ambos con `ErrorBody`. Sin token, API Gateway responde antes con 401. Fuera de `/health`, `/health/ready` y `/api/v1`, responde API Gateway con 404.

## Base de datos en pausa
Aurora se pausa tras 300 s sin conexiones. La primera petición que necesita la base de datos puede recibir 503 `DATABASE_UNAVAILABLE` con `Retry-After`. El cliente reintenta respetando esa cabecera, durante 60 s como máximo en total. Ninguna petición individual supera los 30 s (límite de API Gateway).

## Límites
Throttling global de 10 peticiones/s con ráfagas de 20 (429 de API Gateway). CORS solo para el origen de CloudFront del sitio, métodos `GET`, cabeceras `authorization` y `content-type`, sin credenciales.

## Convenciones
Campos JSON en `snake_case`. Fechas en ISO 8601 con zona horaria (las primeras llegan con la spec de lecturas). Toda respuesta de la API incluye `x-request-id`, que también aparece en los logs.

## Servidores

| URL | Descripción |
| --- | --- |
| `https://{apiId}.execute-api.us-east-1.amazonaws.com` | Producción (AWS us-east-1). El identificador sale del output `api_endpoint` de Terraform. |
| `http://localhost:8000` | Entorno local con Docker Compose (emisor JWT de pruebas en lugar de Cognito; sin SigV4). |

## Esquemas de seguridad

| Esquema | Tipo | Descripción |
| --- | --- | --- |
| `awsSigV4` | `apiKey` | Firma AWS Signature Version 4 para el servicio `execute-api` en `us-east-1`. Solo el rol de despliegue tiene `execute-api:Invoke` sobre `GET /health/ready`. |
| `cognitoAccessToken` | `http (bearer)` | Access token de Amazon Cognito (user pool de monitorglucosa, plan Essentials, MFA TOTP obligatorio), obtenido con el flujo de código de autorización y PKCE (S256) por el cliente `web` o `collector`. Dura 60 minutos. Debe incluir el ámbito `openid` y `token_use = access`. En local lo emite `dev/jwt-issuer`. |

## Operaciones

| Operación | Método y ruta | Seguridad | Criterios | Resumen |
| --- | --- | --- | --- | --- |
| `getCurrentIdentity` | `GET /api/v1/me` | `cognitoAccessToken` | 3.1, 3.2, 3.3, 3.5, 4.5 | Obtener la identidad del usuario autenticado |
| `getHealth` | `GET /health` | Pública (sin autenticación) | 2.1, 6.2 | Comprobar que la API está viva |
| `getReadiness` | `GET /health/ready` | `awsSigV4` | 2.2, 6.2, 7.5, NFR-2 | Comprobar que la API llega a la base de datos |

### `GET /api/v1/me` (`getCurrentIdentity`)

Devuelve solo el identificador estable del usuario (claim `sub` de Cognito).
Sirve para comprobar la cadena de autenticación completa:
cliente → Cognito → API Gateway → API. No toca la base de datos.

- **Seguridad:** `cognitoAccessToken`
- **Etiquetas:** identidad
- **Requisitos:** 3.1, 3.2, 3.3, 3.5, 4.5

| Código | Esquema | Cabeceras | Descripción |
| --- | --- | --- | --- |
| `200` | `Me` | `x-request-id` | Identidad del usuario autenticado. |
| `401` | `ErrorBody` \| `ApiGatewayMessage` | — | Sin identidad válida. API Gateway rechaza los tokens ausentes, mal firmados, caducados, de otro emisor o de otro cliente (`ApiGatewayMessage`, sin `x-request-id`). La API rechaza los que llegan sin claims o con `token_use` distinto de `access` (`ErrorBody`). |
| `403` | `ApiGatewayMessage` | — | API Gateway deniega la petición: falta la firma SigV4 o no es válida, el firmante no tiene `execute-api:Invoke`, o el token no incluye el ámbito `openid` (por ejemplo, un ID token). |
| `429` | `ApiGatewayMessage` | — | Se superó el throttling global (10 peticiones/s, ráfagas de 20). Reintentar con backoff. |
| `500` | `ErrorBody` \| `ApiGatewayMessage` | — | Error interno. La API responde `INTERNAL_ERROR` sin detalles; si la función falla antes de responder, API Gateway devuelve su propio cuerpo. |
| `503` | `ApiGatewayMessage` | — | La integración no respondió a tiempo o no estaba disponible (por ejemplo, la función superó los 30 s o estaba `Inactive` tras semanas sin uso). Reintentar. |

**Ejemplos de respuesta:**

- `200` — Ejemplo:

```json
{
  "sub": "8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f"
}
```

- `401` — Rechazo de la API:

```json
{
  "code": "UNAUTHENTICATED",
  "message": "Se requiere autenticación.",
  "details": []
}
```

- `401` — Rechazo del autorizador JWT (texto orientativo):

```json
{
  "message": "Unauthorized"
}
```

- `403` — Ejemplo:

```json
{
  "message": "Forbidden"
}
```

- `429` — Ejemplo:

```json
{
  "message": "Too Many Requests"
}
```

- `500` — Error controlado por la API:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Error interno.",
  "details": []
}
```

- `500` — La función falló antes de responder:

```json
{
  "message": "Internal Server Error"
}
```

- `503` — Ejemplo:

```json
{
  "message": "Service Unavailable"
}
```

### `GET /health` (`getHealth`)

Responde sin abrir ninguna conexión a la base de datos, así que nunca
despierta Aurora. Lambda Web Adapter la usa como comprobación de arranque.
Pública.

- **Seguridad:** Pública (sin autenticación)
- **Etiquetas:** salud
- **Requisitos:** 2.1, 6.2

| Código | Esquema | Cabeceras | Descripción |
| --- | --- | --- | --- |
| `200` | `HealthStatus` | `x-request-id` | La API está viva. |
| `429` | `ApiGatewayMessage` | — | Se superó el throttling global (10 peticiones/s, ráfagas de 20). Reintentar con backoff. |
| `500` | `ErrorBody` \| `ApiGatewayMessage` | — | Error interno. La API responde `INTERNAL_ERROR` sin detalles; si la función falla antes de responder, API Gateway devuelve su propio cuerpo. |
| `503` | `ApiGatewayMessage` | — | La integración no respondió a tiempo o no estaba disponible (por ejemplo, la función superó los 30 s o estaba `Inactive` tras semanas sin uso). Reintentar. |

**Ejemplos de respuesta:**

- `200` — Ejemplo:

```json
{
  "status": "ok"
}
```

- `429` — Ejemplo:

```json
{
  "message": "Too Many Requests"
}
```

- `500` — Error controlado por la API:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Error interno.",
  "details": []
}
```

- `500` — La función falló antes de responder:

```json
{
  "message": "Internal Server Error"
}
```

- `503` — Ejemplo:

```json
{
  "message": "Service Unavailable"
}
```

### `GET /health/ready` (`getReadiness`)

Ejecuta `SELECT 1` con una conexión propia que se cierra al terminar.
Si Aurora está en pausa, la petición la despierta. Exige SigV4 en producción;
en local no hay autorización.

- **Seguridad:** `awsSigV4`
- **Etiquetas:** salud
- **Requisitos:** 2.2, 6.2, 7.5, NFR-2

| Código | Esquema | Cabeceras | Descripción |
| --- | --- | --- | --- |
| `200` | `ReadinessStatus` | `x-request-id` | La base de datos responde. |
| `403` | `ApiGatewayMessage` | — | API Gateway deniega la petición: falta la firma SigV4 o no es válida, el firmante no tiene `execute-api:Invoke`, o el token no incluye el ámbito `openid` (por ejemplo, un ID token). |
| `429` | `ApiGatewayMessage` | — | Se superó el throttling global (10 peticiones/s, ráfagas de 20). Reintentar con backoff. |
| `500` | `ErrorBody` \| `ApiGatewayMessage` | — | Error interno. La API responde `INTERNAL_ERROR` sin detalles; si la función falla antes de responder, API Gateway devuelve su propio cuerpo. |
| `503` | `ErrorBody` \| `ApiGatewayMessage` | `Retry-After`, `x-request-id` | La base de datos no respondió en 20 s, normalmente porque se está despertando (`ErrorBody` con `Retry-After`), o la integración superó el límite de API Gateway (`ApiGatewayMessage`). Reintentar respetando `Retry-After`, hasta 60 s en total. |

**Ejemplos de respuesta:**

- `200` — Ejemplo:

```json
{
  "status": "ready"
}
```

- `403` — Ejemplo:

```json
{
  "message": "Forbidden"
}
```

- `429` — Ejemplo:

```json
{
  "message": "Too Many Requests"
}
```

- `500` — Error controlado por la API:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Error interno.",
  "details": []
}
```

- `500` — La función falló antes de responder:

```json
{
  "message": "Internal Server Error"
}
```

- `503` — Aurora se está despertando:

```json
{
  "code": "DATABASE_UNAVAILABLE",
  "message": "La base de datos se está despertando. Reintenta en unos segundos.",
  "details": []
}
```

- `503` — Timeout de la integración:

```json
{
  "message": "Service Unavailable"
}
```

## Catálogo de códigos de error (`ErrorCode`)

Todas las respuestas de error generadas por la API usan `ErrorBody` (`code`, `message`, `details`) y nunca repiten valores de entrada:

- `VALIDATION_ERROR`
- `UNAUTHENTICATED`
- `NOT_FOUND`
- `METHOD_NOT_ALLOWED`
- `DATABASE_UNAVAILABLE`
- `INTERNAL_ERROR`

## Esquemas

### `ApiGatewayMessage`

```json
{
  "description": "Cuerpo que genera API Gateway cuando responde sin invocar la API. La API no lo controla: HTTP API no permite personalizarlo (solo las REST API tienen *gateway responses*). El texto exacto puede cambiar; los clientes deciden por el código HTTP.",
  "properties": {
    "message": {
      "type": "string"
    }
  },
  "required": [
    "message"
  ],
  "type": "object"
}
```

### `ErrorBody`

```json
{
  "additionalProperties": false,
  "properties": {
    "code": {
      "$ref": "#/components/schemas/ErrorCode"
    },
    "details": {
      "description": "Vacío salvo en los errores de validación.",
      "items": {
        "$ref": "#/components/schemas/ErrorDetail"
      },
      "type": "array"
    },
    "message": {
      "description": "Mensaje en español para la persona usuaria.",
      "type": "string"
    }
  },
  "required": [
    "code",
    "message",
    "details"
  ],
  "type": "object"
}
```

### `ErrorCode`

```json
{
  "description": "Código estable en UPPER_SNAKE_CASE. Las specs siguientes añaden códigos (por ejemplo `READING_INVALID`); nunca se reutiliza ni se cambia el significado de uno existente.",
  "enum": [
    "VALIDATION_ERROR",
    "UNAUTHENTICATED",
    "NOT_FOUND",
    "METHOD_NOT_ALLOWED",
    "DATABASE_UNAVAILABLE",
    "INTERNAL_ERROR"
  ],
  "type": "string"
}
```

### `ErrorDetail`

```json
{
  "additionalProperties": false,
  "properties": {
    "field": {
      "description": "Ubicación del problema, por ejemplo `query.limit` o `body.value`.",
      "type": "string"
    },
    "problem": {
      "description": "Problema en español, sin el valor recibido. Valores actuales: «obligatorio», «tipo no válido», «longitud no válida», «fuera de rango», «formato no válido» y «valor no válido».",
      "type": "string"
    }
  },
  "required": [
    "field",
    "problem"
  ],
  "type": "object"
}
```

### `HealthStatus`

```json
{
  "additionalProperties": false,
  "properties": {
    "status": {
      "const": "ok",
      "title": "Status",
      "type": "string"
    }
  },
  "required": [
    "status"
  ],
  "title": "HealthResponse",
  "type": "object"
}
```

### `Me`

```json
{
  "additionalProperties": false,
  "properties": {
    "sub": {
      "description": "Identificador estable del usuario en Cognito (claim `sub`). No es un dato de salud.",
      "format": "uuid",
      "title": "Sub",
      "type": "string"
    }
  },
  "required": [
    "sub"
  ],
  "title": "MeResponse",
  "type": "object"
}
```

### `ReadinessStatus`

```json
{
  "additionalProperties": false,
  "properties": {
    "status": {
      "const": "ready",
      "title": "Status",
      "type": "string"
    }
  },
  "required": [
    "status"
  ],
  "title": "ReadinessResponse",
  "type": "object"
}
```

## Índice de contratos por spec (`openapi.yaml`)

| Spec | Contrato de diseño |
| --- | --- |
| `fase-1a-infraestructura-y-auth` | [`openapi.yaml`](../../.kiro/specs/fase-1a-infraestructura-y-auth/openapi.yaml) |
