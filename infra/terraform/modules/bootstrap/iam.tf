# Identidad OIDC de GitHub, permissions boundary de cargas de trabajo y rol
# monitorglucosa-deploy acotado por región us-east-1 y prefijo monitorglucosa-*
# (Requisitos 7.2, NFR-4, NFR-5; D4, ADR 0007, ADR 0008, ADR 0011).

locals {
  deploy_role_name               = "${var.project}-deploy"
  workload_boundary_name         = "${var.project}-workload-boundary"
  deploy_core_policy_name        = "${var.project}-deploy-core"
  deploy_infra_core_policy_name  = "${var.project}-deploy-infra-core"
  deploy_infra_edge_policy_name  = "${var.project}-deploy-infra-edge"
  deploy_read_policy_name        = "${var.project}-deploy-read"
  expected_oidc_sub              = "repo:${var.github_repository}:environment:${var.github_environment}"
  oidc_provider_arn              = "arn:aws:iam::${var.account_id}:oidc-provider/token.actions.githubusercontent.com"
  deploy_role_arn                = "arn:aws:iam::${var.account_id}:role/${local.deploy_role_name}"
  deploy_policy_arn_pattern      = "arn:aws:iam::${var.account_id}:policy/${var.project}-deploy-*"
  boundary_arn                   = "arn:aws:iam::${var.account_id}:policy/${local.workload_boundary_name}"
  ecr_repository_arn             = "arn:aws:ecr:${var.region}:${var.account_id}:repository/${var.project}-api"
  aurora_cluster_arn_effective   = coalesce(var.aurora_cluster_arn, "arn:aws:rds:${var.region}:${var.account_id}:cluster:${var.project}-aurora")
  master_secret_arn_effective    = coalesce(var.master_secret_arn, "arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:rds!cluster-*")
  workload_role_arn_deny_pattern = "arn:aws:iam::${var.account_id}:role/${var.project}-*"

  # Lista exacta de los dos roles de carga de trabajo que Terraform puede gestionar
  # (evita crear roles auxiliares con comodín monitorglucosa-* fuera de Lambda).
  workload_role_arns = [
    "arn:aws:iam::${var.account_id}:role/${var.project}-api",
    "arn:aws:iam::${var.account_id}:role/${var.project}-migrator",
  ]

  region_condition = {
    StringEquals = {
      "aws:RequestedRegion" = var.region
    }
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# Rol vinculado al servicio RDS creado durante el bootstrap local con credenciales de
# administrador (evita conceder iam:CreateServiceLinkedRole a monitorglucosa-deploy).
resource "aws_iam_service_linked_role" "rds" {
  aws_service_name = "rds.amazonaws.com"
  description      = "Service-linked role requerido por Aurora PostgreSQL Serverless v2."
}

# ---------------------------------------------------------------------------
# Permissions boundary obligatorio para roles creados por Terraform (ADR 0008)
# ---------------------------------------------------------------------------

resource "aws_iam_policy" "workload_boundary" {
  # checkov:skip=CKV_AWS_111:Excepción NFR-4 #2 (ADR 0008): AWS exige Resource="*" en las 6 acciones EC2 de ENI para Lambda en VPC; denegadas al código con lambda:SourceFunctionArn.
  # checkov:skip=CKV_AWS_356:Excepción NFR-4 #2 (ADR 0008): AWS no permite acotar por recurso las 6 acciones EC2 de ENI de Lambda.
  name        = local.workload_boundary_name
  description = "Permissions boundary obligatorio para roles de carga de trabajo de monitorglucosa (ADR 0008)."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaCloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource  = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${var.project}-*:*"]
        Condition = local.region_condition
      },
      {
        Sid    = "AllowAuroraIamConnectForAppRoles"
        Effect = "Allow"
        Action = ["rds-db:connect"]
        Resource = [
          "arn:aws:rds-db:${var.region}:${var.account_id}:dbuser:*/mg_api",
          "arn:aws:rds-db:${var.region}:${var.account_id}:dbuser:*/mg_migrator",
        ]
        Condition = local.region_condition
      },
      # Excepción NFR-4 #2 (ADR 0008): las 6 acciones EC2 de ENI exigidas por Lambda en VPC.
      {
        Sid    = "AllowLambdaVpcNetworkInterfaces"
        Effect = "Allow"
        Action = [
          "ec2:AssignPrivateIpAddresses",
          "ec2:CreateNetworkInterface",
          "ec2:DeleteNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeSubnets",
          "ec2:UnassignPrivateIpAddresses",
        ]
        Resource  = "*"
        Condition = local.region_condition
      },
      {
        Sid    = "DenyVpcNetworkInterfacesToFunctionCode"
        Effect = "Deny"
        Action = [
          "ec2:AssignPrivateIpAddresses",
          "ec2:CreateNetworkInterface",
          "ec2:DeleteNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeSubnets",
          "ec2:UnassignPrivateIpAddresses",
        ]
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
# Rol de despliegue asumido por GitHub Actions vía OIDC (Requisito 7.2, D4)
# ---------------------------------------------------------------------------

resource "aws_iam_role" "deploy" {
  name                 = local.deploy_role_name
  description          = "Rol de despliegue acotado para GitHub Actions (entorno prod, us-east-1; ADR 0008)."
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowGitHubActionsProdEnvironmentOnly"
        Effect = "Allow"
        Principal = {
          Federated = local.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = local.expected_oidc_sub
          }
        }
      }
    ]
  })

  depends_on = [aws_iam_openid_connect_provider.github]
}

