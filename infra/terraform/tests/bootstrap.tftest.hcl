# Pruebas de plan con proveedores simulados para la raíz y el módulo `bootstrap`
# (Requisitos 6.1, 7.2, 8.1, 8.2, NFR-4; ADR 0007, ADR 0008, ADR 0011).

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

run "raiz_bootstrap_inicial_sin_digests_permite_primer_despliegue" {
  command = plan

  assert {
    condition     = output.tfstate_bucket_name == "monitorglucosa-tfstate-123456789012"
    error_message = "El bucket de estado debe llamarse monitorglucosa-tfstate-<cuenta>."
  }

  assert {
    condition     = output.api_image_digest == "" && output.migrator_image_digest == ""
    error_message = "Sin digests iniciales, los outputs deben quedar vacíos para que deploy.py detecte primer_despliegue=si."
  }

  # --- Requisito 8.1: versiones fijadas y backend S3 con use_lockfile = true ---
  assert {
    condition = (
      output.tfstate_bucket_name != "" &&
      can(regex("required_version\\s*=\\s*\"~> 1\\.16\\.6\"", file("${path.module}/versions.tf"))) &&
      can(regex("version\\s*=\\s*\"~> 6\\.69\\.1\"", file("${path.module}/versions.tf"))) &&
      can(regex("backend\\s+\"s3\"", file("${path.module}/versions.tf"))) &&
      can(regex("use_lockfile\\s*=\\s*true", file("${path.module}/versions.tf"))) &&
      can(regex("encrypt\\s*=\\s*true", file("${path.module}/versions.tf"))) &&
      can(regex("region\\s*=\\s*\"us-east-1\"", file("${path.module}/versions.tf")))
    )
    error_message = "versions.tf debe fijar Terraform ~> 1.16.6, AWS ~> 6.69.1 y backend S3 cifrado con use_lockfile = true en us-east-1."
  }

  # --- Requisito 8.2: default_tags obligatorias en el proveedor AWS ---
  assert {
    condition = (
      module.bootstrap.deploy_role_name == "monitorglucosa-deploy" &&
      can(regex("region\\s*=\\s*\"us-east-1\"", file("${path.module}/providers.tf"))) &&
      can(regex("default_tags\\s*\\{", file("${path.module}/providers.tf"))) &&
      can(regex("Environment\\s*=\\s*\"prod\"", file("${path.module}/providers.tf"))) &&
      can(regex("Project\\s*=\\s*\"monitorglucosa\"", file("${path.module}/providers.tf"))) &&
      can(regex("Owner\\s*=\\s*\"ldordellygithub\"", file("${path.module}/providers.tf")))
    )
    error_message = "providers.tf debe fijar us-east-1 y default_tags (Environment=prod, Project=monitorglucosa, Owner=ldordellygithub)."
  }
}

run "raiz_refleja_digests_inmutables_validos" {
  command = plan

  variables {
    api_image_digest      = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    migrator_image_digest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }

  assert {
    condition     = output.api_image_digest == var.api_image_digest
    error_message = "El output api_image_digest debe reflejar el digest inmutable recibido."
  }

  assert {
    condition     = output.migrator_image_digest == var.migrator_image_digest
    error_message = "El output migrator_image_digest debe reflejar el digest inmutable recibido."
  }
}

