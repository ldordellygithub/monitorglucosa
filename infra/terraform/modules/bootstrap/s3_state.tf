# Bucket del estado remoto de Terraform (Requisito 8.1, D1, ADR 0008, ADR 0011).
# Versionado, cifrado SSE-S3 (US$0/mes), bloqueo total de acceso público,
# retención de versiones antiguas de 90 días y política que exige TLS.

locals {
  tfstate_bucket_name = "${var.project}-tfstate-${var.account_id}"
  tfstate_bucket_arn  = "arn:aws:s3:::${local.tfstate_bucket_name}"
}

resource "aws_s3_bucket" "tfstate" {
  # checkov:skip=CKV_AWS_18:El bucket de estado solo lo usa el propietario y OIDC; CloudTrail registra la actividad sin coste de un bucket extra de logs.
  # checkov:skip=CKV_AWS_144:Despliegue en región única us-east-1 según ADR 0011 y presupuesto < US$20/mes.
  # checkov:skip=CKV_AWS_145:Cifrado SSE-S3 (AES256) decidido en D1 y ADR 0011 para evitar US$1/mes por CMK.
  # checkov:skip=CKV2_AWS_62:No se requieren notificaciones de eventos S3 sobre el estado de Terraform.
  bucket = local.tfstate_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    bucket_key_enabled = false

    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    id     = "expire-noncurrent-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.tfstate]
}

resource "aws_s3_bucket_policy" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          local.tfstate_bucket_arn,
          "${local.tfstate_bucket_arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.tfstate]
}
