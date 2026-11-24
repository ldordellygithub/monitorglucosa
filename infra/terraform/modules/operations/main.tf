# Observabilidad, alertas y control de coste (Requisitos 8.2, 8.3, 8.4, 8.5, NFR-3, NFR-5; D11, D14):
# - 3 grupos de logs de CloudWatch con retención de 30 días
# - Tema SNS monitorglucosa-alarms sin cifrado en reposo (D14) + suscripción por correo desde SSM
# - 4 alarmas CloudWatch (errores api, errores migrator, 5xx HTTP API y Aurora sin pausa 6 h)
# - Presupuesto mensual de US$20 sobre toda la cuenta con avisos real/previsto al 80 % y 100 %

data "aws_ssm_parameter" "owner_email" {
  name            = var.owner_email_parameter
  with_decryption = true
}

# ---------------------------------------------------------------------------
# Grupos de logs de CloudWatch con retención fija de 30 días (Requisito 8.5)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  # checkov:skip=CKV_AWS_158:Sin CMK KMS propia por coste (US$1/mes, NFR-3); logs JSON sin PII ni datos de salud cifrados por AWS.
  # checkov:skip=CKV_AWS_338:Requisito 8.5 fija exactamente 30 días de retención para los grupos de logs.
  name              = "/aws/lambda/${var.api_function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "migrator" {
  # checkov:skip=CKV_AWS_158:Sin CMK KMS propia por coste (US$1/mes, NFR-3); logs de migraciones sin PII cifrados por AWS.
  # checkov:skip=CKV_AWS_338:Requisito 8.5 fija exactamente 30 días de retención para los grupos de logs.
  name              = "/aws/lambda/${var.migrator_function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "apigateway" {
  # checkov:skip=CKV_AWS_158:Sin CMK KMS propia por coste (US$1/mes, NFR-3); logs de acceso sin IP ni cabeceras cifrados por AWS.
  # checkov:skip=CKV_AWS_338:Requisito 8.5 fija exactamente 30 días de retención para los grupos de logs.
  name              = "/aws/apigateway/${var.project}"
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------------------
# Tema SNS de alarmas sin cifrado en reposo (D14) y suscripción por correo
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alarms" {
  # checkov:skip=CKV_AWS_26:Decisión D14: CloudWatch Alarms no puede publicar en un tema cifrado con aws/sns; los mensajes solo contienen metadatos de alarma sin PII ni datos de salud y viajan por TLS.
  name = "${var.project}-alarms"
}

resource "aws_sns_topic_policy" "alarms" {
  arn = aws_sns_topic.alarms.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudWatchAlarmsPublish"
        Effect = "Allow"
        Principal = {
          Service = "cloudwatch.amazonaws.com"
        }
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.alarms.arn]
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:cloudwatch:${var.region}:${var.account_id}:alarm:${var.project}-*"
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "sns:*"
        Resource  = [aws_sns_topic.alarms.arn]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
    ]
  })
}

resource "aws_sns_topic_subscription" "owner_email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = data.aws_ssm_parameter.owner_email.value
}

# ---------------------------------------------------------------------------
# Las 4 alarmas de CloudWatch (Requisito 8.4, D14, NFR-3)
# ---------------------------------------------------------------------------

# 1/4: Errores de la Lambda api (Suma >= 1 en 5 min; sin datos = OK).
resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name          = "${var.project}-api-errors"
  alarm_description   = "La Lambda ${var.api_function_name} registró al menos 1 error en 5 minutos."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  dimensions = {
    FunctionName = var.api_function_name
  }
}

# 2/4: Errores de la Lambda migrator (Suma >= 1 en 5 min; sin datos = OK).
resource "aws_cloudwatch_metric_alarm" "migrator_errors" {
  alarm_name          = "${var.project}-migrator-errors"
  alarm_description   = "La Lambda ${var.migrator_function_name} registró al menos 1 error en 5 minutos."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  dimensions = {
    FunctionName = var.migrator_function_name
  }
}

# 3/4: Respuestas 5xx de HTTP API en etapa $default (Suma >= 1 en 5 min; sin datos = OK).
resource "aws_cloudwatch_metric_alarm" "apigateway_5xx" {
  alarm_name          = "${var.project}-apigateway-5xx"
  alarm_description   = "API Gateway HTTP API devolvió al menos una respuesta 5xx en 5 minutos."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  dimensions = {
    ApiId = var.http_api_id
    Stage = "$default"
  }
}

# 4/4: Aurora sin pausa (D14, NFR-3): ServerlessDatabaseCapacity mínimo > 0 durante 6 h.
resource "aws_cloudwatch_metric_alarm" "aurora_not_paused" {
  alarm_name          = "${var.project}-aurora-not-paused"
  alarm_description   = "Aurora Serverless v2 mantuvo capacidad > 0 ACU durante 6 horas seguidas (riesgo de coste D14)."
  namespace           = "AWS/RDS"
  metric_name         = "ServerlessDatabaseCapacity"
  statistic           = "Minimum"
  period              = 3600
  evaluation_periods  = 6
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  dimensions = {
    DBInstanceIdentifier = var.aurora_writer_instance_id
  }
}

# ---------------------------------------------------------------------------
# Presupuesto mensual de US$20 sobre toda la cuenta (Requisito 8.3, NFR-3)
# Avisos real > 80 % (US$16), previsto > 80 % (US$16), real > 100 % (US$20) y previsto > 100 % (US$20)
# ---------------------------------------------------------------------------

resource "aws_budgets_budget" "monthly_cost" {
  name         = "${var.project}-monthly-budget"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [data.aws_ssm_parameter.owner_email.value]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [data.aws_ssm_parameter.owner_email.value]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [data.aws_ssm_parameter.owner_email.value]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [data.aws_ssm_parameter.owner_email.value]
  }
}