run "modulo_bootstrap_cumple_s3_oidc_iam_ecr_y_etiquetas" {
  command = plan

  module {
    source = "./modules/bootstrap"
  }

  variables {
    account_id            = "123456789012"
    region                = "us-east-1"
    project               = "monitorglucosa"
    github_repository     = "ldordellygithub/monitorglucosa"
    github_environment    = "prod"
    owner_email_parameter = "/monitorglucosa/prod/owner-email"
  }

  # --- Requisito 8.1: bucket del estado remoto seguro (sin bucket_key_enabled con AES256) ---
  assert {
    condition     = aws_s3_bucket.tfstate.bucket == "monitorglucosa-tfstate-123456789012"
    error_message = "El bucket de estado debe llamarse monitorglucosa-tfstate-<cuenta>."
  }

  assert {
    condition = (
      aws_s3_bucket_public_access_block.tfstate.block_public_acls &&
      aws_s3_bucket_public_access_block.tfstate.block_public_policy &&
      aws_s3_bucket_public_access_block.tfstate.ignore_public_acls &&
      aws_s3_bucket_public_access_block.tfstate.restrict_public_buckets
    )
    error_message = "El bucket de estado debe bloquear todo acceso público."
  }

  assert {
    condition     = aws_s3_bucket_versioning.tfstate.versioning_configuration[0].status == "Enabled"
    error_message = "El bucket de estado debe tener el versionado activado."
  }

  assert {
    condition = (
      one(aws_s3_bucket_server_side_encryption_configuration.tfstate.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256" &&
      one(aws_s3_bucket_server_side_encryption_configuration.tfstate.rule).bucket_key_enabled == false
    )
    error_message = "El bucket de estado debe cifrarse con SSE-S3 (AES256) y con bucket_key_enabled = false."
  }

  assert {
    condition     = aws_s3_bucket_lifecycle_configuration.tfstate.rule[0].noncurrent_version_expiration[0].noncurrent_days == 90
    error_message = "Las versiones antiguas del estado deben expirar a los 90 días."
  }

  assert {
    condition = (
      length(jsondecode(aws_s3_bucket_policy.tfstate.policy).Statement) == 1 &&
      jsondecode(aws_s3_bucket_policy.tfstate.policy).Statement[0].Effect == "Deny" &&
      jsondecode(aws_s3_bucket_policy.tfstate.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    )
    error_message = "La política del bucket de estado debe tener un Deny explícito para aws:SecureTransport = false."
  }

  # --- Requisito 7.2 y ADR 0008: OIDC estricto y confianza del rol deploy ---
  assert {
    condition     = aws_iam_openid_connect_provider.github.url == "https://token.actions.githubusercontent.com"
    error_message = "El proveedor OIDC debe apuntar a token.actions.githubusercontent.com."
  }

  assert {
    condition     = toset(aws_iam_openid_connect_provider.github.client_id_list) == toset(["sts.amazonaws.com"])
    error_message = "El proveedor OIDC debe aceptar únicamente aud = sts.amazonaws.com."
  }

  assert {
    condition = (
      aws_iam_role.deploy.name == "monitorglucosa-deploy" &&
      length(jsondecode(aws_iam_role.deploy.assume_role_policy).Statement) == 1 &&
      jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Effect == "Allow" &&
      jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Principal.Federated == "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" &&
      jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Action == "sts:AssumeRoleWithWebIdentity" &&
      jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com" &&
      jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:ldordellygithub/monitorglucosa:environment:prod"
    )
    error_message = "La política de confianza del rol deploy debe restringirse exactamente al proveedor OIDC, aud=sts.amazonaws.com y sub=repo:ldordellygithub/monitorglucosa:environment:prod."
  }

  # --- ADR 0008 / ADR 0011: todos los Allow exigen aws:RequestedRegion = us-east-1 ---
  assert {
    condition = alltrue([
      for doc in [
        jsondecode(aws_iam_policy.workload_boundary.policy),
        jsondecode(aws_iam_policy.deploy_core.policy),
        jsondecode(aws_iam_policy.deploy_infra_core.policy),
        jsondecode(aws_iam_policy.deploy_infra_edge.policy),
        jsondecode(aws_iam_policy.deploy_read.policy),
        ] : alltrue([
          for s in doc.Statement :
          s.Effect != "Allow" || try(s.Condition.StringEquals["aws:RequestedRegion"], "") == "us-east-1"
      ])
    ])
    error_message = "Todos los statements Allow en todas las políticas IAM deben exigir aws:RequestedRegion = us-east-1 (ADR 0008, ADR 0011)."
  }

  # --- ADR 0008: salvaguardas anti-escalada con Effect == Deny y boundary en acciones compatibles ---
  assert {
    condition = (
      alltrue([
        for s in jsondecode(aws_iam_policy.deploy_core.policy).Statement :
        !contains(["DenyModifyOrDeleteWorkloadBoundary", "DenyRemovePermissionsBoundary", "DenySelfModifyDeployRole"], s.Sid) || s.Effect == "Deny"
      ]) &&
      length([
        for s in jsondecode(aws_iam_policy.deploy_core.policy).Statement : s
        if s.Sid == "IamManageWorkloadRolesWithMandatoryBoundary" &&
        s.Effect == "Allow" &&
        try(s.Condition.StringEquals["iam:PermissionsBoundary"], "") == "arn:aws:iam::123456789012:policy/monitorglucosa-workload-boundary" &&
        toset(s.Resource) == toset([
          "arn:aws:iam::123456789012:role/monitorglucosa-api",
          "arn:aws:iam::123456789012:role/monitorglucosa-migrator",
        ])
      ]) == 1 &&
      length([
        for s in jsondecode(aws_iam_policy.workload_boundary.policy).Statement : s
        if s.Sid == "DenyVpcNetworkInterfacesToFunctionCode" &&
        s.Effect == "Deny" &&
        try(s.Condition.Null["lambda:SourceFunctionArn"], "") == "false"
      ]) == 1
    )
    error_message = "Las salvaguardas anti-escalada deben tener Effect=Deny, roles acotados a api/migrator y boundary bloqueando EC2 al código de Lambda."
  }

  # --- NFR-4: cero Action con comodín y cero Resource="*" fuera de las excepciones ADR 0008 ---
  assert {
    condition = alltrue([
      for doc in [
        jsondecode(aws_iam_policy.workload_boundary.policy),
        jsondecode(aws_iam_policy.deploy_core.policy),
        jsondecode(aws_iam_policy.deploy_infra_core.policy),
        jsondecode(aws_iam_policy.deploy_infra_edge.policy),
        jsondecode(aws_iam_policy.deploy_read.policy),
        ] : alltrue([
          for s in doc.Statement : alltrue([
            for act in flatten([s.Action]) : act != "*" && !endswith(act, ":*")
          ])
      ])
    ])
    error_message = "Ninguna política IAM puede contener Action \"*\" ni comodines de servicio (NFR-4)."
  }

  assert {
    condition = alltrue([
      for doc in [
        jsondecode(aws_iam_policy.deploy_core.policy),
        jsondecode(aws_iam_policy.deploy_infra_core.policy),
        jsondecode(aws_iam_policy.deploy_infra_edge.policy),
        ] : alltrue([
          for s in doc.Statement : !contains(flatten([s.Resource]), "*")
      ])
    ])
    error_message = "deploy_core, deploy_infra_core y deploy_infra_edge no pueden usar Resource=\"*\" (NFR-4, ADR 0008)."
  }

  # --- Límite AWS de políticas gestionadas (<= 6144 caracteres sin espacios) ---
  assert {
    condition = alltrue([
      for p in [
        aws_iam_policy.workload_boundary.policy,
        aws_iam_policy.deploy_core.policy,
        aws_iam_policy.deploy_infra_core.policy,
        aws_iam_policy.deploy_infra_edge.policy,
        aws_iam_policy.deploy_read.policy,
      ] : length(p) <= 6144
    ])
    error_message = "Cada política IAM gestionada debe mantenerse por debajo del límite AWS de 6144 caracteres."
  }

  # --- D11 / mínimo privilegio KMS: descifrado SSM acotado al parámetro exacto ---
  assert {
    condition = (
      length([
        for s in jsondecode(aws_iam_policy.deploy_infra_edge.policy).Statement : s
        if s.Sid == "DecryptOwnerEmailParameterViaSsm" &&
        s.Effect == "Allow" &&
        try(s.Condition.StringEquals["kms:ViaService"], "") == "ssm.us-east-1.amazonaws.com" &&
        try(s.Condition.StringEquals["kms:EncryptionContext:PARAMETER_ARN"], "") == "arn:aws:ssm:us-east-1:123456789012:parameter/monitorglucosa/prod/owner-email"
      ]) == 1 &&
      length([
        for s in jsondecode(aws_iam_policy.deploy_infra_edge.policy).Statement : s
        if s.Sid == "ManageProjectSiteBucket" &&
        contains(s.Action, "s3:PutObjectTagging") &&
        contains(s.Action, "s3:GetObjectTagging")
      ]) == 1 &&
      length([
        for s in jsondecode(aws_iam_policy.deploy_read.policy).Statement : s
        if s.Sid == "ApiGatewayV2AccessLogDelivery" &&
        contains(s.Action, "logs:CreateLogDelivery")
      ]) == 1
    )
    error_message = "deploy_infra_edge y deploy_read deben acotar KMS por PARAMETER_ARN, permitir tagging S3 del sitio y Vended Logs de HTTP API v2."
  }

  # --- Requisito 6.1: ECR inmutable, escaneo al subir, AES256, 10 imágenes y política Lambda ---
  assert {
    condition = (
      aws_ecr_repository.api.name == "monitorglucosa-api" &&
      aws_ecr_repository.api.image_tag_mutability == "IMMUTABLE" &&
      aws_ecr_repository.api.image_scanning_configuration[0].scan_on_push == true &&
      aws_ecr_repository.api.encryption_configuration[0].encryption_type == "AES256"
    )
    error_message = "ECR debe ser monitorglucosa-api, IMMUTABLE, con scan_on_push=true y cifrado AES256."
  }

  assert {
    condition = (
      jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[0].selection.countNumber == 10 &&
      jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[0].selection.tagStatus == "any" &&
      jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[0].action.type == "expire"
    )
    error_message = "La política de ciclo de vida de ECR debe expirar por encima de 10 imágenes (tagStatus=any)."
  }

  assert {
    condition = (
      length(jsondecode(aws_ecr_repository_policy.api.policy).Statement) == 1 &&
      jsondecode(aws_ecr_repository_policy.api.policy).Statement[0].Principal.Service == "lambda.amazonaws.com" &&
      jsondecode(aws_ecr_repository_policy.api.policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "123456789012" &&
      toset(jsondecode(aws_ecr_repository_policy.api.policy).Statement[0].Condition.ArnEquals["aws:sourceArn"]) == toset([
        "arn:aws:lambda:us-east-1:123456789012:function:monitorglucosa-api",
        "arn:aws:lambda:us-east-1:123456789012:function:monitorglucosa-migrator",
      ])
    )
    error_message = "La política de ECR debe restringir el pull de Lambda con ArnEquals a api/migrator y SourceAccount."
  }

  # --- Requisito 8.2: ningún recurso etiquetable sobreescribe las default_tags obligatorias ---
  assert {
    condition = alltrue([
      for res_tags in [
        aws_s3_bucket.tfstate.tags,
        aws_ecr_repository.api.tags,
        aws_iam_openid_connect_provider.github.tags,
        aws_iam_policy.workload_boundary.tags,
        aws_iam_role.deploy.tags,
        aws_iam_policy.deploy_core.tags,
        aws_iam_policy.deploy_infra_core.tags,
        aws_iam_policy.deploy_infra_edge.tags,
        aws_iam_policy.deploy_read.tags,
        ] : (
        try(res_tags["Environment"], "prod") == "prod" &&
        try(res_tags["Project"], "monitorglucosa") == "monitorglucosa" &&
        try(res_tags["Owner"], "ldordellygithub") == "ldordellygithub"
      )
    ])
    error_message = "Ningún recurso etiquetable de bootstrap puede anular o contradecir Environment, Project u Owner heredados de default_tags."
  }
}

run "modulo_bootstrap_acota_data_api_y_secreto_a_arns_exactos" {
  command = plan

  module {
    source = "./modules/bootstrap"
  }

  variables {
    account_id            = "123456789012"
    region                = "us-east-1"
    project               = "monitorglucosa"
    github_repository     = "ldordellygithub/monitorglucosa"
    github_environment    = "prod"
    owner_email_parameter = "/monitorglucosa/prod/owner-email"
    aurora_cluster_arn    = "arn:aws:rds:us-east-1:123456789012:cluster:monitorglucosa-aurora"
    master_secret_arn     = "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds!cluster-abc123"
  }

  assert {
    condition = (
      length([
        for s in jsondecode(aws_iam_policy.deploy_core.policy).Statement : s
        if s.Sid == "ExecuteBootstrapSqlViaDataApi" &&
        s.Resource == ["arn:aws:rds:us-east-1:123456789012:cluster:monitorglucosa-aurora"]
      ]) == 1 &&
      length([
        for s in jsondecode(aws_iam_policy.deploy_core.policy).Statement : s
        if s.Sid == "ReadAuroraMasterSecretForBootstrap" &&
        s.Resource == ["arn:aws:secretsmanager:us-east-1:123456789012:secret:rds!cluster-abc123"]
      ]) == 1
    )
    error_message = "Cuando se inyectan los ARNs de Aurora y del secreto maestro, deploy_core debe acotar Data API y Secrets Manager a esos ARNs exactos (ADR 0007)."
  }
}

run "rechaza_digest_no_inmutable_en_api" {
  command = plan

  variables {
    api_image_digest = "latest"
  }

  expect_failures = [
    var.api_image_digest,
  ]
}

run "rechaza_digest_no_inmutable_en_migrator" {
  command = plan

  variables {
    migrator_image_digest = "sha256:ZZZZ"
  }

  expect_failures = [
    var.migrator_image_digest,
  ]
}

run "rechaza_region_distinta_de_us_east_1" {
  command = plan

  module {
    source = "./modules/bootstrap"
  }

  variables {
    account_id            = "123456789012"
    region                = "sa-east-1"
    project               = "monitorglucosa"
    github_repository     = "ldordellygithub/monitorglucosa"
    github_environment    = "prod"
    owner_email_parameter = "/monitorglucosa/prod/owner-email"
  }

  expect_failures = [
    var.region,
  ]
}

run "rechaza_master_secret_arn_con_comodin_o_prefijo_invalido" {
  command = plan

  module {
    source = "./modules/bootstrap"
  }

  variables {
    account_id            = "123456789012"
    region                = "us-east-1"
    project               = "monitorglucosa"
    github_repository     = "ldordellygithub/monitorglucosa"
    github_environment    = "prod"
    owner_email_parameter = "/monitorglucosa/prod/owner-email"
    master_secret_arn     = "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds-db-credentials/*"
  }

  expect_failures = [
    var.master_secret_arn,
  ]
}
