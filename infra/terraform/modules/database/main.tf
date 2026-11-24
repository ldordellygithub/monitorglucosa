# Aurora PostgreSQL 16 Serverless v2 (Requisitos 5.2, 5.5; D3, D13, ADR 0002, ADR 0004, ADR 0007, ADR 0011).
# Escala a cero (0-2 ACU, pausa 300 s), TLS forzado (rds.force_ssl = 1), autenticación IAM,
# RDS Data API para bootstrap.sql, backups de 7 días, protección contra borrado y
# contraseña maestra gestionada por RDS en Secrets Manager (nunca en código ni estado).

resource "aws_db_subnet_group" "aurora" {
  name        = "${var.project}-aurora-subnets"
  description = "Subredes privadas de us-east-1a y us-east-1b para Aurora PostgreSQL."
  subnet_ids  = var.private_subnet_ids

  tags = {
    Name = "${var.project}-aurora-subnets"
  }
}

resource "aws_rds_cluster_parameter_group" "aurora" {
  name        = "${var.project}-aurora-pg16"
  family      = "aurora-postgresql16"
  description = "Grupo de parámetros de Aurora PostgreSQL 16 con TLS obligatorio (Requisito 5.5)."

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }

  tags = {
    Name = "${var.project}-aurora-pg16"
  }
}

resource "aws_rds_cluster" "aurora" {
  # checkov:skip=CKV_AWS_324:Sin exportación de logs de PostgreSQL a CloudWatch por privacidad de datos clínicos y coste (design.md, STRIDE).
  # checkov:skip=CKV_AWS_327:Cifrado en reposo con clave KMS gestionada aws/rds (US$0/mes) según ADR 0011 y Requisito 5.2.
  # checkov:skip=CKV2_AWS_8:Backups automáticos de 7 días con PITR gestionados por Aurora (Requisito 5.2) sin plan AWS Backup extra.
  # checkov:skip=CKV2_AWS_27:Logs de consultas PostgreSQL desactivados explícitamente por privacidad de datos clínicos (design.md, STRIDE, NFR-5).
  cluster_identifier              = "${var.project}-aurora"
  engine                          = "aurora-postgresql"
  engine_mode                     = "provisioned"
  engine_version                  = var.engine_version
  database_name                   = var.database_name
  master_username                 = var.master_username
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.aurora.name
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.aurora.name
  vpc_security_group_ids          = [var.aurora_security_group_id]
  port                            = 5432

  storage_encrypted                   = true
  iam_database_authentication_enabled = true
  enable_http_endpoint                = true
  backup_retention_period             = 7
  copy_tags_to_snapshot               = true
  deletion_protection                 = true
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${var.project}-aurora-final"
  enabled_cloudwatch_logs_exports     = []

  serverlessv2_scaling_configuration {
    min_capacity             = 0
    max_capacity             = 2
    seconds_until_auto_pause = 300
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name = "${var.project}-aurora"
  }
}

resource "aws_rds_cluster_instance" "writer" {
  # checkov:skip=CKV_AWS_118:Enhanced Monitoring desactivado para mantener presupuesto < US$20/mes (design.md, ADR 0011).
  # checkov:skip=CKV_AWS_353:Performance Insights desactivado explícitamente según design.md y presupuesto < US$20/mes.
  # checkov:skip=CKV_AWS_226:auto_minor_version_upgrade desactivado para mantener versión menor fija y reproducible (design.md, D15).
  identifier                   = "${var.project}-aurora-writer"
  cluster_identifier           = aws_rds_cluster.aurora.id
  instance_class               = "db.serverless"
  engine                       = aws_rds_cluster.aurora.engine
  engine_version               = aws_rds_cluster.aurora.engine_version
  db_subnet_group_name         = aws_db_subnet_group.aurora.name
  publicly_accessible          = false
  performance_insights_enabled = false
  monitoring_interval          = 0
  auto_minor_version_upgrade   = false
  copy_tags_to_snapshot        = true

  tags = {
    Name = "${var.project}-aurora-writer"
  }
}
