# Identidad con Amazon Cognito Essentials (Requisitos 4.1, 4.2, 4.3, 4.4; D11, D12, ADR 0003).
# User Pool Essentials en us-east-1, MFA TOTP obligatorio sin SMS, sin registro propio,
# clientes públicos web (refresh 1 d) y collector (refresh 30 d con rotación + 10 s de gracia),
# dominio de prefijo derivado del ID aleatorio del User Pool (sin correlación con account_id)
# y usuario propietario desde Parameter Store.

locals {
  # Sufijo de 8 hex derivado del ID aleatorio generado por AWS para el User Pool:
  # globalmente único, determinista tras la creación y sin correlación con account_id (NFR-5).
  domain_prefix = "${var.project}-${substr(sha256(aws_cognito_user_pool.main.id), 0, 8)}"
}

data "aws_ssm_parameter" "owner_email" {
  name            = var.owner_email_parameter
  with_decryption = true
}

resource "aws_cognito_user_pool" "main" {
  name                = "${var.project}-users"
  user_pool_tier      = "ESSENTIALS"
  deletion_protection = "ACTIVE"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # MFA TOTP obligatorio; sin SMS (Requisito 4.1, ADR 0003).
  mfa_configuration = "ON"

  software_token_mfa_configuration {
    enabled = true
  }

  # Registro propio desactivado: solo alta administrativa (Requisitos 4.1 y 4.2).
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = local.domain_prefix
  user_pool_id = aws_cognito_user_pool.main.id
}

# Cliente público de la aplicación web (Requisito 4.3, D12):
# código + PKCE, sin secreto, refresh token de 1 día, callbacks en CloudFront.
resource "aws_cognito_user_pool_client" "web" {
  name         = "web"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = ["https://${var.site_domain}/auth/callback"]
  logout_urls   = ["https://${var.site_domain}/"]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 1

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
  explicit_auth_flows           = ["ALLOW_REFRESH_TOKEN_AUTH"]
}

# Cliente público del colector BLE local (Requisito 4.4, ADR 0003, D12, T-7):
# código + PKCE (S256), sin secreto, callback http://localhost, refresh 30 días,
# rotación activada y retry_grace_period_seconds fijado explícitamente en 10 s.
resource "aws_cognito_user_pool_client" "collector" {
  name         = "collector"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = ["http://localhost"]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  refresh_token_rotation {
    feature                    = "ENABLED"
    retry_grace_period_seconds = 10
  }

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
  explicit_auth_flows           = ["ALLOW_REFRESH_TOKEN_AUTH"]
}

# Usuario propietario dado de alta solo por vía administrativa (Requisito 4.2, D11):
# correo leído de SSM Parameter Store, entrega por correo (sin SMS) y sin contraseña en Terraform.
resource "aws_cognito_user" "owner" {
  user_pool_id             = aws_cognito_user_pool.main.id
  username                 = data.aws_ssm_parameter.owner_email.value
  desired_delivery_mediums = ["EMAIL"]

  attributes = {
    email          = data.aws_ssm_parameter.owner_email.value
    email_verified = "true"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [desired_delivery_mediums]
  }
}
