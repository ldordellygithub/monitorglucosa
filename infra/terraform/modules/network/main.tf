# Red privada sin NAT Gateway ni Internet Gateway (Requisito 5.1, 5.5; ADR 0004, ADR 0011).
# Dos subredes privadas en us-east-1a y us-east-1b, endpoint gateway gratuito de S3 y
# tres grupos de seguridad con tráfico restringido exclusivamente a TCP 5432 hacia Aurora.

resource "aws_vpc" "main" {
  # checkov:skip=CKV2_AWS_11:VPC estrictamente privada sin IGW ni NAT; omitir VPC Flow Logs evita coste recurrente en presupuesto < US$20/mes (ADR 0004, ADR 0011).
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project}-vpc"
  }
}

# Bloquear completamente el grupo de seguridad por defecto de la VPC (defensa en profundidad).
resource "aws_default_security_group" "default" {
  vpc_id  = aws_vpc.main.id
  ingress = []
  egress  = []

  tags = {
    Name = "${var.project}-default-sg-locked"
  }
}

resource "aws_subnet" "private" {
  for_each = var.private_subnets

  vpc_id                  = aws_vpc.main.id
  cidr_block              = each.value
  availability_zone       = each.key
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.project}-private-${each.key}"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  # Sin salida a internet: no existe IGW ni NAT Gateway (Requisito 5.1, ADR 0004).
  tags = {
    Name = "${var.project}-private-rt"
  }
}

resource "aws_route_table_association" "private" {
  for_each = aws_subnet.private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}

# Endpoint gateway de S3 (US$0/mes), acotado a identidades de la propia cuenta AWS.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowAccountPrincipalsOnly"
        Effect    = "Allow"
        Principal = "*"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::${var.project}-*",
          "arn:aws:s3:::${var.project}-*/*",
        ]
        Condition = {
          StringEquals = {
            "aws:PrincipalAccount" = var.account_id
            "aws:ResourceAccount"  = var.account_id
          }
          Bool = {
            "aws:SecureTransport" = "true"
          }
        }
      }
    ]
  })

  tags = {
    Name = "${var.project}-s3-gateway-endpoint"
  }
}

# ---------------------------------------------------------------------------
# Grupos de seguridad (design.md · Red y grupos de seguridad, Requisito 5.5)
# ---------------------------------------------------------------------------

resource "aws_security_group" "api" {
  # checkov:skip=CKV2_AWS_5:Adjuntado a la Lambda monitorglucosa-api desde el módulo hermano module.api (tarea 18).
  name                   = "${var.project}-api"
  description            = "Lambda api: sin entrada; salida exclusivamente a TCP 5432 de Aurora."
  vpc_id                 = aws_vpc.main.id
  revoke_rules_on_delete = true

  tags = {
    Name = "${var.project}-api"
  }
}

resource "aws_security_group" "migrator" {
  # checkov:skip=CKV2_AWS_5:Adjuntado a la Lambda monitorglucosa-migrator desde el módulo hermano module.api (tarea 18).
  name                   = "${var.project}-migrator"
  description            = "Lambda migrator: sin entrada; salida exclusivamente a TCP 5432 de Aurora."
  vpc_id                 = aws_vpc.main.id
  revoke_rules_on_delete = true

  tags = {
    Name = "${var.project}-migrator"
  }
}

resource "aws_security_group" "aurora" {
  # checkov:skip=CKV2_AWS_5:Adjuntado al clúster Aurora desde el módulo hermano module.database (vpc_security_group_ids).
  name                   = "${var.project}-aurora"
  description            = "Aurora PostgreSQL: entrada TCP 5432 solo desde api y migrator; sin salida."
  vpc_id                 = aws_vpc.main.id
  revoke_rules_on_delete = true

  tags = {
    Name = "${var.project}-aurora"
  }
}

resource "aws_vpc_security_group_egress_rule" "api_to_aurora" {
  security_group_id            = aws_security_group.api.id
  description                  = "Permitir salida TCP 5432 desde Lambda api hacia Aurora."
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.aurora.id
}

resource "aws_vpc_security_group_egress_rule" "migrator_to_aurora" {
  security_group_id            = aws_security_group.migrator.id
  description                  = "Permitir salida TCP 5432 desde Lambda migrator hacia Aurora."
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.aurora.id
}

resource "aws_vpc_security_group_ingress_rule" "aurora_from_api" {
  security_group_id            = aws_security_group.aurora.id
  description                  = "Permitir entrada TCP 5432 hacia Aurora solo desde Lambda api."
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.api.id
}

resource "aws_vpc_security_group_ingress_rule" "aurora_from_migrator" {
  security_group_id            = aws_security_group.aurora.id
  description                  = "Permitir entrada TCP 5432 hacia Aurora solo desde Lambda migrator."
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.migrator.id
}
