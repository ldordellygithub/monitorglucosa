"""Construcción del contrato OpenAPI 3.1 de monitorglucosa (D16, NFR-6).

Parte del esquema que genera FastAPI desde las rutas reales y añade lo que FastAPI no
puede inferir: `servers`, descripción de `info`, `tags`, `securitySchemes`, cabeceras
(`x-request-id`, `Retry-After`) y respuestas generadas por API Gateway.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, get_args

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from src.api.errors import ErrorCode

API_TITLE = "monitorglucosa API"
API_VERSION = "0.1.0"
API_SUMMARY = (
    "API personal de seguimiento de glucemia. Fase 1a, plataforma y autenticación."
)
API_DESCRIPTION = """\
API de un solo usuario (el propietario). Esta versión no maneja lecturas de glucemia: \
expone las comprobaciones de salud y la identidad autenticada, sobre las que se \
construyen las specs siguientes.

## Autenticación
- Las rutas de `/api/v1` exigen un **access token de Amazon Cognito** en \
`Authorization: Bearer <token>`. API Gateway valida firma, emisor, `client_id` \
(clientes `web` y `collector`), expiración y el ámbito `openid`, y la API exige además \
`token_use = access`: un ID token nunca sirve de credencial.
- `GET /health/ready` exige una firma **AWS SigV4** (servicio `execute-api`). Solo la \
usa la prueba de humo.
- `GET /health` es pública y nunca toca la base de datos.

## Errores
- Lo que responde la API usa siempre el cuerpo `ErrorBody` (`code`, `message`, \
`details`). Los códigos son estables y nunca incluyen el valor recibido, trazas ni \
detalles internos.
- Lo que responde **API Gateway sin invocar la API** (rechazo del autorizador o de la \
firma, throttling, fallo o timeout de la integración) usa el cuerpo \
`ApiGatewayMessage`. Los clientes lo distinguen por el código HTTP y por la ausencia \
de `x-request-id`.
- Una ruta inexistente dentro de `/api/v1` con token válido responde 404 `NOT_FOUND`, \
y un método no soportado responde 405 `METHOD_NOT_ALLOWED`, ambos con `ErrorBody`. \
Sin token, API Gateway responde antes con 401. Fuera de `/health`, `/health/ready` y \
`/api/v1`, responde API Gateway con 404.

## Base de datos en pausa
Aurora se pausa tras 300 s sin conexiones. La primera petición que necesita la base de \
datos puede recibir 503 `DATABASE_UNAVAILABLE` con `Retry-After`. El cliente reintenta \
respetando esa cabecera, durante 60 s como máximo en total. Ninguna petición \
individual supera los 30 s (límite de API Gateway).

## Límites
Throttling global de 10 peticiones/s con ráfagas de 20 (429 de API Gateway). CORS solo \
para el origen de CloudFront del sitio, métodos `GET`, cabeceras `authorization` y \
`content-type`, sin credenciales.

