# Pruebas de plan con proveedores simulados para el módulo `operations`
# (Requisitos 8.2, 8.3, 8.4, 8.5, NFR-3, NFR-5; D11, D14).

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
      arn        = "arn:aws:sts::123456789012:assumed-role/monitorglucosa-deploy/test"
      user_id    = "AROAEXAMPLE:test"
    }
  }

  mock_data "aws_ssm_parameter" {
    defaults = {
      name  = "/monitorglucosa/prod/owner-email"
      type  = "SecureString"
      value = "owner@example.invalid"
    }
  }
}

run "raiz_conecta_operations_sin_ciclos_ni_errores" {
  command = plan

  override_resource {
    target          = module.api.aws_apigatewayv2_api.main
    override_during = plan
    values = {
      id            = "abc123def4"
      api_endpoint  = "https://abc123def4.execute-api.us-east-1.amazonaws.com"
      execution_arn = "arn:aws:execute-api:us-east-1:123456789012:abc123def4"
    }
  }

  override_resource {
    target          = module.operations.aws_cloudwatch_log_group.apigateway
    override_during = plan
    values = {
      arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/apigateway/monitorglucosa"
    }
  }

  assert {
    condition     = module.operations.budget_name == "monitorglucosa-monthly-budget"
    error_message = "La raíz debe conectar module.operations con module.api y module.database sin ciclos."
  }
}

