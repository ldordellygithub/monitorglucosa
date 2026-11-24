# Repositorio ECR de la imagen única API + migrator (Requisito 6.1, D5, ADR 0005).
# Etiquetas inmutables, escaneo al subir, política de ciclo de vida de 10 imágenes
# y acceso de Lambda limitado por sourceArn exclusivamente a api y migrator.

resource "aws_ecr_repository" "api" {
  # checkov:skip=CKV_AWS_136:Cifrado gestionado AES256 decidido en ADR 0011 para evitar US$1/mes por CMK.
  name                 = "${var.project}-api"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Conservar solo las últimas 10 imágenes en ECR (Requisito 6.1, D5)"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

resource "aws_ecr_repository_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaPullForProjectFunctionsOnly"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Condition = {
          ArnEquals = {
            "aws:sourceArn" = [
              "arn:aws:lambda:${var.region}:${var.account_id}:function:${var.project}-api",
              "arn:aws:lambda:${var.region}:${var.account_id}:function:${var.project}-migrator",
            ]
          }
          StringEquals = {
            "aws:SourceAccount" = var.account_id
          }
        }
      }
    ]
  })
}
