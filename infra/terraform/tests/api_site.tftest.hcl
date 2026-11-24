# Pruebas de plan con proveedores simulados para los módulos `site` y `api`
# (Requisitos 4.5, 6.1, 6.2, 6.3, 6.4, 6.5, 8.2, NFR-4, NFR-5; D2, D7, D9, D13, ADR 0005, ADR 0006, ADR 0008).

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

run "raiz_conecta_site_identity_y_api_con_digests_y_sin_placeholder" {
  command = plan

  variables {
    api_image_digest      = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    migrator_image_digest = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
  }

  override_resource {
    target          = module.site.aws_cloudfront_distribution.site
    override_during = plan
    values = {
      domain_name = "d111111abcdef8.cloudfront.net"
    }
  }

  override_resource {
    target          = module.bootstrap.aws_iam_policy.workload_boundary
    override_during = plan
    values = {
      arn = "arn:aws:iam::123456789012:policy/monitorglucosa-workload-boundary"
    }
  }

  override_resource {
    target          = module.bootstrap.aws_ecr_repository.api
    override_during = plan
    values = {
      repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/monitorglucosa-api"
    }
  }

  override_resource {
    target          = module.database.aws_rds_cluster.aurora
    override_during = plan
    values = {
      endpoint            = "monitorglucosa-aurora.cluster-mock12345.us-east-1.rds.amazonaws.com"
      cluster_resource_id = "cluster-MOCKRESOURCEID1234"
    }
  }

  override_resource {
    target          = module.identity.aws_cognito_user_pool.main
    override_during = plan
    values = {
      id       = "us-east-1_AbCdEfGhI"
      endpoint = "cognito-idp.us-east-1.amazonaws.com/us-east-1_AbCdEfGhI"
    }
  }

  override_resource {
    target          = module.api.aws_apigatewayv2_api.main
    override_during = plan
    values = {
      api_endpoint  = "https://abc123def4.execute-api.us-east-1.amazonaws.com"
      execution_arn = "arn:aws:execute-api:us-east-1:123456789012:abc123def4"
    }
  }

  assert {
    condition = (
      output.site_domain == "d111111abcdef8.cloudfront.net" &&
      !strcontains(output.site_domain, "placeholder") &&
      output.api_endpoint == "https://abc123def4.execute-api.us-east-1.amazonaws.com" &&
      module.api.api_function_name == "monitorglucosa-api" &&
      module.api.migrator_function_name == "monitorglucosa-migrator"
    )
    error_message = "La raíz debe conectar site -> identity y api sin placeholder, y exponer site_domain y api_endpoint."
  }
}