# ---------------------------------------------------------------------------
# Política 1/4: núcleo de despliegue (estado S3, ECR, IAM con boundary, runtime)
# ---------------------------------------------------------------------------

resource "aws_iam_policy" "deploy_core" {
  name        = local.deploy_core_policy_name
  description = "Permisos de núcleo y salvaguardas anti-escalada del rol monitorglucosa-deploy (ADR 0008)."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "TerraformStateBucketList"
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = [local.tfstate_bucket_arn]
        Condition = local.region_condition
      },
      {
        Sid    = "TerraformStateObjectsAndLockfile"
        Effect = "Allow"
        Action = [
          "s3:DeleteObject",
          "s3:GetObject",
          "s3:PutObject",
        ]
        Resource  = ["${local.tfstate_bucket_arn}/prod/*"]
        Condition = local.region_condition
      },
      {
        Sid    = "TerraformStateBucketMetadataRead"
        Effect = "Allow"
        Action = [
          "s3:GetAccelerateConfiguration",
          "s3:GetBucketAcl",
          "s3:GetBucketCORS",
          "s3:GetBucketLocation",
          "s3:GetBucketLogging",
          "s3:GetBucketObjectLockConfiguration",
          "s3:GetBucketOwnershipControls",
          "s3:GetBucketPolicy",
          "s3:GetBucketPublicAccessBlock",
          "s3:GetBucketRequestPayment",
          "s3:GetBucketTagging",
          "s3:GetBucketVersioning",
          "s3:GetBucketWebsite",
          "s3:GetEncryptionConfiguration",
          "s3:GetLifecycleConfiguration",
          "s3:GetReplicationConfiguration",
        ]
        Resource  = [local.tfstate_bucket_arn]
        Condition = local.region_condition
      },
      {
        Sid    = "EcrRepositoryPushAndDescribe"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeImages",
          "ecr:DescribeRepositories",
          "ecr:GetDownloadUrlForLayer",
          "ecr:GetLifecyclePolicy",
          "ecr:GetRepositoryPolicy",
          "ecr:InitiateLayerUpload",
          "ecr:ListTagsForResource",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
        ]
        Resource  = [local.ecr_repository_arn]
        Condition = local.region_condition
      },
      # Solo acciones IAM que soportan la clave de condición iam:PermissionsBoundary.
      {
        Sid    = "IamManageWorkloadRolesWithMandatoryBoundary"
        Effect = "Allow"
        Action = [
          "iam:AttachRolePolicy",
          "iam:CreateRole",
          "iam:DeleteRolePolicy",
          "iam:DetachRolePolicy",
          "iam:PutRolePermissionsBoundary",
          "iam:PutRolePolicy",
        ]
        Resource = local.workload_role_arns
        Condition = {
          StringEquals = {
            "iam:PermissionsBoundary" = local.boundary_arn
            "aws:RequestedRegion"     = var.region
          }
        }
      },
      # Acciones de metadatos de rol (no soportan iam:PermissionsBoundary en AWS),
      # acotadas exclusivamente a los 2 ARNs exactos de api y migrator.
      {
        Sid    = "IamUpdateWorkloadRoleMetadata"
        Effect = "Allow"
        Action = [
          "iam:TagRole",
          "iam:UntagRole",
          "iam:UpdateAssumeRolePolicy",
          "iam:UpdateRole",
          "iam:UpdateRoleDescription",
        ]
        Resource  = local.workload_role_arns
        Condition = local.region_condition
      },
      {
        Sid    = "IamReadAndDeleteWorkloadRoles"
        Effect = "Allow"
        Action = [
          "iam:DeleteRole",
          "iam:GetRole",
          "iam:GetRolePolicy",
          "iam:ListAttachedRolePolicies",
          "iam:ListInstanceProfilesForRole",
          "iam:ListRolePolicies",
        ]
        Resource  = local.workload_role_arns
        Condition = local.region_condition
      },
      {
        Sid      = "IamPassWorkloadRoleToLambdaOnly"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = local.workload_role_arns
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "lambda.amazonaws.com"
            "aws:RequestedRegion" = var.region
          }
        }
      },
      {
        Sid    = "IamReadBootstrapMetadata"
        Effect = "Allow"
        Action = [
          "iam:GetOpenIDConnectProvider",
          "iam:GetPolicy",
          "iam:GetPolicyVersion",
          "iam:GetRole",
          "iam:ListAttachedRolePolicies",
          "iam:ListInstanceProfilesForRole",
          "iam:ListPolicyVersions",
          "iam:ListRolePolicies",
        ]
        Resource = [
          local.oidc_provider_arn,
          local.boundary_arn,
          local.deploy_policy_arn_pattern,
          local.deploy_role_arn,
          "arn:aws:iam::${var.account_id}:role/aws-service-role/rds.amazonaws.com/AWSServiceRoleForRDS",
        ]
        Condition = local.region_condition
      },
      # Operaciones de despliegue: migrator (ADR 0006), humo SigV4 (7.5) y Data API (ADR 0007).
      {
        Sid       = "InvokeMigratorLambda"
        Effect    = "Allow"
        Action    = ["lambda:InvokeFunction"]
        Resource  = ["arn:aws:lambda:${var.region}:${var.account_id}:function:${var.project}-migrator"]
        Condition = local.region_condition
      },
      {
        Sid       = "InvokeHealthReadySmokeTest"
        Effect    = "Allow"
        Action    = ["execute-api:Invoke"]
        Resource  = ["arn:aws:execute-api:${var.region}:${var.account_id}:*/*/GET/health/ready"]
        Condition = local.region_condition
      },
      {
        Sid       = "ExecuteBootstrapSqlViaDataApi"
        Effect    = "Allow"
        Action    = ["rds-data:ExecuteStatement"]
        Resource  = [local.aurora_cluster_arn_effective]
        Condition = local.region_condition
      },
      {
        Sid       = "ReadAuroraMasterSecretForBootstrap"
        Effect    = "Allow"
        Action    = ["secretsmanager:GetSecretValue"]
        Resource  = [local.master_secret_arn_effective]
        Condition = local.region_condition
      },
      # Deny explícitos incondicionales anti-escalada de privilegios (ADR 0008).
      {
        Sid    = "DenyModifyOrDeleteWorkloadBoundary"
        Effect = "Deny"
        Action = [
          "iam:CreatePolicyVersion",
          "iam:DeletePolicy",
          "iam:DeletePolicyVersion",
          "iam:SetDefaultPolicyVersion",
          "iam:TagPolicy",
          "iam:UntagPolicy",
        ]
        Resource = [
          local.boundary_arn,
          local.deploy_policy_arn_pattern,
        ]
      },
      {
        Sid      = "DenyRemovePermissionsBoundary"
        Effect   = "Deny"
        Action   = ["iam:DeleteRolePermissionsBoundary"]
        Resource = [local.workload_role_arn_deny_pattern]
      },
      {
        Sid    = "DenySelfModifyDeployRole"
        Effect = "Deny"
        Action = [
          "iam:AttachRolePolicy",
          "iam:DeleteRole",
          "iam:DeleteRolePolicy",
          "iam:DeleteRolePermissionsBoundary",
          "iam:DetachRolePolicy",
          "iam:PutRolePermissionsBoundary",
          "iam:PutRolePolicy",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:UpdateAssumeRolePolicy",
          "iam:UpdateRole",
          "iam:UpdateRoleDescription",
        ]
        Resource = [local.deploy_role_arn]
      },
    ]
  })

  depends_on = [
    aws_s3_bucket.tfstate,
    aws_ecr_repository.api,
    aws_iam_policy.workload_boundary,
    aws_iam_openid_connect_provider.github,
  ]
}

