# Roles IAM de las Lambdas api y migrator con permissions boundary obligatorio,
# acceso acotado a CloudWatch Logs y rds-db:connect por usuario, y Deny de las
# 6 acciones EC2 de ENI al código de la función mediante lambda:SourceFunctionArn
# (Requisitos 5.3, 6.1, NFR-4; D4, ADR 0008).

locals {
  api_function_name      = "${var.project}-api"
  migrator_function_name = "${var.project}-migrator"

  region_condition = {
    StringEquals = {
      "aws:RequestedRegion" = var.region
    }
  }

  lambda_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaServiceAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.account_id
          }
        }
      }
    ]
  })

  # Excepción NFR-4 #2 (ADR 0008): las 6 acciones EC2 de ENI exigidas por Lambda en VPC.
  lambda_vpc_eni_actions = [
    "ec2:AssignPrivateIpAddresses",
    "ec2:CreateNetworkInterface",
    "ec2:DeleteNetworkInterface",
    "ec2:DescribeNetworkInterfaces",
    "ec2:DescribeSubnets",
    "ec2:UnassignPrivateIpAddresses",
  ]
}

# ---------------------------------------------------------------------------
# Rol IAM de la Lambda api (usuario de BD mg_api)
# ---------------------------------------------------------------------------

resource "aws_iam_role" "api" {
  name                 = local.api_function_name
  description          = "Rol de ejecución de la Lambda monitorglucosa-api acotado por workload-boundary (ADR 0008)."
  assume_role_policy   = local.lambda_assume_role_policy
  permissions_boundary = var.workload_boundary_arn
}

resource "aws_iam_role_policy" "api" {
  # checkov:skip=CKV_AWS_111:Excepción NFR-4 #2 (ADR 0008): AWS exige Resource="*" en las 6 acciones EC2 de ENI para Lambda en VPC; denegadas al código con lambda:SourceFunctionArn.
  # checkov:skip=CKV_AWS_356:Excepción NFR-4 #2 (ADR 0008): AWS no permite acotar por recurso las 6 acciones EC2 de ENI de Lambda.
  name = "${local.api_function_name}-inline"
  role = aws_iam_role.api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource  = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${local.api_function_name}:*"]
        Condition = local.region_condition
      },
      {
        Sid       = "AllowAuroraIamConnectApi"
        Effect    = "Allow"
        Action    = ["rds-db:connect"]
        Resource  = ["arn:aws:rds-db:${var.region}:${var.account_id}:dbuser:${var.aurora_cluster_resource_id}/mg_api"]
        Condition = local.region_condition
      },
      # Excepción NFR-4 #2 (ADR 0008): solo para el servicio de Lambda al gestionar ENIs.
      {
        Sid       = "AllowLambdaVpcNetworkInterfaces"
        Effect    = "Allow"
        Action    = local.lambda_vpc_eni_actions
        Resource  = "*"
        Condition = local.region_condition
      },
      {
        Sid      = "DenyVpcNetworkInterfacesToFunctionCode"
        Effect   = "Deny"
        Action   = local.lambda_vpc_eni_actions
        Resource = "*"
        Condition = {
          Null = {
            "lambda:SourceFunctionArn" = "false"
          }
        }
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Rol IAM de la Lambda migrator (usuario de BD mg_migrator)
# ---------------------------------------------------------------------------

resource "aws_iam_role" "migrator" {
  name                 = local.migrator_function_name
  description          = "Rol de ejecución de la Lambda monitorglucosa-migrator acotado por workload-boundary (ADR 0008)."
  assume_role_policy   = local.lambda_assume_role_policy
  permissions_boundary = var.workload_boundary_arn
}

resource "aws_iam_role_policy" "migrator" {
  # checkov:skip=CKV_AWS_111:Excepción NFR-4 #2 (ADR 0008): AWS exige Resource="*" en las 6 acciones EC2 de ENI para Lambda en VPC; denegadas al código con lambda:SourceFunctionArn.
  # checkov:skip=CKV_AWS_356:Excepción NFR-4 #2 (ADR 0008): AWS no permite acotar por recurso las 6 acciones EC2 de ENI de Lambda.
  name = "${local.migrator_function_name}-inline"
  role = aws_iam_role.migrator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource  = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${local.migrator_function_name}:*"]
        Condition = local.region_condition
      },
      {
        Sid       = "AllowAuroraIamConnectMigrator"
        Effect    = "Allow"
        Action    = ["rds-db:connect"]
        Resource  = ["arn:aws:rds-db:${var.region}:${var.account_id}:dbuser:${var.aurora_cluster_resource_id}/mg_migrator"]
        Condition = local.region_condition
      },
      # Excepción NFR-4 #2 (ADR 0008): solo para el servicio de Lambda al gestionar ENIs.
      {
        Sid       = "AllowLambdaVpcNetworkInterfaces"
        Effect    = "Allow"
        Action    = local.lambda_vpc_eni_actions
        Resource  = "*"
        Condition = local.region_condition
      },
      {
        Sid      = "DenyVpcNetworkInterfacesToFunctionCode"
        Effect   = "Deny"
        Action   = local.lambda_vpc_eni_actions
        Resource = "*"
        Condition = {
          Null = {
            "lambda:SourceFunctionArn" = "false"
          }
        }
      },
    ]
  })
}
