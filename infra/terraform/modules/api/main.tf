# Lambdas api y migrator (imagen única en ECR por digest inmutable) y API Gateway HTTP API
# con autorizador JWT de Cognito (ámbito openid), ruta pública /health, ruta IAM /health/ready,
# throttling 10/20, CORS restringido a CloudFront y logs de acceso JSON sin PII
# (Requisitos 4.5, 6.1, 6.2, 6.3, 6.5, 8.2; D2, D7, D9, D13, ADR 0005, ADR 0006).

locals {
  create_api_lambda      = var.api_image_digest != null
  create_migrator_lambda = var.migrator_image_digest != null

  # Formato JSON de logs de acceso de API Gateway (design.md):
  # solo metadatos técnicos, sin cabeceras, IP ni query string (NFR-5).
  access_log_format = jsonencode({
    requestId       = "$context.requestId"
    routeKey        = "$context.routeKey"
    status          = "$context.status"
    responseLatency = "$context.responseLatency"
    authorizerError = "$context.authorizer.error"
  })
}

# ---------------------------------------------------------------------------
# Lambdas dentro de la VPC privada (imagen única identificada por digest)
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "api" {
  # checkov:skip=CKV_AWS_50:Sin X-Ray en esta spec por presupuesto y simplicidad (NFR-3); trazabilidad mediante request_id JSON.
  # checkov:skip=CKV_AWS_115:Sin concurrencia reservada por decisión D13 (cuota de cuenta nueva y throttling 10/20 en API Gateway).
  # checkov:skip=CKV_AWS_116:Invocación síncrona desde HTTP API; una DLQ no aplica a invocaciones síncronas.
  # checkov:skip=CKV_AWS_173:Ninguna variable de entorno contiene secretos (T-11); Lambda cifra en reposo con clave gestionada por AWS.
  # checkov:skip=CKV_AWS_272:Imagen de contenedor inmutable desplegada por digest SHA-256 desde ECR; AWS Code Signing solo aplica a paquetes ZIP.
  count = local.create_api_lambda ? 1 : 0

  function_name = local.api_function_name
  description   = "API HTTP de monitorglucosa (FastAPI + Lambda Web Adapter, imagen por digest)."
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repository_url}@${var.api_image_digest}"
  architectures = ["x86_64"]
  memory_size   = 512
  timeout       = 30

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.api_security_group_id]
  }

  environment {
    variables = {
      ENVIRONMENT                  = "prod"
      DATABASE_HOST                = var.database_host
      DATABASE_PORT                = tostring(var.database_port)
      DATABASE_NAME                = var.database_name
      DATABASE_USER                = "mg_api"
      DATABASE_CONNECT_TIMEOUT_S   = "20"
      LOG_LEVEL                    = "INFO"
      AWS_LWA_READINESS_CHECK_PATH = "/health"
    }
  }

  depends_on = [aws_iam_role_policy.api]
}

resource "aws_lambda_function" "migrator" {
  # checkov:skip=CKV_AWS_50:Sin X-Ray en esta spec por presupuesto y simplicidad (NFR-3).
  # checkov:skip=CKV_AWS_115:Sin concurrencia reservada por decisión D13; invocada únicamente por el job deploy (concurrency: deploy-prod).
  # checkov:skip=CKV_AWS_116:Invocación síncrona desde scripts/deploy.py (D2, ADR 0006); sin cola asíncrona.
  # checkov:skip=CKV_AWS_173:Ninguna variable de entorno contiene secretos (T-11); autenticación IAM contra Aurora.
  # checkov:skip=CKV_AWS_272:Imagen de contenedor inmutable desplegada por digest SHA-256 desde ECR; AWS Code Signing solo aplica a paquetes ZIP.
  count = local.create_migrator_lambda ? 1 : 0

  function_name = local.migrator_function_name
  description   = "Migrador Alembic dentro de la VPC (misma imagen que api con create_migrator_app; ADR 0006)."
  role          = aws_iam_role.migrator.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repository_url}@${var.migrator_image_digest}"
  architectures = ["x86_64"]
  memory_size   = 512
  timeout       = 300

  image_config {
    command = [
      "/app/.venv/bin/uvicorn",
      "src.main:create_migrator_app",
      "--factory",
      "--host",
      "0.0.0.0",
      "--port",
      "8080",
      "--no-access-log",
    ]
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.migrator_security_group_id]
  }

  environment {
    variables = {
      ENVIRONMENT                  = "prod"
      DATABASE_HOST                = var.database_host
      DATABASE_PORT                = tostring(var.database_port)
      DATABASE_NAME                = var.database_name
      DATABASE_USER                = "mg_migrator"
      DATABASE_CONNECT_TIMEOUT_S   = "20"
      LOG_LEVEL                    = "INFO"
      AWS_LWA_READINESS_CHECK_PATH = "/"
      AWS_LWA_PASS_THROUGH_PATH    = "/events"
    }
  }

  depends_on = [aws_iam_role_policy.migrator]
}