run "modulo_operations_cumple_sns_alarmas_presupuesto_y_retencion" {
  command = plan

  module {
    source = "./modules/operations"
  }

  variables {
    account_id                = "123456789012"
    region                    = "us-east-1"
    project                   = "monitorglucosa"
    owner_email_parameter     = "/monitorglucosa/prod/owner-email"
    api_function_name         = "monitorglucosa-api"
    migrator_function_name    = "monitorglucosa-migrator"
    http_api_id               = "abc123def4"
    aurora_writer_instance_id = "monitorglucosa-aurora-writer"
  }

  override_resource {
    target          = aws_sns_topic.alarms
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-1:123456789012:monitorglucosa-alarms"
    }
  }

  # --- Requisito 8.5: retención de 30 días en los 3 grupos de logs ---
  assert {
    condition = (
      aws_cloudwatch_log_group.api.name == "/aws/lambda/monitorglucosa-api" &&
      aws_cloudwatch_log_group.api.retention_in_days == 30 &&
      aws_cloudwatch_log_group.migrator.name == "/aws/lambda/monitorglucosa-migrator" &&
      aws_cloudwatch_log_group.migrator.retention_in_days == 30 &&
      aws_cloudwatch_log_group.apigateway.name == "/aws/apigateway/monitorglucosa" &&
      aws_cloudwatch_log_group.apigateway.retention_in_days == 30
    )
    error_message = "Los tres grupos de logs de CloudWatch deben tener nombres exactos y retención de 30 días (8.5)."
  }

  # --- Requisito 8.4, D11 y D14: SNS sin KMS, política acotada a CloudWatch + TLS, correo desde SSM ---
  assert {
    condition = (
      aws_sns_topic.alarms.name == "monitorglucosa-alarms" &&
      aws_sns_topic.alarms.kms_master_key_id == null &&
      aws_sns_topic_subscription.owner_email.protocol == "email" &&
      aws_sns_topic_subscription.owner_email.endpoint == "owner@example.invalid" &&
      length(jsondecode(aws_sns_topic_policy.alarms.policy).Statement) == 2 &&
      length([
        for s in jsondecode(aws_sns_topic_policy.alarms.policy).Statement : s
        if s.Effect == "Allow" &&
        s.Principal.Service == "cloudwatch.amazonaws.com" &&
        toset(s.Action) == toset(["sns:Publish"]) &&
        s.Condition.StringEquals["aws:SourceAccount"] == "123456789012" &&
        s.Condition.ArnLike["aws:SourceArn"] == "arn:aws:cloudwatch:us-east-1:123456789012:alarm:monitorglucosa-*"
      ]) == 1 &&
      length([
        for s in jsondecode(aws_sns_topic_policy.alarms.policy).Statement : s
        if s.Effect == "Deny" &&
        s.Action == "sns:*" &&
        s.Condition.Bool["aws:SecureTransport"] == "false"
      ]) == 1
    )
    error_message = "El tema SNS debe llamarse monitorglucosa-alarms sin KMS (D14), con política restringida a CloudWatch + TLS y suscripción desde SSM."
  }

  # --- Requisito 8.4 y D14: las 4 alarmas de CloudWatch apuntando al tema SNS (sin monitores sintéticos) ---
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.api_errors.alarm_name == "monitorglucosa-api-errors" &&
      aws_cloudwatch_metric_alarm.api_errors.namespace == "AWS/Lambda" &&
      aws_cloudwatch_metric_alarm.api_errors.metric_name == "Errors" &&
      aws_cloudwatch_metric_alarm.api_errors.statistic == "Sum" &&
      aws_cloudwatch_metric_alarm.api_errors.period == 300 &&
      aws_cloudwatch_metric_alarm.api_errors.evaluation_periods == 1 &&
      aws_cloudwatch_metric_alarm.api_errors.comparison_operator == "GreaterThanOrEqualToThreshold" &&
      aws_cloudwatch_metric_alarm.api_errors.threshold == 1 &&
      aws_cloudwatch_metric_alarm.api_errors.treat_missing_data == "notBreaching" &&
      aws_cloudwatch_metric_alarm.api_errors.dimensions["FunctionName"] == "monitorglucosa-api" &&
      toset(aws_cloudwatch_metric_alarm.api_errors.alarm_actions) == toset(["arn:aws:sns:us-east-1:123456789012:monitorglucosa-alarms"]) &&
      aws_cloudwatch_metric_alarm.migrator_errors.alarm_name == "monitorglucosa-migrator-errors" &&
      aws_cloudwatch_metric_alarm.migrator_errors.namespace == "AWS/Lambda" &&
      aws_cloudwatch_metric_alarm.migrator_errors.metric_name == "Errors" &&
      aws_cloudwatch_metric_alarm.migrator_errors.statistic == "Sum" &&
      aws_cloudwatch_metric_alarm.migrator_errors.period == 300 &&
      aws_cloudwatch_metric_alarm.migrator_errors.evaluation_periods == 1 &&
      aws_cloudwatch_metric_alarm.migrator_errors.comparison_operator == "GreaterThanOrEqualToThreshold" &&
      aws_cloudwatch_metric_alarm.migrator_errors.threshold == 1 &&
      aws_cloudwatch_metric_alarm.migrator_errors.treat_missing_data == "notBreaching" &&
      aws_cloudwatch_metric_alarm.migrator_errors.dimensions["FunctionName"] == "monitorglucosa-migrator" &&
      toset(aws_cloudwatch_metric_alarm.migrator_errors.alarm_actions) == toset(["arn:aws:sns:us-east-1:123456789012:monitorglucosa-alarms"])
    )
    error_message = "Las alarmas de Lambda api y migrator deben vigilar Errors (Sum >= 1 en 5 min, notBreaching) y publicar en el tema SNS."
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.apigateway_5xx.alarm_name == "monitorglucosa-apigateway-5xx" &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.namespace == "AWS/ApiGateway" &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.metric_name == "5xx" &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.statistic == "Sum" &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.period == 300 &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.evaluation_periods == 1 &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.comparison_operator == "GreaterThanOrEqualToThreshold" &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.threshold == 1 &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.treat_missing_data == "notBreaching" &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.dimensions["ApiId"] == "abc123def4" &&
      aws_cloudwatch_metric_alarm.apigateway_5xx.dimensions["Stage"] == "$default" &&
      toset(aws_cloudwatch_metric_alarm.apigateway_5xx.alarm_actions) == toset(["arn:aws:sns:us-east-1:123456789012:monitorglucosa-alarms"])
    )
    error_message = "La alarma de API Gateway debe vigilar AWS/ApiGateway 5xx en la etapa $default (Sum >= 1 en 5 min, notBreaching) y publicar en el tema SNS."
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.aurora_not_paused.alarm_name == "monitorglucosa-aurora-not-paused" &&
      aws_cloudwatch_metric_alarm.aurora_not_paused.namespace == "AWS/RDS" &&
      aws_cloudwatch_metric_alarm.aurora_not_paused.metric_name == "ServerlessDatabaseCapacity" &&
      aws_cloudwatch_metric_alarm.aurora_not_paused.statistic == "Minimum" &&
      aws_cloudwatch_metric_alarm.aurora_not_paused.period == 3600 &&
      aws_cloudwatch_metric_alarm.aurora_not_paused.evaluation_periods == 6 &&
      aws_cloudwatch_metric_alarm.aurora_not_paused.comparison_operator == "GreaterThanThreshold" &&
      aws_cloudwatch_metric_alarm.aurora_not_paused.threshold == 0 &&
      aws_cloudwatch_metric_alarm.aurora_not_paused.treat_missing_data == "notBreaching" &&
      aws_cloudwatch_metric_alarm.aurora_not_paused.dimensions["DBInstanceIdentifier"] == "monitorglucosa-aurora-writer" &&
      toset(aws_cloudwatch_metric_alarm.aurora_not_paused.alarm_actions) == toset(["arn:aws:sns:us-east-1:123456789012:monitorglucosa-alarms"]) &&
      !can(regex("aws_synthetics_canary|aws_route53_health_check|aws_cloudwatch_event_rule|aws_scheduler_schedule", file("${path.module}/main.tf")))
    )
    error_message = "La alarma Aurora sin pausa (D14) debe vigilar ServerlessDatabaseCapacity Minimum > 0 durante 6×1 h, publicar en SNS y no crear monitores sintéticos."
  }

  # --- Requisito 8.3 y NFR-3: presupuesto mensual US$20 sobre toda la cuenta, 4 avisos (80%/100% actual+forecasted) ---
  assert {
    condition = (
      aws_budgets_budget.monthly_cost.name == "monitorglucosa-monthly-budget" &&
      aws_budgets_budget.monthly_cost.budget_type == "COST" &&
      aws_budgets_budget.monthly_cost.limit_amount == "20" &&
      aws_budgets_budget.monthly_cost.limit_unit == "USD" &&
      aws_budgets_budget.monthly_cost.time_unit == "MONTHLY" &&
      length(aws_budgets_budget.monthly_cost.cost_filter) == 0 &&
      length(aws_budgets_budget.monthly_cost.notification) == 4 &&
      toset([
        for n in aws_budgets_budget.monthly_cost.notification :
        "${n.notification_type}:${n.threshold}:${n.threshold_type}:${n.comparison_operator}"
        ]) == toset([
        "ACTUAL:80:PERCENTAGE:GREATER_THAN",
        "FORECASTED:80:PERCENTAGE:GREATER_THAN",
        "ACTUAL:100:PERCENTAGE:GREATER_THAN",
        "FORECASTED:100:PERCENTAGE:GREATER_THAN",
      ]) &&
      alltrue([
        for n in aws_budgets_budget.monthly_cost.notification :
        toset(n.subscriber_email_addresses) == toset(["owner@example.invalid"])
      ])
    )
    error_message = "El presupuesto debe ser de 20 USD/mes sobre toda la cuenta con 4 notificaciones (ACTUAL/FORECASTED al 80% y 100%) al correo de SSM."
  }

  # --- Requisito 8.2: no sobreescribe default_tags ---
  assert {
    condition = alltrue([
      for res_tags in [
        aws_cloudwatch_log_group.api.tags,
        aws_cloudwatch_log_group.migrator.tags,
        aws_cloudwatch_log_group.apigateway.tags,
        aws_sns_topic.alarms.tags,
        aws_cloudwatch_metric_alarm.api_errors.tags,
        aws_cloudwatch_metric_alarm.migrator_errors.tags,
        aws_cloudwatch_metric_alarm.apigateway_5xx.tags,
        aws_cloudwatch_metric_alarm.aurora_not_paused.tags,
        aws_budgets_budget.monthly_cost.tags,
        ] : (
        try(res_tags["Environment"], "prod") == "prod" &&
        try(res_tags["Project"], "monitorglucosa") == "monitorglucosa" &&
        try(res_tags["Owner"], "ldordellygithub") == "ldordellygithub"
      )
    ])
    error_message = "Ningún recurso etiquetable de operations puede sobrescribir default_tags."
  }
}

run "rechaza_retencion_de_logs_distinta_de_30_dias" {
  command = plan

  module {
    source = "./modules/operations"
  }

  variables {
    account_id                = "123456789012"
    region                    = "us-east-1"
    project                   = "monitorglucosa"
    owner_email_parameter     = "/monitorglucosa/prod/owner-email"
    api_function_name         = "monitorglucosa-api"
    migrator_function_name    = "monitorglucosa-migrator"
    http_api_id               = "abc123def4"
    aurora_writer_instance_id = "monitorglucosa-aurora-writer"
    log_retention_days        = 7
  }

  expect_failures = [
    var.log_retention_days,
  ]
}