run "modulo_site_crea_bucket_privado_oac_cloudfront_hsts_y_csp" {
  command = plan

  module {
    source = "./modules/site"
  }

  variables {
    account_id = "123456789012"
    project    = "monitorglucosa"
  }

  override_resource {
    target          = aws_s3_bucket.site
    override_during = plan
    values = {
      arn = "arn:aws:s3:::monitorglucosa-site-123456789012"
    }
  }

  override_resource {
    target          = aws_cloudfront_distribution.site
    override_during = plan
    values = {
      arn         = "arn:aws:cloudfront::123456789012:distribution/E1234567890ABC"
      domain_name = "d111111abcdef8.cloudfront.net"
    }
  }

  # --- Requisito 6.4: bucket S3 privado, cifrado SSE-S3, versionado y ciclo de vida ---
  assert {
    condition = (
      aws_s3_bucket.site.bucket == "monitorglucosa-site-123456789012" &&
      aws_s3_bucket_ownership_controls.site.rule[0].object_ownership == "BucketOwnerEnforced" &&
      aws_s3_bucket_public_access_block.site.block_public_acls &&
      aws_s3_bucket_public_access_block.site.block_public_policy &&
      aws_s3_bucket_public_access_block.site.ignore_public_acls &&
      aws_s3_bucket_public_access_block.site.restrict_public_buckets &&
      aws_s3_bucket_versioning.site.versioning_configuration[0].status == "Enabled" &&
      one(aws_s3_bucket_server_side_encryption_configuration.site.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256" &&
      one(aws_s3_bucket_server_side_encryption_configuration.site.rule).bucket_key_enabled == false &&
      aws_s3_bucket_lifecycle_configuration.site.rule[0].noncurrent_version_expiration[0].noncurrent_days == 30
    )
    error_message = "El bucket S3 del sitio debe ser privado, SSE-S3 (AES256, bucket_key_enabled=false), BucketOwnerEnforced y versionado."
  }

  # --- Página provisional index.html compatible con CSP estricta (sin scripts ni estilos en línea) ---
  assert {
    condition = (
      aws_s3_object.index.key == "index.html" &&
      aws_s3_object.index.content_type == "text/html; charset=utf-8" &&
      strcontains(aws_s3_object.index.content, "monitorglucosa") &&
      !strcontains(lower(aws_s3_object.index.content), "<script") &&
      !strcontains(lower(aws_s3_object.index.content), "<style") &&
      !strcontains(lower(aws_s3_object.index.content), "style=")
    )
    error_message = "index.html provisional debe servirse como text/html sin scripts ni estilos inline (compatible con CSP D13)."
  }

  # --- Requisito 6.4 y D13: OAC SigV4, cabeceras HSTS + CSP + nosniff + DENY + no-referrer ---
  assert {
    condition = (
      aws_cloudfront_origin_access_control.site.origin_access_control_origin_type == "s3" &&
      aws_cloudfront_origin_access_control.site.signing_behavior == "always" &&
      aws_cloudfront_origin_access_control.site.signing_protocol == "sigv4" &&
      aws_cloudfront_response_headers_policy.site.security_headers_config[0].strict_transport_security[0].access_control_max_age_sec == 63072000 &&
      aws_cloudfront_response_headers_policy.site.security_headers_config[0].strict_transport_security[0].include_subdomains == true &&
      aws_cloudfront_response_headers_policy.site.security_headers_config[0].content_security_policy[0].content_security_policy == "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" &&
      aws_cloudfront_response_headers_policy.site.security_headers_config[0].content_type_options[0].override == true &&
      aws_cloudfront_response_headers_policy.site.security_headers_config[0].frame_options[0].frame_option == "DENY" &&
      aws_cloudfront_response_headers_policy.site.security_headers_config[0].referrer_policy[0].referrer_policy == "no-referrer"
    )
    error_message = "CloudFront debe usar OAC SigV4 y aplicar HSTS (2 años, includeSubDomains), CSP estricta D13, nosniff, DENY y no-referrer."
  }

  # --- Distribución CloudFront HTTPS obligatorio + default_root_object ---
  assert {
    condition = (
      aws_cloudfront_distribution.site.enabled == true &&
      aws_cloudfront_distribution.site.default_root_object == "index.html" &&
      aws_cloudfront_distribution.site.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https" &&
      toset(aws_cloudfront_distribution.site.default_cache_behavior[0].allowed_methods) == toset(["GET", "HEAD"]) &&
      aws_cloudfront_distribution.site.viewer_certificate[0].cloudfront_default_certificate == true
    )
    error_message = "La distribución CloudFront debe exigir redirect-to-https, GET/HEAD y default_root_object = index.html."
  }

  # --- Política del bucket: solo esta distribución CloudFront (AWS:SourceArn) + Deny sin TLS ---
  assert {
    condition = (
      length(jsondecode(aws_s3_bucket_policy.site.policy).Statement) == 2 &&
      length([
        for s in jsondecode(aws_s3_bucket_policy.site.policy).Statement : s
        if s.Effect == "Allow" &&
        s.Principal.Service == "cloudfront.amazonaws.com" &&
        toset(s.Action) == toset(["s3:GetObject"]) &&
        s.Condition.StringEquals["AWS:SourceArn"] == "arn:aws:cloudfront::123456789012:distribution/E1234567890ABC"
      ]) == 1 &&
      length([
        for s in jsondecode(aws_s3_bucket_policy.site.policy).Statement : s
        if s.Effect == "Deny" &&
        s.Condition.Bool["aws:SecureTransport"] == "false"
      ]) == 1
    )
    error_message = "La política del bucket del sitio debe permitir solo s3:GetObject desde CloudFront (AWS:SourceArn) y denegar transporte sin TLS."
  }

  # --- Requisito 8.2: no sobreescribe default_tags ---
  assert {
    condition = alltrue([
      for res_tags in [
        aws_s3_bucket.site.tags,
        aws_cloudfront_distribution.site.tags,
        ] : (
        try(res_tags["Environment"], "prod") == "prod" &&
        try(res_tags["Project"], "monitorglucosa") == "monitorglucosa" &&
        try(res_tags["Owner"], "ldordellygithub") == "ldordellygithub"
      )
    ])
    error_message = "Los recursos etiquetables de site no deben sobrescribir default_tags."
  }
}

run "modulo_api_cumple_lambdas_jwt_iam_throttling_cors_y_boundary" {
  command = plan

  module {
    source = "./modules/api"
  }

  variables {
    account_id                  = "123456789012"
    region                      = "us-east-1"
    project                     = "monitorglucosa"
    workload_boundary_arn       = "arn:aws:iam::123456789012:policy/monitorglucosa-workload-boundary"
    ecr_repository_url          = "123456789012.dkr.ecr.us-east-1.amazonaws.com/monitorglucosa-api"
    api_image_digest            = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    migrator_image_digest       = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    private_subnet_ids          = ["subnet-0111111111111111a", "subnet-0222222222222222b"]
    api_security_group_id       = "sg-0111111111111111a"
    migrator_security_group_id  = "sg-0222222222222222b"
    database_host               = "monitorglucosa-aurora.cluster-mock12345.us-east-1.rds.amazonaws.com"
    database_port               = 5432
    database_name               = "monitorglucosa"
    aurora_cluster_resource_id  = "cluster-MOCKRESOURCEID1234"
    cognito_issuer              = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_AbCdEfGhI"
    cognito_web_client_id       = "1111webclientid1111"
    cognito_collector_client_id = "2222collectorclientid2222"
    site_domain                 = "d111111abcdef8.cloudfront.net"
    access_log_group_arn        = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/apigateway/monitorglucosa"
  }

  override_resource {
    target          = aws_apigatewayv2_api.main
    override_during = plan
    values = {
      execution_arn = "arn:aws:execute-api:us-east-1:123456789012:abc123def4"
      api_endpoint  = "https://abc123def4.execute-api.us-east-1.amazonaws.com"
    }
  }

  # --- Requisito 6.1, D2, D7, D13: Lambda api por digest en VPC sin secretos en env ---
  assert {
    condition = (
      length(aws_lambda_function.api) == 1 &&
      aws_lambda_function.api[0].function_name == "monitorglucosa-api" &&
      aws_lambda_function.api[0].package_type == "Image" &&
      aws_lambda_function.api[0].image_uri == "123456789012.dkr.ecr.us-east-1.amazonaws.com/monitorglucosa-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" &&
      toset(aws_lambda_function.api[0].architectures) == toset(["x86_64"]) &&
      aws_lambda_function.api[0].memory_size == 512 &&
      aws_lambda_function.api[0].timeout == 30 &&
      aws_lambda_function.api[0].reserved_concurrent_executions == null &&
      toset(aws_lambda_function.api[0].vpc_config[0].subnet_ids) == toset(["subnet-0111111111111111a", "subnet-0222222222222222b"]) &&
      toset(aws_lambda_function.api[0].vpc_config[0].security_group_ids) == toset(["sg-0111111111111111a"]) &&
      aws_lambda_function.api[0].environment[0].variables["ENVIRONMENT"] == "prod" &&
      aws_lambda_function.api[0].environment[0].variables["DATABASE_USER"] == "mg_api" &&
      aws_lambda_function.api[0].environment[0].variables["DATABASE_CONNECT_TIMEOUT_S"] == "20" &&
      aws_lambda_function.api[0].environment[0].variables["AWS_LWA_READINESS_CHECK_PATH"] == "/health" &&
      !contains(keys(aws_lambda_function.api[0].environment[0].variables), "DATABASE_PASSWORD") &&
      !contains(keys(aws_lambda_function.api[0].environment[0].variables), "LOCAL_JWT_ISSUER")
    )
    error_message = "La Lambda api debe desplegarse por digest en VPC (512 MB, 30 s, x86_64), con mg_api, LWA /health y sin secretos."
  }

  # --- Requisito 6.1, D2, ADR 0006: Lambda migrator con misma imagen, comando create_migrator_app y 300 s ---
  assert {
    condition = (
      length(aws_lambda_function.migrator) == 1 &&
      aws_lambda_function.migrator[0].function_name == "monitorglucosa-migrator" &&
      aws_lambda_function.migrator[0].package_type == "Image" &&
      aws_lambda_function.migrator[0].image_uri == "123456789012.dkr.ecr.us-east-1.amazonaws.com/monitorglucosa-api@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" &&
      toset(aws_lambda_function.migrator[0].architectures) == toset(["x86_64"]) &&
      aws_lambda_function.migrator[0].memory_size == 512 &&
      aws_lambda_function.migrator[0].timeout == 300 &&
      contains(aws_lambda_function.migrator[0].image_config[0].command, "src.main:create_migrator_app") &&
      contains(aws_lambda_function.migrator[0].image_config[0].command, "--factory") &&
      aws_lambda_function.migrator[0].environment[0].variables["DATABASE_USER"] == "mg_migrator" &&
      aws_lambda_function.migrator[0].environment[0].variables["AWS_LWA_READINESS_CHECK_PATH"] == "/" &&
      aws_lambda_function.migrator[0].environment[0].variables["AWS_LWA_PASS_THROUGH_PATH"] == "/events" &&
      !contains(keys(aws_lambda_function.migrator[0].environment[0].variables), "DATABASE_PASSWORD")
    )
    error_message = "La Lambda migrator debe usar la misma imagen por digest con create_migrator_app, 300 s, mg_migrator y LWA /events."
  }

  # --- ADR 0008 / NFR-4: roles con boundary obligatorio, rds-db:connect separado y Deny EC2 al código ---
  assert {
    condition = (
      aws_iam_role.api.permissions_boundary == "arn:aws:iam::123456789012:policy/monitorglucosa-workload-boundary" &&
      aws_iam_role.migrator.permissions_boundary == "arn:aws:iam::123456789012:policy/monitorglucosa-workload-boundary" &&
      length([
        for s in jsondecode(aws_iam_role_policy.api.policy).Statement : s
        if s.Sid == "AllowAuroraIamConnectApi" &&
        s.Resource == ["arn:aws:rds-db:us-east-1:123456789012:dbuser:cluster-MOCKRESOURCEID1234/mg_api"]
      ]) == 1 &&
      length([
        for s in jsondecode(aws_iam_role_policy.migrator.policy).Statement : s
        if s.Sid == "AllowAuroraIamConnectMigrator" &&
        s.Resource == ["arn:aws:rds-db:us-east-1:123456789012:dbuser:cluster-MOCKRESOURCEID1234/mg_migrator"]
      ]) == 1 &&
      alltrue([
        for doc in [
          jsondecode(aws_iam_role_policy.api.policy),
          jsondecode(aws_iam_role_policy.migrator.policy),
          ] : (
          length([
            for s in doc.Statement : s
            if s.Sid == "DenyVpcNetworkInterfacesToFunctionCode" &&
            s.Effect == "Deny" &&
            try(s.Condition.Null["lambda:SourceFunctionArn"], "") == "false"
          ]) == 1 &&
          alltrue([
            for s in doc.Statement :
            s.Effect != "Allow" || try(s.Condition.StringEquals["aws:RequestedRegion"], "") == "us-east-1"
          ]) &&
          alltrue([
            for s in doc.Statement : alltrue([
              for act in flatten([s.Action]) : act != "*" && !endswith(act, ":*")
            ])
          ])
        )
      ])
    )
    error_message = "Los roles de api y migrator deben llevar workload-boundary, rds-db:connect separado, aws:RequestedRegion=us-east-1 y Deny EC2 al código."
  }

  # --- Requisitos 4.5, 6.2 y D9: autorizador JWT (issuer + web/collector) y 3 rutas (JWT openid, NONE, AWS_IAM) ---
  assert {
    condition = (
      aws_apigatewayv2_api.main.protocol_type == "HTTP" &&
      aws_apigatewayv2_authorizer.cognito.authorizer_type == "JWT" &&
      toset(aws_apigatewayv2_authorizer.cognito.identity_sources) == toset(["$request.header.Authorization"]) &&
      aws_apigatewayv2_authorizer.cognito.jwt_configuration[0].issuer == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_AbCdEfGhI" &&
      toset(aws_apigatewayv2_authorizer.cognito.jwt_configuration[0].audience) == toset(["1111webclientid1111", "2222collectorclientid2222"]) &&
      aws_apigatewayv2_route.api_v1[0].route_key == "GET /api/v1/{proxy+}" &&
      aws_apigatewayv2_route.api_v1[0].authorization_type == "JWT" &&
      toset(aws_apigatewayv2_route.api_v1[0].authorization_scopes) == toset(["openid"]) &&
      aws_apigatewayv2_route.health[0].route_key == "GET /health" &&
      aws_apigatewayv2_route.health[0].authorization_type == "NONE" &&
      aws_apigatewayv2_route.health_ready[0].route_key == "GET /health/ready" &&
      aws_apigatewayv2_route.health_ready[0].authorization_type == "AWS_IAM" &&
      aws_apigatewayv2_integration.api[0].payload_format_version == "2.0" &&
      aws_apigatewayv2_integration.api[0].timeout_milliseconds == 30000
    )
    error_message = "HTTP API debe exigir JWT+openid en /api/v1/{proxy+}, NONE en /health y AWS_IAM en /health/ready con integración v2.0 (30 s)."
  }

  # --- Requisitos 6.3, 6.5, D13, NFR-5: throttling 10/20, CORS CloudFront, logs JSON sin PII y source_arn ---
  assert {
    condition = (
      toset(aws_apigatewayv2_api.main.cors_configuration[0].allow_origins) == toset(["https://d111111abcdef8.cloudfront.net"]) &&
      toset(aws_apigatewayv2_api.main.cors_configuration[0].allow_methods) == toset(["GET"]) &&
      toset(aws_apigatewayv2_api.main.cors_configuration[0].allow_headers) == toset(["authorization", "content-type"]) &&
      aws_apigatewayv2_api.main.cors_configuration[0].allow_credentials == false &&
      aws_apigatewayv2_api.main.cors_configuration[0].max_age == 3600 &&
      aws_apigatewayv2_stage.default.name == "$default" &&
      aws_apigatewayv2_stage.default.auto_deploy == true &&
      aws_apigatewayv2_stage.default.default_route_settings[0].throttling_rate_limit == 10 &&
      aws_apigatewayv2_stage.default.default_route_settings[0].throttling_burst_limit == 20 &&
      aws_apigatewayv2_stage.default.access_log_settings[0].destination_arn == "arn:aws:logs:us-east-1:123456789012:log-group:/aws/apigateway/monitorglucosa" &&
      toset(keys(jsondecode(aws_apigatewayv2_stage.default.access_log_settings[0].format))) == toset(["requestId", "routeKey", "status", "responseLatency", "authorizerError"]) &&
      !strcontains(aws_apigatewayv2_stage.default.access_log_settings[0].format, "sourceIp") &&
      !strcontains(aws_apigatewayv2_stage.default.access_log_settings[0].format, "Authorization") &&
      aws_lambda_permission.api[0].principal == "apigateway.amazonaws.com" &&
      aws_lambda_permission.api[0].action == "lambda:InvokeFunction" &&
      aws_lambda_permission.api[0].source_arn == "arn:aws:execute-api:us-east-1:123456789012:abc123def4/*/*"
    )
    error_message = "HTTP API debe fijar CORS solo para CloudFront, throttling 10/20, logs JSON sin PII y permiso Lambda con source_arn."
  }

  # --- Requisito 8.2: no sobreescribe default_tags ---
  assert {
    condition = alltrue([
      for res_tags in [
        aws_iam_role.api.tags,
        aws_iam_role.migrator.tags,
        aws_lambda_function.api[0].tags,
        aws_lambda_function.migrator[0].tags,
        aws_apigatewayv2_api.main.tags,
        aws_apigatewayv2_stage.default.tags,
        ] : (
        try(res_tags["Environment"], "prod") == "prod" &&
        try(res_tags["Project"], "monitorglucosa") == "monitorglucosa" &&
        try(res_tags["Owner"], "ldordellygithub") == "ldordellygithub"
      )
    ])
    error_message = "Los recursos etiquetables de api no deben sobrescribir default_tags."
  }
}

run "modulo_api_sin_digests_omite_lambdas_para_bootstrap" {
  command = plan

  module {
    source = "./modules/api"
  }

  variables {
    account_id                  = "123456789012"
    region                      = "us-east-1"
    project                     = "monitorglucosa"
    workload_boundary_arn       = "arn:aws:iam::123456789012:policy/monitorglucosa-workload-boundary"
    ecr_repository_url          = "123456789012.dkr.ecr.us-east-1.amazonaws.com/monitorglucosa-api"
    private_subnet_ids          = ["subnet-0111111111111111a", "subnet-0222222222222222b"]
    api_security_group_id       = "sg-0111111111111111a"
    migrator_security_group_id  = "sg-0222222222222222b"
    database_host               = "monitorglucosa-aurora.cluster-mock12345.us-east-1.rds.amazonaws.com"
    database_port               = 5432
    database_name               = "monitorglucosa"
    aurora_cluster_resource_id  = "cluster-MOCKRESOURCEID1234"
    cognito_issuer              = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_AbCdEfGhI"
    cognito_web_client_id       = "1111webclientid1111"
    cognito_collector_client_id = "2222collectorclientid2222"
    site_domain                 = "d111111abcdef8.cloudfront.net"
    access_log_group_arn        = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/apigateway/monitorglucosa"
  }

  assert {
    condition = (
      length(aws_lambda_function.api) == 0 &&
      length(aws_lambda_function.migrator) == 0 &&
      length(aws_apigatewayv2_route.api_v1) == 0 &&
      length(aws_lambda_permission.api) == 0
    )
    error_message = "Sin digests iniciales, las Lambdas, rutas y permisos no deben crearse hasta el primer despliegue."
  }
}

run "rechaza_site_domain_invalido_en_api" {
  command = plan

  module {
    source = "./modules/api"
  }

  variables {
    account_id                  = "123456789012"
    region                      = "us-east-1"
    project                     = "monitorglucosa"
    workload_boundary_arn       = "arn:aws:iam::123456789012:policy/monitorglucosa-workload-boundary"
    ecr_repository_url          = "123456789012.dkr.ecr.us-east-1.amazonaws.com/monitorglucosa-api"
    private_subnet_ids          = ["subnet-0111111111111111a", "subnet-0222222222222222b"]
    api_security_group_id       = "sg-0111111111111111a"
    migrator_security_group_id  = "sg-0222222222222222b"
    database_host               = "monitorglucosa-aurora.cluster-mock12345.us-east-1.rds.amazonaws.com"
    database_port               = 5432
    database_name               = "monitorglucosa"
    aurora_cluster_resource_id  = "cluster-MOCKRESOURCEID1234"
    cognito_issuer              = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_AbCdEfGhI"
    cognito_web_client_id       = "1111webclientid1111"
    cognito_collector_client_id = "2222collectorclientid2222"
    site_domain                 = "https://evil.example.com/*"
    access_log_group_arn        = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/apigateway/monitorglucosa"
  }

  expect_failures = [
    var.site_domain,
  ]
}

run "rechaza_aurora_cluster_resource_id_con_comodin" {
  command = plan

  module {
    source = "./modules/api"
  }

  variables {
    account_id                  = "123456789012"
    region                      = "us-east-1"
    project                     = "monitorglucosa"
    workload_boundary_arn       = "arn:aws:iam::123456789012:policy/monitorglucosa-workload-boundary"
    ecr_repository_url          = "123456789012.dkr.ecr.us-east-1.amazonaws.com/monitorglucosa-api"
    private_subnet_ids          = ["subnet-0111111111111111a", "subnet-0222222222222222b"]
    api_security_group_id       = "sg-0111111111111111a"
    migrator_security_group_id  = "sg-0222222222222222b"
    database_host               = "monitorglucosa-aurora.cluster-mock12345.us-east-1.rds.amazonaws.com"
    database_port               = 5432
    database_name               = "monitorglucosa"
    aurora_cluster_resource_id  = "*"
    cognito_issuer              = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_AbCdEfGhI"
    cognito_web_client_id       = "1111webclientid1111"
    cognito_collector_client_id = "2222collectorclientid2222"
    site_domain                 = "d111111abcdef8.cloudfront.net"
    access_log_group_arn        = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/apigateway/monitorglucosa"
  }

  expect_failures = [
    var.aurora_cluster_resource_id,
  ]
}
