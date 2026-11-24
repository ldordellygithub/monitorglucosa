# Sitio web estático provisional en S3 privado servido únicamente por CloudFront con OAC,
# HTTPS obligatorio y política de cabeceras HSTS + CSP (Requisitos 6.4, 8.2; D13).

locals {
  site_bucket_name = "${var.project}-site-${var.account_id}"
  s3_origin_id     = "${var.project}-site-s3"

  # Política gestionada AWS CachingOptimized (sin políticas de caché propias adicionales).
  cloudfront_caching_optimized_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"

  # CSP estricta de D13 (sin inline styles ni scripts).
  content_security_policy = "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"

  # Página provisional sin estilos ni scripts en línea para cumplir la CSP estricta.
  placeholder_html = <<-HTML
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>monitorglucosa</title>
    </head>
    <body>
      <main>
        <h1>monitorglucosa</h1>
        <p>monitorglucosa · en construcción</p>
      </main>
    </body>
    </html>
  HTML
}

# ---------------------------------------------------------------------------
# Bucket S3 privado del sitio (SSE-S3, sin acceso público, solo CloudFront OAC)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "site" {
  # checkov:skip=CKV_AWS_18:Sin bucket de logs de acceso S3 en esta spec por simplicidad y coste (NFR-3); se revisa en la spec de la web.
  # checkov:skip=CKV_AWS_144:Región única autorizada us-east-1 (ADR 0011); sin replicación cross-region.
  # checkov:skip=CKV_AWS_145:Cifrado SSE-S3 (AES256) definido por diseño (design.md); sin CMK KMS propia (US$1/mes, NFR-3).
  # checkov:skip=CKV2_AWS_62:Sin notificaciones de eventos S3 requeridas para archivos estáticos.
  bucket = local.site_bucket_name
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    id     = "expire-noncurrent-and-abort-multipart"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.site]
}

resource "aws_s3_object" "index" {
  bucket        = aws_s3_bucket.site.id
  key           = "index.html"
  content       = local.placeholder_html
  content_type  = "text/html; charset=utf-8"
  cache_control = "no-cache"
  etag          = md5(local.placeholder_html)

  depends_on = [
    aws_s3_bucket_ownership_controls.site,
    aws_s3_bucket_public_access_block.site,
    aws_s3_bucket_server_side_encryption_configuration.site,
  ]
}

# ---------------------------------------------------------------------------
# CloudFront OAC, cabeceras de seguridad (D13) y distribución HTTPS
# ---------------------------------------------------------------------------

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.project}-site-oac"
  description                       = "Origin Access Control SigV4 para el bucket privado del sitio de monitorglucosa."
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_response_headers_policy" "site" {
  # checkov:skip=CKV_AWS_259:HSTS configurado con max-age=63072000, includeSubDomains y override=true según D13; preload no aplica al dominio *.cloudfront.net.
  name    = "${var.project}-site-security-headers"
  comment = "Cabeceras HSTS, CSP, nosniff, Referrer-Policy y X-Frame-Options (Requisito 6.4, D13)."

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 63072000
      include_subdomains         = true
      preload                    = false
      override                   = true
    }

    content_security_policy {
      content_security_policy = local.content_security_policy
      override                = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    referrer_policy {
      referrer_policy = "no-referrer"
      override        = true
    }
  }
}

resource "aws_cloudfront_distribution" "site" {
  # checkov:skip=CKV_AWS_68:Sin AWS WAF en esta spec por presupuesto <= US$20/mes (design.md, NFR-3); contenido estático sin datos de salud.
  # checkov:skip=CKV_AWS_86:Sin bucket de logs de acceso CloudFront en esta spec por coste y privacidad (sin registrar IPs).
  # checkov:skip=CKV_AWS_174:Dominio por defecto *.cloudfront.net sin dominio propio ni ACM (Out of Scope); AWS gestiona TLS del certificado por defecto.
  # checkov:skip=CKV_AWS_310:Origen único S3 en us-east-1 para aplicación personal de un usuario (sin failover multi-origen).
  # checkov:skip=CKV_AWS_374:Sin geo-restricción requerida (usuario propietario puede viajar).
  # checkov:skip=CKV2_AWS_42:Dominio propio y certificado ACM fuera de alcance (requirements.md Out of Scope); usa *.cloudfront.net con redirect-to-https.
  # checkov:skip=CKV2_AWS_47:Sin AWS WAF en esta spec por presupuesto <= US$20/mes (design.md, NFR-3).
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Sitio estático provisional de monitorglucosa (HTTPS + OAC)."
  default_root_object = "index.html"
  http_version        = "http2and3"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = local.s3_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id           = local.s3_origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = local.cloudfront_caching_optimized_policy_id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.site.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Política del bucket S3: solo permite lectura a esta distribución CloudFront vía OAC
# y deniega explícitamente cualquier transporte sin TLS (Requisito 6.4).
resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOacReadOnly"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.site.arn}/*"]
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.site.arn
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.site.arn,
          "${aws_s3_bucket.site.arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.site]
}
