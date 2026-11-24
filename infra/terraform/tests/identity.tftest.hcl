# Pruebas de plan con proveedores simulados para el módulo `identity`
# (Requisitos 4.1, 4.2, 4.3, 4.4, 8.2; D11, D12, ADR 0003).

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

run "raiz_conecta_modulo_identity_y_expone_prefijo_dominio" {
  command = plan

  override_resource {
    target          = module.identity.aws_cognito_user_pool.main
    override_during = plan
    values = {
      id = "us-east-1_AbCdEfGhI"
    }
  }

  assert {
    condition = (
      can(regex("^monitorglucosa-[0-9a-f]{8}$", output.cognito_domain_prefix)) &&
      !strcontains(output.cognito_domain_prefix, "123456789012") &&
      output.cognito_domain_prefix != "monitorglucosa-${substr(sha256("123456789012-monitorglucosa"), 0, 8)}"
    )
    error_message = "El prefijo de dominio Cognito debe tener formato monitorglucosa-<8 hex> sin correlación con el ID de cuenta."
  }
}

run "modulo_identity_cumple_essentials_totp_clientes_web_y_collector_y_usuario" {
  command = plan

  module {
    source = "./modules/identity"
  }

  variables {
    project               = "monitorglucosa"
    owner_email_parameter = "/monitorglucosa/prod/owner-email"
    site_domain           = "d111111abcdef8.cloudfront.net"
  }

  override_resource {
    target          = aws_cognito_user_pool.main
    override_during = plan
    values = {
      id = "us-east-1_AbCdEfGhI"
    }
  }

  # --- Requisito 4.1: User Pool Essentials, MFA TOTP obligatorio sin SMS, sin registro propio, deletion_protection ---
  assert {
    condition = (
      aws_cognito_user_pool.main.name == "monitorglucosa-users" &&
      aws_cognito_user_pool.main.user_pool_tier == "ESSENTIALS" &&
      aws_cognito_user_pool.main.mfa_configuration == "ON" &&
      aws_cognito_user_pool.main.software_token_mfa_configuration[0].enabled == true &&
      length(aws_cognito_user_pool.main.sms_configuration) == 0 &&
      aws_cognito_user_pool.main.admin_create_user_config[0].allow_admin_create_user_only == true &&
      aws_cognito_user_pool.main.deletion_protection == "ACTIVE" &&
      toset(aws_cognito_user_pool.main.username_attributes) == toset(["email"]) &&
      aws_cognito_user_pool.main.email_configuration[0].email_sending_account == "COGNITO_DEFAULT"
    )
    error_message = "El User Pool debe ser Essentials, MFA TOTP ON sin SMS, sin auto-registro y con deletion_protection ACTIVE."
  }

  assert {
    condition = (
      aws_cognito_user_pool.main.password_policy[0].minimum_length >= 12 &&
      aws_cognito_user_pool.main.password_policy[0].require_lowercase == true &&
      aws_cognito_user_pool.main.password_policy[0].require_uppercase == true &&
      aws_cognito_user_pool.main.password_policy[0].require_numbers == true &&
      aws_cognito_user_pool.main.password_policy[0].require_symbols == true
    )
    error_message = "La política de contraseñas del User Pool debe exigir mínimo 12 caracteres y complejidad completa."
  }

  # --- Dominio de prefijo único sin ID de cuenta ---
  assert {
    condition     = can(regex("^monitorglucosa-[0-9a-f]{8}$", aws_cognito_user_pool_domain.main.domain))
    error_message = "El dominio de Cognito debe tener formato monitorglucosa-<8 hex>."
  }

  # --- Requisito 4.3: cliente público web (PKCE, sin secreto, refresh 1 día, CloudFront) ---
  assert {
    condition = (
      aws_cognito_user_pool_client.web.name == "web" &&
      aws_cognito_user_pool_client.web.generate_secret == false &&
      aws_cognito_user_pool_client.web.allowed_oauth_flows_user_pool_client == true &&
      toset(aws_cognito_user_pool_client.web.allowed_oauth_flows) == toset(["code"]) &&
      toset(aws_cognito_user_pool_client.web.allowed_oauth_scopes) == toset(["openid"]) &&
      toset(aws_cognito_user_pool_client.web.supported_identity_providers) == toset(["COGNITO"]) &&
      toset(aws_cognito_user_pool_client.web.callback_urls) == toset(["https://d111111abcdef8.cloudfront.net/auth/callback"]) &&
      toset(aws_cognito_user_pool_client.web.logout_urls) == toset(["https://d111111abcdef8.cloudfront.net/"]) &&
      aws_cognito_user_pool_client.web.access_token_validity == 60 &&
      aws_cognito_user_pool_client.web.id_token_validity == 60 &&
      aws_cognito_user_pool_client.web.refresh_token_validity == 1 &&
      aws_cognito_user_pool_client.web.token_validity_units[0].access_token == "minutes" &&
      aws_cognito_user_pool_client.web.token_validity_units[0].id_token == "minutes" &&
      aws_cognito_user_pool_client.web.token_validity_units[0].refresh_token == "days" &&
      aws_cognito_user_pool_client.web.prevent_user_existence_errors == "ENABLED" &&
      aws_cognito_user_pool_client.web.enable_token_revocation == true &&
      toset(aws_cognito_user_pool_client.web.explicit_auth_flows) == toset(["ALLOW_REFRESH_TOKEN_AUTH"])
    )
    error_message = "El cliente web debe ser público, código+PKCE, openid, refresh 1 día y callbacks en CloudFront."
  }

  # --- Requisito 4.4 y ADR 0003: cliente público collector (30 días, rotación y retry_grace_period_seconds=10) ---
  assert {
    condition = (
      aws_cognito_user_pool_client.collector.name == "collector" &&
      aws_cognito_user_pool_client.collector.generate_secret == false &&
      aws_cognito_user_pool_client.collector.allowed_oauth_flows_user_pool_client == true &&
      toset(aws_cognito_user_pool_client.collector.allowed_oauth_flows) == toset(["code"]) &&
      toset(aws_cognito_user_pool_client.collector.allowed_oauth_scopes) == toset(["openid"]) &&
      toset(aws_cognito_user_pool_client.collector.supported_identity_providers) == toset(["COGNITO"]) &&
      toset(aws_cognito_user_pool_client.collector.callback_urls) == toset(["http://localhost"]) &&
      aws_cognito_user_pool_client.collector.access_token_validity == 60 &&
      aws_cognito_user_pool_client.collector.id_token_validity == 60 &&
      aws_cognito_user_pool_client.collector.refresh_token_validity == 30 &&
      aws_cognito_user_pool_client.collector.token_validity_units[0].access_token == "minutes" &&
      aws_cognito_user_pool_client.collector.token_validity_units[0].id_token == "minutes" &&
      aws_cognito_user_pool_client.collector.token_validity_units[0].refresh_token == "days" &&
      aws_cognito_user_pool_client.collector.refresh_token_rotation[0].feature == "ENABLED" &&
      aws_cognito_user_pool_client.collector.refresh_token_rotation[0].retry_grace_period_seconds == 10 &&
      aws_cognito_user_pool_client.collector.prevent_user_existence_errors == "ENABLED" &&
      aws_cognito_user_pool_client.collector.enable_token_revocation == true &&
      toset(aws_cognito_user_pool_client.collector.explicit_auth_flows) == toset(["ALLOW_REFRESH_TOKEN_AUTH"])
    )
    error_message = "El cliente collector debe ser público, callback http://localhost, refresh 30 días, rotación ENABLED y retry_grace_period_seconds = 10."
  }

  # --- Requisito 4.2 y D11: usuario propietario por correo de Parameter Store, sin contraseña en Terraform ---
  assert {
    condition = (
      aws_cognito_user.owner.username == "owner@example.invalid" &&
      toset(aws_cognito_user.owner.desired_delivery_mediums) == toset(["EMAIL"]) &&
      aws_cognito_user.owner.attributes["email"] == "owner@example.invalid" &&
      aws_cognito_user.owner.attributes["email_verified"] == "true" &&
      aws_cognito_user.owner.password == null &&
      aws_cognito_user.owner.temporary_password == null
    )
    error_message = "El usuario propietario debe usar el correo de Parameter Store, entrega EMAIL y ninguna contraseña en Terraform."
  }

  # --- Requisito 8.2: no sobreescribe default_tags ---
  assert {
    condition = (
      try(aws_cognito_user_pool.main.tags["Environment"], "prod") == "prod" &&
      try(aws_cognito_user_pool.main.tags["Project"], "monitorglucosa") == "monitorglucosa" &&
      try(aws_cognito_user_pool.main.tags["Owner"], "ldordellygithub") == "ldordellygithub"
    )
    error_message = "aws_cognito_user_pool.main no debe anular las default_tags obligatorias."
  }
}

run "rechaza_site_domain_con_esquema_o_ruta" {
  command = plan

  module {
    source = "./modules/identity"
  }

  variables {
    project               = "monitorglucosa"
    owner_email_parameter = "/monitorglucosa/prod/owner-email"
    site_domain           = "https://d111111abcdef8.cloudfront.net/path"
  }

  expect_failures = [
    var.site_domain,
  ]
}