resource "aws_iam_role_policy_attachment" "deploy_core" {
  role       = aws_iam_role.deploy.name
  policy_arn = aws_iam_policy.deploy_core.arn
}

# ---------------------------------------------------------------------------
# Política 2/4: infraestructura núcleo (network, database y api en us-east-1)
# ---------------------------------------------------------------------------

resource "aws_iam_policy" "deploy_infra_core" {
  name        = local.deploy_infra_core_policy_name
  description = "Permisos acotados de monitorglucosa-deploy para red VPC, Aurora, Lambda y HTTP API (ADR 0008)."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ManageProjectNetworkVpc"
        Effect = "Allow"
        Action = [
          "ec2:AssociateRouteTable",
          "ec2:AuthorizeSecurityGroupEgress",
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:CreateRouteTable",
          "ec2:CreateSecurityGroup",
          "ec2:CreateSubnet",
          "ec2:CreateTags",
          "ec2:CreateVpc",
          "ec2:CreateVpcEndpoint",
          "ec2:DeleteRouteTable",
          "ec2:DeleteSecurityGroup",
          "ec2:DeleteSubnet",
          "ec2:DeleteTags",
          "ec2:DeleteVpc",
          "ec2:DeleteVpcEndpoints",
          "ec2:DisassociateRouteTable",
          "ec2:ModifySecurityGroupRules",
          "ec2:ModifyVpcAttribute",
          "ec2:ModifyVpcEndpoint",
          "ec2:RevokeSecurityGroupEgress",
          "ec2:RevokeSecurityGroupIngress",
        ]
        Resource = [
          "arn:aws:ec2:${var.region}:${var.account_id}:route-table/*",
          "arn:aws:ec2:${var.region}:${var.account_id}:security-group-rule/*",
          "arn:aws:ec2:${var.region}:${var.account_id}:security-group/*",
          "arn:aws:ec2:${var.region}:${var.account_id}:subnet/*",
          "arn:aws:ec2:${var.region}:${var.account_id}:vpc-endpoint/*",
          "arn:aws:ec2:${var.region}:${var.account_id}:vpc/*",
        ]
        Condition = local.region_condition
      },
      {
        Sid    = "ManageProjectAuroraDatabase"
        Effect = "Allow"
        Action = [
          "rds:AddTagsToResource",
          "rds:CreateDBCluster",
          "rds:CreateDBClusterParameterGroup",
          "rds:CreateDBInstance",
          "rds:CreateDBSubnetGroup",
          "rds:DeleteDBCluster",
          "rds:DeleteDBClusterParameterGroup",
          "rds:DeleteDBInstance",
          "rds:DeleteDBSubnetGroup",
          "rds:ListTagsForResource",
          "rds:ModifyDBCluster",
          "rds:ModifyDBClusterParameterGroup",
          "rds:ModifyDBInstance",
          "rds:ModifyDBSubnetGroup",
          "rds:RemoveTagsFromResource",
        ]
        Resource = [
          "arn:aws:rds:${var.region}:${var.account_id}:cluster:${var.project}-*",
          "arn:aws:rds:${var.region}:${var.account_id}:cluster-pg:${var.project}-*",
          "arn:aws:rds:${var.region}:${var.account_id}:db:${var.project}-*",
          "arn:aws:rds:${var.region}:${var.account_id}:og:default:aurora-postgresql-16",
          "arn:aws:rds:${var.region}:${var.account_id}:pg:default.aurora-postgresql16",
          "arn:aws:rds:${var.region}:${var.account_id}:subgrp:${var.project}-*",
        ]
        Condition = local.region_condition
      },
      {
        Sid    = "ManageAuroraManagedMasterSecret"
        Effect = "Allow"
        Action = [
          "secretsmanager:CreateSecret",
          "secretsmanager:TagResource",
        ]
        Resource  = ["arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:rds!cluster-*"]
        Condition = local.region_condition
      },
      {
        Sid      = "DescribeKmsKeyForRdsManagedSecret"
        Effect   = "Allow"
        Action   = ["kms:DescribeKey"]
        Resource = ["arn:aws:kms:${var.region}:${var.account_id}:key/*"]
        Condition = {
          StringEquals = {
            "kms:ViaService" = [
              "secretsmanager.${var.region}.amazonaws.com",
              "rds.${var.region}.amazonaws.com",
            ]
            "aws:RequestedRegion" = var.region
          }
        }
      },
      {
        Sid    = "ManageProjectLambdas"
        Effect = "Allow"
        Action = [
          "lambda:AddPermission",
          "lambda:CreateFunction",
          "lambda:DeleteFunction",
          "lambda:GetFunction",
          "lambda:GetFunctionCodeSigningConfig",
          "lambda:GetFunctionConfiguration",
          "lambda:GetPolicy",
          "lambda:ListTags",
          "lambda:ListVersionsByFunction",
          "lambda:RemovePermission",
          "lambda:TagResource",
          "lambda:UntagResource",
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
        ]
        Resource  = ["arn:aws:lambda:${var.region}:${var.account_id}:function:${var.project}-*"]
        Condition = local.region_condition
      },
      {
        Sid    = "ManageProjectHttpApi"
        Effect = "Allow"
        Action = [
          "apigateway:DELETE",
          "apigateway:GET",
          "apigateway:PATCH",
          "apigateway:POST",
          "apigateway:PUT",
        ]
        Resource = [
          "arn:aws:apigateway:${var.region}::/apis",
          "arn:aws:apigateway:${var.region}::/apis/*",
          "arn:aws:apigateway:${var.region}::/tags/*",
        ]
        Condition = local.region_condition
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "deploy_infra_core" {
  role       = aws_iam_role.deploy.name
  policy_arn = aws_iam_policy.deploy_infra_core.arn
}

# ---------------------------------------------------------------------------
# Política 3/4: borde y operación (identity, site y operations en us-east-1)
# ---------------------------------------------------------------------------

resource "aws_iam_policy" "deploy_infra_edge" {
  name        = local.deploy_infra_edge_policy_name
  description = "Permisos acotados de monitorglucosa-deploy para Cognito, S3 sitio, CloudFront, Logs, SNS y Budgets (ADR 0008)."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ManageProjectCognitoIdentity"
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminDeleteUser",
          "cognito-idp:AdminGetUser",
          "cognito-idp:CreateUserPool",
          "cognito-idp:CreateUserPoolClient",
          "cognito-idp:CreateUserPoolDomain",
          "cognito-idp:DeleteUserPool",
          "cognito-idp:DeleteUserPoolClient",
          "cognito-idp:DeleteUserPoolDomain",
          "cognito-idp:DescribeUserPool",
          "cognito-idp:DescribeUserPoolClient",
          "cognito-idp:GetUserPoolMfaConfig",
          "cognito-idp:ListTagsForResource",
          "cognito-idp:SetUserPoolMfaConfig",
          "cognito-idp:TagResource",
          "cognito-idp:UntagResource",
          "cognito-idp:UpdateUserPool",
          "cognito-idp:UpdateUserPoolClient",
        ]
        Resource  = ["arn:aws:cognito-idp:${var.region}:${var.account_id}:userpool/*"]
        Condition = local.region_condition
      },
      # Lectura y descifrado del correo propietario en Parameter Store (D11) para Cognito y SNS.
      {
        Sid       = "ReadOwnerEmailParameter"
        Effect    = "Allow"
        Action    = ["ssm:GetParameter"]
        Resource  = ["arn:aws:ssm:${var.region}:${var.account_id}:parameter${var.owner_email_parameter}"]
        Condition = local.region_condition
      },
      {
        Sid      = "DecryptOwnerEmailParameterViaSsm"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = ["arn:aws:kms:${var.region}:${var.account_id}:key/*"]
        Condition = {
          StringEquals = {
            "kms:ViaService"                      = "ssm.${var.region}.amazonaws.com"
            "kms:EncryptionContext:PARAMETER_ARN" = "arn:aws:ssm:${var.region}:${var.account_id}:parameter${var.owner_email_parameter}"
            "aws:RequestedRegion"                 = var.region
          }
        }
      },
      {
        Sid    = "ManageProjectSiteBucket"
        Effect = "Allow"
        Action = [
          "s3:CreateBucket",
          "s3:DeleteBucket",
          "s3:DeleteBucketPolicy",
          "s3:DeleteObject",
          "s3:GetAccelerateConfiguration",
          "s3:GetBucketAcl",
          "s3:GetBucketCORS",
          "s3:GetBucketLocation",
          "s3:GetBucketLogging",
          "s3:GetBucketObjectLockConfiguration",
          "s3:GetBucketOwnershipControls",
          "s3:GetBucketPolicy",
          "s3:GetBucketPublicAccessBlock",
          "s3:GetBucketRequestPayment",
          "s3:GetBucketTagging",
          "s3:GetBucketVersioning",
          "s3:GetBucketWebsite",
          "s3:GetEncryptionConfiguration",
          "s3:GetLifecycleConfiguration",
          "s3:GetObject",
          "s3:GetReplicationConfiguration",
          "s3:ListBucket",
          "s3:PutBucketOwnershipControls",
          "s3:PutBucketPolicy",
          "s3:PutBucketPublicAccessBlock",
          "s3:PutBucketTagging",
          "s3:PutBucketVersioning",
          "s3:PutEncryptionConfiguration",
          "s3:PutLifecycleConfiguration",
          "s3:PutObject",
        ]
        Resource = [
          "arn:aws:s3:::${var.project}-site-${var.account_id}",
          "arn:aws:s3:::${var.project}-site-${var.account_id}/*",
        ]
        Condition = local.region_condition
      },
      {
        Sid    = "ManageProjectCloudFrontSite"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateDistribution",
          "cloudfront:CreateOriginAccessControl",
          "cloudfront:CreateResponseHeadersPolicy",
          "cloudfront:DeleteDistribution",
          "cloudfront:DeleteOriginAccessControl",
          "cloudfront:DeleteResponseHeadersPolicy",
          "cloudfront:GetDistribution",
          "cloudfront:GetDistributionConfig",
          "cloudfront:GetOriginAccessControl",
          "cloudfront:GetOriginAccessControlConfig",
          "cloudfront:GetResponseHeadersPolicy",
          "cloudfront:GetResponseHeadersPolicyConfig",
          "cloudfront:ListTagsForResource",
          "cloudfront:TagResource",
          "cloudfront:UntagResource",
          "cloudfront:UpdateDistribution",
          "cloudfront:UpdateOriginAccessControl",
          "cloudfront:UpdateResponseHeadersPolicy",
        ]
        Resource = [
          "arn:aws:cloudfront::${var.account_id}:distribution/*",
          "arn:aws:cloudfront::${var.account_id}:origin-access-control/*",
          "arn:aws:cloudfront::${var.account_id}:response-headers-policy/*",
        ]
        Condition = local.region_condition
      },
      {
        Sid    = "ManageProjectCloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:DeleteLogGroup",
          "logs:ListTagsForResource",
          "logs:PutRetentionPolicy",
          "logs:TagResource",
          "logs:UntagResource",
        ]
        Resource = [
          "arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${var.project}-*",
          "arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/apigateway/${var.project}",
        ]
        Condition = local.region_condition
      },
      {
        Sid    = "ManageProjectAlarmsSnsAndBudgets"
        Effect = "Allow"
        Action = [
          "budgets:CreateBudget",
          "budgets:DeleteBudget",
          "budgets:ModifyBudget",
          "budgets:TagResource",
          "budgets:UntagResource",
          "budgets:ViewBudget",
          "cloudwatch:DeleteAlarms",
          "cloudwatch:ListTagsForResource",
          "cloudwatch:PutMetricAlarm",
          "cloudwatch:TagResource",
          "cloudwatch:UntagResource",
          "sns:CreateTopic",
          "sns:DeleteTopic",
          "sns:GetSubscriptionAttributes",
          "sns:GetTopicAttributes",
          "sns:ListTagsForResource",
          "sns:SetTopicAttributes",
          "sns:Subscribe",
          "sns:TagResource",
          "sns:Unsubscribe",
          "sns:UntagResource",
        ]
        Resource = [
          "arn:aws:cloudwatch:${var.region}:${var.account_id}:alarm:${var.project}-*",
          "arn:aws:sns:${var.region}:${var.account_id}:${var.project}-alarms",
          "arn:aws:sns:${var.region}:${var.account_id}:${var.project}-alarms:*",
          "arn:aws:budgets::${var.account_id}:budget/${var.project}-*",
        ]
        Condition = local.region_condition
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "deploy_infra_edge" {
  role       = aws_iam_role.deploy.name
  policy_arn = aws_iam_policy.deploy_infra_edge.arn
}

# ---------------------------------------------------------------------------
# Política 4/4: excepciones documentadas a NFR-4 (ADR 0008)
# ---------------------------------------------------------------------------

resource "aws_iam_policy" "deploy_read" {
  # checkov:skip=CKV_AWS_356:Excepciones NFR-4 #1 y #3 (ADR 0008): ecr:GetAuthorizationToken y acciones Describe*/List* de solo lectura no admiten acotación por recurso en AWS.
  name        = local.deploy_read_policy_name
  description = "Excepciones NFR-4 #1 y #3 enumeradas para el rol monitorglucosa-deploy (ADR 0008)."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Excepción NFR-4 #1 (ADR 0008): ecr:GetAuthorizationToken no admite recurso en AWS.
      {
        Sid       = "EcrGetAuthorizationToken"
        Effect    = "Allow"
        Action    = ["ecr:GetAuthorizationToken"]
        Resource  = "*"
        Condition = local.region_condition
      },
      # Excepción NFR-4 #3 (ADR 0008): acciones de solo lectura Describe*/List* enumeradas
      # una por una que Terraform y las comprobaciones de red de Lambda exigen sobre "*".
      {
        Sid    = "TerraformAndLambdaNetworkReadOnly"
        Effect = "Allow"
        Action = [
          "cloudfront:ListDistributions",
          "cloudfront:ListOriginAccessControls",
          "cloudfront:ListResponseHeadersPolicies",
          "cloudwatch:DescribeAlarms",
          "cognito-idp:DescribeUserPoolDomain",
          "cognito-idp:ListUserPools",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeNetworkAcls",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribePrefixLists",
          "ec2:DescribeRouteTables",
          "ec2:DescribeSecurityGroupRules",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeSubnets",
          "ec2:DescribeVpcAttribute",
          "ec2:DescribeVpcEndpoints",
          "ec2:DescribeVpcs",
          "ec2:GetSecurityGroupsForVpc",
          "logs:DescribeLogGroups",
          "rds:DescribeDBClusterParameterGroups",
          "rds:DescribeDBClusterParameters",
          "rds:DescribeDBClusters",
          "rds:DescribeDBInstances",
          "rds:DescribeDBSubnetGroups",
          "sns:ListTopics",
        ]
        Resource  = "*"
        Condition = local.region_condition
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "deploy_read" {
  role       = aws_iam_role.deploy.name
  policy_arn = aws_iam_policy.deploy_read.arn
}