# ---------------------------------------------------------------------------
# API Gateway HTTP API v2 (JWT Cognito, IAM /health/ready, throttling, CORS)
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project}-api"
  description   = "HTTP API de monitorglucosa (JWT Cognito en /api/v1, IAM en /health/ready, CORS CloudFront)."
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins     = ["https://${var.site_domain}"]
    allow_methods     = ["GET"]
    allow_headers     = ["authorization", "content-type"]
    allow_credentials = false
    max_age           = 3600
  }
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.main.id
  name             = "${var.project}-cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer = var.cognito_issuer
    audience = [
      var.cognito_web_client_id,
      var.cognito_collector_client_id,
    ]
  }
}

resource "aws_apigatewayv2_integration" "api" {
  count = local.create_api_lambda ? 1 : 0

  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.api[0].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}

# Rutas protegidas por el autorizador JWT de Cognito y ámbito openid (Requisitos 4.5, 6.2; D9).
# Se declara método explícito GET (en lugar de ANY) para alinear con D13 (allow_methods = ["GET"])
# y evitar que HTTP API v2 intercepte las peticiones preflight CORS OPTIONS con el autorizador JWT
# devolviendo 401; cada spec posterior añade sus métodos explícitos aquí y en cors_configuration.
resource "aws_apigatewayv2_route" "api_v1" {
  count = local.create_api_lambda ? 1 : 0

  api_id               = aws_apigatewayv2_api.main.id
  route_key            = "GET /api/v1/{proxy+}"
  target               = "integrations/${aws_apigatewayv2_integration.api[0].id}"
  authorization_type   = "JWT"
  authorizer_id        = aws_apigatewayv2_authorizer.cognito.id
  authorization_scopes = ["openid"]
}

# Ruta pública /health sin acceso a BD (Requisitos 2.1, 6.2).
resource "aws_apigatewayv2_route" "health" {
  # checkov:skip=CKV_AWS_309:Requisitos 2.1 y 6.2: GET /health es la ruta pública de liveness sin acceso a BD ni datos sensibles.
  count = local.create_api_lambda ? 1 : 0

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /health"
  target             = "integrations/${aws_apigatewayv2_integration.api[0].id}"
  authorization_type = "NONE"
}

# Ruta de disponibilidad /health/ready protegida con firma SigV4 IAM (Requisitos 2.2, 6.2, 7.5).
resource "aws_apigatewayv2_route" "health_ready" {
  count = local.create_api_lambda ? 1 : 0

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /health/ready"
  target             = "integrations/${aws_apigatewayv2_integration.api[0].id}"
  authorization_type = "AWS_IAM"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit    = 10
    throttling_burst_limit   = 20
    detailed_metrics_enabled = false
  }

  access_log_settings {
    destination_arn = var.access_log_group_arn
    format          = local.access_log_format
  }
}

# Permiso explícito de invocación acotado por source_arn a esta HTTP API (D9, design.md).
resource "aws_lambda_permission" "api" {
  count = local.create_api_lambda ? 1 : 0

  statement_id  = "AllowExecutionFromHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api[0].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}