## Convenciones
Campos JSON en `snake_case`. Fechas en ISO 8601 con zona horaria (las primeras llegan \
con la spec de lecturas). Toda respuesta de la API incluye `x-request-id`, que también \
aparece en los logs.
"""

API_SERVERS: list[dict[str, Any]] = [
    {
        "url": "https://{apiId}.execute-api.us-east-1.amazonaws.com",
        "description": (
            "Producción (AWS us-east-1). El identificador sale del output "
            "`api_endpoint` de Terraform."
        ),
        "variables": {
            "apiId": {
                "default": "apiId",
                "description": (
                    "Identificador de la HTTP API (no es un secreto, pero no se "
                    "versiona)."
                ),
            }
        },
    },
    {
        "url": "http://localhost:8000",
        "description": (
            "Entorno local con Docker Compose (emisor JWT de pruebas en lugar de "
            "Cognito; sin SigV4)."
        ),
    },
]

API_TAGS: list[dict[str, Any]] = [
    {
        "name": "salud",
        "description": (
            "Comprobaciones de disponibilidad de la API y de la base de datos."
        ),
    },
    {
        "name": "identidad",
        "description": "Identidad del usuario autenticado.",
    },
]

SECURITY_SCHEMES: dict[str, dict[str, Any]] = {
    "cognitoAccessToken": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Access token de Amazon Cognito (user pool de monitorglucosa, plan "
            "Essentials, MFA TOTP obligatorio), obtenido con el flujo de código de "
            "autorización y PKCE (S256) por el cliente `web` o `collector`. Dura 60 "
            "minutos. Debe incluir el ámbito `openid` y `token_use = access`. En "
            "local lo emite `dev/jwt-issuer`."
        ),
    },
    "awsSigV4": {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization",
        "description": (
            "Firma AWS Signature Version 4 para el servicio `execute-api` en "
            "`us-east-1`. Solo el rol de despliegue tiene `execute-api:Invoke` sobre "
            "`GET /health/ready`."
        ),
    },
}

REUSABLE_HEADERS: dict[str, dict[str, Any]] = {
    "XRequestId": {
        "description": (
            "Identificador de correlación de la petición: el `requestId` de API "
            "Gateway en producción, o un UUID4 en local. Se ignora el valor que "
            "envíe el cliente. Solo lo llevan las respuestas generadas por la API."
        ),
        "schema": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "example": "0b1f6c52-3a9e-4e0d-8f57-2c4d9a7e1b30",
    },
    "RetryAfter": {
        "description": "Segundos que el cliente debe esperar antes de reintentar.",
        "schema": {
            "type": "integer",
            "minimum": 1,
        },
        "example": 5,
    },
}

SHARED_SCHEMAS: dict[str, dict[str, Any]] = {
    "ErrorCode": {
        "type": "string",
        "description": (
            "Código estable en UPPER_SNAKE_CASE. Las specs siguientes añaden códigos "
            "(por ejemplo `READING_INVALID`); nunca se reutiliza ni se cambia el "
            "significado de uno existente."
        ),
        "enum": list(get_args(ErrorCode)),
    },
    "ErrorDetail": {
        "type": "object",
        "additionalProperties": False,
        "required": ["field", "problem"],
        "properties": {
            "field": {
                "type": "string",
                "description": (
                    "Ubicación del problema, por ejemplo `query.limit` o `body.value`."
                ),
            },
            "problem": {
                "type": "string",
                "description": (
                    "Problema en español, sin el valor recibido. Valores actuales: "
                    "«obligatorio», «tipo no válido», «longitud no válida», "
                    "«fuera de rango», «formato no válido» y «valor no válido»."
                ),
            },
        },
    },
    "ErrorBody": {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "message", "details"],
        "properties": {
            "code": {"$ref": "#/components/schemas/ErrorCode"},
            "message": {
                "type": "string",
                "description": "Mensaje en español para la persona usuaria.",
            },
            "details": {
                "type": "array",
                "description": "Vacío salvo en los errores de validación.",
                "items": {"$ref": "#/components/schemas/ErrorDetail"},
            },
        },
    },
    "ApiGatewayMessage": {
        "type": "object",
        "required": ["message"],
        "properties": {
            "message": {"type": "string"},
        },
        "description": (
            "Cuerpo que genera API Gateway cuando responde sin invocar la API. La API "
            "no lo controla: HTTP API no permite personalizarlo (solo las REST API "
            "tienen *gateway responses*). El texto exacto puede cambiar; los clientes "
            "deciden por el código HTTP."
        ),
    },
}

REUSABLE_RESPONSES: dict[str, dict[str, Any]] = {
    "ValidationError": {
        "description": (
            "La petición no supera la validación. Ninguna ruta de esta spec recibe "
            "parámetros; el contrato aplica a las rutas con cuerpo, query o ruta que "
            "añadan las specs siguientes (criterio 2.3)."
        ),
        "headers": {
            "x-request-id": {"$ref": "#/components/headers/XRequestId"},
        },
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorBody"},
                "example": {
                    "code": "VALIDATION_ERROR",
                    "message": "La petición no es válida.",
                    "details": [{"field": "query.limit", "problem": "fuera de rango"}],
                },
            }
        },
    },
    "Unauthenticated": {
        "description": (
            "Sin identidad válida. API Gateway rechaza los tokens ausentes, mal "
            "firmados, caducados, de otro emisor o de otro cliente "
            "(`ApiGatewayMessage`, sin `x-request-id`). La API rechaza los que llegan "
            "sin claims o con `token_use` distinto de `access` (`ErrorBody`)."
        ),
        "content": {
            "application/json": {
                "schema": {
                    "anyOf": [
                        {"$ref": "#/components/schemas/ErrorBody"},
                        {"$ref": "#/components/schemas/ApiGatewayMessage"},
                    ]
                },
                "examples": {
                    "api": {
                        "summary": "Rechazo de la API",
                        "value": {
                            "code": "UNAUTHENTICATED",
                            "message": "Se requiere autenticación.",
                            "details": [],
                        },
                    },
                    "gateway": {
                        "summary": "Rechazo del autorizador JWT (texto orientativo)",
                        "value": {"message": "Unauthorized"},
                    },
                },
            }
        },
    },
    "GatewayForbidden": {
        "description": (
            "API Gateway deniega la petición: falta la firma SigV4 o no es válida, "
            "el firmante no tiene `execute-api:Invoke`, o el token no incluye el "
            "ámbito `openid` (por ejemplo, un ID token)."
        ),
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiGatewayMessage"},
                "example": {"message": "Forbidden"},
            }
        },
    },
    "Throttled": {
        "description": (
            "Se superó el throttling global (10 peticiones/s, ráfagas de 20). "
            "Reintentar con backoff."
        ),
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiGatewayMessage"},
                "example": {"message": "Too Many Requests"},
            }
        },
    },
    "InternalError": {
        "description": (
            "Error interno. La API responde `INTERNAL_ERROR` sin detalles; si la "
            "función falla antes de responder, API Gateway devuelve su propio cuerpo."
        ),
        "content": {
            "application/json": {
                "schema": {
                    "anyOf": [
                        {"$ref": "#/components/schemas/ErrorBody"},
                        {"$ref": "#/components/schemas/ApiGatewayMessage"},
                    ]
                },
                "examples": {
                    "api": {
                        "summary": "Error controlado por la API",
                        "value": {
                            "code": "INTERNAL_ERROR",
                            "message": "Error interno.",
                            "details": [],
                        },
                    },
                    "gateway": {
                        "summary": "La función falló antes de responder",
                        "value": {"message": "Internal Server Error"},
                    },
                },
            }
        },
    },
    "GatewayUnavailable": {
        "description": (
            "La integración no respondió a tiempo o no estaba disponible (por "
            "ejemplo, la función superó los 30 s o estaba `Inactive` tras semanas "
            "sin uso). Reintentar."
        ),
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiGatewayMessage"},
                "example": {"message": "Service Unavailable"},
            }
        },
    },
    "DatabaseUnavailable": {
        "description": (
            "La base de datos no respondió en 20 s, normalmente porque se está "
            "despertando (`ErrorBody` con `Retry-After`), o la integración superó "
            "el límite de API Gateway (`ApiGatewayMessage`). Reintentar respetando "
            "`Retry-After`, hasta 60 s en total."
        ),
        "headers": {
            "Retry-After": {"$ref": "#/components/headers/RetryAfter"},
            "x-request-id": {"$ref": "#/components/headers/XRequestId"},
        },
        "content": {
            "application/json": {
                "schema": {
                    "anyOf": [
                        {"$ref": "#/components/schemas/ErrorBody"},
                        {"$ref": "#/components/schemas/ApiGatewayMessage"},
                    ]
                },
                "examples": {
                    "api": {
                        "summary": "Aurora se está despertando",
                        "value": {
                            "code": "DATABASE_UNAVAILABLE",
                            "message": (
                                "La base de datos se está despertando. "
                                "Reintenta en unos segundos."
                            ),
                            "details": [],
                        },
                    },
                    "gateway": {
                        "summary": "Timeout de la integración",
                        "value": {"message": "Service Unavailable"},
                    },
                },
            }
        },
    },
}

SCHEMA_RENAMES: dict[str, str] = {
    "HealthResponse": "HealthStatus",
    "ReadinessResponse": "ReadinessStatus",
    "MeResponse": "Me",
}

OPERATION_OVERRIDES: dict[str, dict[str, Any]] = {
    "getHealth": {
        "200_description": "La API está viva.",
        "200_example": {"status": "ok"},
        "extra_responses": {
            "429": {"$ref": "#/components/responses/Throttled"},
            "500": {"$ref": "#/components/responses/InternalError"},
            "503": {"$ref": "#/components/responses/GatewayUnavailable"},
        },
    },
    "getReadiness": {
        "200_description": "La base de datos responde.",
        "200_example": {"status": "ready"},
        "extra_responses": {
            "403": {"$ref": "#/components/responses/GatewayForbidden"},
            "429": {"$ref": "#/components/responses/Throttled"},
            "500": {"$ref": "#/components/responses/InternalError"},
            "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
        },
    },
    "getCurrentIdentity": {
        "200_description": "Identidad del usuario autenticado.",
        "200_example": {"sub": "8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f"},
        "extra_responses": {
            "401": {"$ref": "#/components/responses/Unauthenticated"},
            "403": {"$ref": "#/components/responses/GatewayForbidden"},
            "429": {"$ref": "#/components/responses/Throttled"},
            "500": {"$ref": "#/components/responses/InternalError"},
            "503": {"$ref": "#/components/responses/GatewayUnavailable"},
        },
    },
}


def _rewrite_refs(node: Any, renames: dict[str, str]) -> Any:
    """Reescribe referencias `$ref` tras renombrar esquemas de Pydantic."""
    if isinstance(node, dict):
        rewritten: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                prefix = "#/components/schemas/"
                if value.startswith(prefix):
                    target = value[len(prefix) :]
                    value = prefix + renames.get(target, target)
            rewritten[key] = _rewrite_refs(value, renames)
        return rewritten
    if isinstance(node, list):
        return [_rewrite_refs(item, renames) for item in node]
    return node


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """Construye y cachea el contrato OpenAPI 3.1 completo de la aplicación."""
    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = get_openapi(
        title=API_TITLE,
        version=API_VERSION,
        summary=API_SUMMARY,
        description=API_DESCRIPTION,
        routes=app.routes,
        tags=API_TAGS,
    )
    schema["openapi"] = "3.1.0"
    schema["servers"] = deepcopy(API_SERVERS)

    components = schema.setdefault("components", {})
    raw_schemas: dict[str, Any] = components.get("schemas", {})

    # Renombrar los modelos Pydantic a los nombres públicos del contrato y retirar
    # los esquemas de error por defecto de FastAPI (sustituidos por ErrorBody).
    renamed_schemas: dict[str, Any] = {}
    for name, definition in raw_schemas.items():
        if name in {"HTTPValidationError", "ValidationError"}:
            continue
        public_name = SCHEMA_RENAMES.get(name, name)
        renamed_schemas[public_name] = definition

    for shared_name, shared_def in SHARED_SCHEMAS.items():
        renamed_schemas[shared_name] = deepcopy(shared_def)

    components["schemas"] = renamed_schemas
    components["securitySchemes"] = deepcopy(SECURITY_SCHEMES)
    components["headers"] = deepcopy(REUSABLE_HEADERS)
    components["responses"] = deepcopy(REUSABLE_RESPONSES)

    rewritten = _rewrite_refs(schema, SCHEMA_RENAMES)
    if not isinstance(rewritten, dict):
        raise TypeError("El esquema OpenAPI generado debe ser un objeto JSON")
    schema = rewritten

    # Completar cada operación generada por FastAPI con cabeceras, ejemplos y
    # respuestas de error/gateway.
    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId")
            responses: dict[str, Any] = operation.setdefault("responses", {})
            # En rutas sin parámetros ni cuerpo retiramos el 422 de FastAPI; en rutas
            # con entrada lo mapeamos a nuestra respuesta uniforme ValidationError.
            if not operation.get("parameters") and "requestBody" not in operation:
                responses.pop("422", None)
            elif "422" in responses:
                responses["422"] = {"$ref": "#/components/responses/ValidationError"}

            ok_response = responses.get("200")
            if isinstance(ok_response, dict):
                ok_response["headers"] = {
                    "x-request-id": {"$ref": "#/components/headers/XRequestId"}
                }
                override = OPERATION_OVERRIDES.get(str(op_id), {})
                if "200_description" in override:
                    ok_response["description"] = override["200_description"]
                json_content = ok_response.get("content", {}).get("application/json")
                if isinstance(json_content, dict) and "200_example" in override:
                    json_content["example"] = deepcopy(override["200_example"])

            override = OPERATION_OVERRIDES.get(str(op_id), {})
            for status_code, resp_ref in override.get("extra_responses", {}).items():
                responses[status_code] = deepcopy(resp_ref)

    app.openapi_schema = schema
    return schema
