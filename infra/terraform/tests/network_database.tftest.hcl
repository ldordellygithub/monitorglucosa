# Pruebas de plan con proveedores simulados para los módulos `network` y `database`
# (Requisitos 5.1, 5.2, 5.5, 8.2; ADR 0002, ADR 0004, ADR 0007, ADR 0011).

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
      arn        = "arn:aws:sts::123456789012:assumed-role/monitorglucosa-deploy/test"
      user_id    = "AROAEXAMPLE:test"
    }
  }
}

run "raiz_conecta_network_y_database_sin_errores" {
  command = plan

  assert {
    condition     = module.database.writer_instance_id == "monitorglucosa-aurora-writer" && length(module.network.private_subnet_ids) == 2
    error_message = "La raíz debe instanciar module.database conectado a las 2 subredes privadas de module.network."
  }

  assert {
    condition     = module.database.database_name == "monitorglucosa" && module.database.cluster_port == 5432
    error_message = "La base de datos debe llamarse monitorglucosa en el puerto 5432."
  }
}

run "modulo_network_crea_vpc_privada_sin_nat_ni_igw_con_endpoint_s3_y_sgs" {
  command = plan

  module {
    source = "./modules/network"
  }

  variables {
    account_id = "123456789012"
    region     = "us-east-1"
    project    = "monitorglucosa"
  }

  # --- Requisito 5.1: VPC 10.20.0.0/16 en us-east-1a/1b, DNS activo, sin NAT ni IGW ---
  assert {
    condition = (
      aws_vpc.main.cidr_block == "10.20.0.0/16" &&
      aws_vpc.main.enable_dns_support == true &&
      aws_vpc.main.enable_dns_hostnames == true
    )
    error_message = "La VPC debe usar 10.20.0.0/16 con DNS support y hostnames activados."
  }

  assert {
    condition = (
      length(aws_subnet.private) == 2 &&
      toset(keys(aws_subnet.private)) == toset(["us-east-1a", "us-east-1b"]) &&
      alltrue([for s in values(aws_subnet.private) : s.map_public_ip_on_launch == false])
    )
    error_message = "Deben existir exactamente 2 subredes privadas en us-east-1a y us-east-1b sin IP pública."
  }

  assert {
    condition = (
      !can(regex("aws_nat_gateway|aws_internet_gateway|aws_eip|aws_route\\b|0\\.0\\.0\\.0/0|::/0", file("${path.module}/main.tf"))) &&
      length(aws_route_table_association.private) == 2 &&
      length(aws_default_security_group.default.ingress) == 0 &&
      length(aws_default_security_group.default.egress) == 0 &&
      !can(regex("egress_rule\"\\s+\"aurora_", file("${path.module}/main.tf")))
    )
    error_message = "El módulo network no debe crear NAT/IGW/EIP/rutas abiertas ni 0.0.0.0/0, debe bloquear el SG por defecto y no abrir egress en Aurora."
  }

  assert {
    condition = (
      aws_vpc_endpoint.s3.service_name == "com.amazonaws.us-east-1.s3" &&
      aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway" &&
      length(jsondecode(aws_vpc_endpoint.s3.policy).Statement) == 1 &&
      jsondecode(aws_vpc_endpoint.s3.policy).Statement[0].Condition.StringEquals["aws:PrincipalAccount"] == "123456789012" &&
      jsondecode(aws_vpc_endpoint.s3.policy).Statement[0].Condition.StringEquals["aws:ResourceAccount"] == "123456789012" &&
      jsondecode(aws_vpc_endpoint.s3.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "true"
    )
    error_message = "El endpoint de S3 debe ser Gateway en us-east-1 y exigir PrincipalAccount, ResourceAccount y SecureTransport."
  }

  # --- Requisito 5.5: grupos de seguridad estrictos (solo TCP 5432 api/migrator → aurora) ---
  assert {
    condition = (
      aws_security_group.api.name == "monitorglucosa-api" &&
      aws_security_group.migrator.name == "monitorglucosa-migrator" &&
      aws_security_group.aurora.name == "monitorglucosa-aurora"
    )
    error_message = "Los tres grupos de seguridad deben llamarse monitorglucosa-api, monitorglucosa-migrator y monitorglucosa-aurora."
  }

  assert {
    condition = (
      aws_vpc_security_group_egress_rule.api_to_aurora.ip_protocol == "tcp" &&
      aws_vpc_security_group_egress_rule.api_to_aurora.from_port == 5432 &&
      aws_vpc_security_group_egress_rule.api_to_aurora.to_port == 5432 &&
      aws_vpc_security_group_egress_rule.api_to_aurora.cidr_ipv4 == null &&
      aws_vpc_security_group_egress_rule.migrator_to_aurora.ip_protocol == "tcp" &&
      aws_vpc_security_group_egress_rule.migrator_to_aurora.from_port == 5432 &&
      aws_vpc_security_group_egress_rule.migrator_to_aurora.to_port == 5432 &&
      aws_vpc_security_group_egress_rule.migrator_to_aurora.cidr_ipv4 == null &&
      aws_vpc_security_group_ingress_rule.aurora_from_api.ip_protocol == "tcp" &&
      aws_vpc_security_group_ingress_rule.aurora_from_api.from_port == 5432 &&
      aws_vpc_security_group_ingress_rule.aurora_from_api.to_port == 5432 &&
      aws_vpc_security_group_ingress_rule.aurora_from_api.cidr_ipv4 == null &&
      aws_vpc_security_group_ingress_rule.aurora_from_migrator.ip_protocol == "tcp" &&
      aws_vpc_security_group_ingress_rule.aurora_from_migrator.from_port == 5432 &&
      aws_vpc_security_group_ingress_rule.aurora_from_migrator.to_port == 5432 &&
      aws_vpc_security_group_ingress_rule.aurora_from_migrator.cidr_ipv4 == null
    )
    error_message = "Todas las reglas SG deben ser TCP 5432 por referencia de grupo de seguridad, sin ningún CIDR abierto."
  }

  # --- Requisito 8.2: ningún recurso de network sobreescribe default_tags ---
  assert {
    condition = alltrue([
      for res_tags in concat(
        [
          aws_vpc.main.tags,
          aws_default_security_group.default.tags,
          aws_route_table.private.tags,
          aws_vpc_endpoint.s3.tags,
          aws_security_group.api.tags,
          aws_security_group.migrator.tags,
          aws_security_group.aurora.tags,
        ],
        [for s in values(aws_subnet.private) : s.tags],
        ) : (
        try(res_tags["Environment"], "prod") == "prod" &&
        try(res_tags["Project"], "monitorglucosa") == "monitorglucosa" &&
        try(res_tags["Owner"], "ldordellygithub") == "ldordellygithub"
      )
    ])
    error_message = "Ningún recurso de network puede anular Environment, Project u Owner heredados de default_tags."
  }
}

run "modulo_database_crea_aurora_serverless_v2_escala_a_cero_tls_iam_y_data_api" {
  command = plan

  module {
    source = "./modules/database"
  }

  variables {
    project                  = "monitorglucosa"
    private_subnet_ids       = ["subnet-11111111", "subnet-22222222"]
    aurora_security_group_id = "sg-12345678"
  }

  # --- Requisito 5.2: Aurora Serverless v2 0–2 ACU, pausa 300 s, cifrado, PITR 7 d, protección borrado, secreto RDS ---
  assert {
    condition = (
      aws_rds_cluster.aurora.cluster_identifier == "monitorglucosa-aurora" &&
      aws_rds_cluster.aurora.engine == "aurora-postgresql" &&
      aws_rds_cluster.aurora.engine_mode == "provisioned" &&
      aws_rds_cluster.aurora.engine_version == "16.6" &&
      aws_rds_cluster.aurora.database_name == "monitorglucosa" &&
      aws_rds_cluster.aurora.manage_master_user_password == true &&
      aws_rds_cluster.aurora.master_password == null &&
      aws_rds_cluster.aurora.storage_encrypted == true &&
      aws_rds_cluster.aurora.iam_database_authentication_enabled == true &&
      aws_rds_cluster.aurora.enable_http_endpoint == true &&
      aws_rds_cluster.aurora.backup_retention_period == 7 &&
      aws_rds_cluster.aurora.deletion_protection == true &&
      aws_rds_cluster.aurora.skip_final_snapshot == false &&
      aws_rds_cluster.aurora.copy_tags_to_snapshot == true &&
      length(aws_rds_cluster.aurora.enabled_cloudwatch_logs_exports) == 0
    )
    error_message = "El clúster Aurora debe cumplir todos los parámetros de 5.2, ADR 0002, ADR 0007 y NFR-5."
  }

  assert {
    condition = (
      aws_rds_cluster.aurora.serverlessv2_scaling_configuration[0].min_capacity == 0 &&
      aws_rds_cluster.aurora.serverlessv2_scaling_configuration[0].max_capacity == 2 &&
      aws_rds_cluster.aurora.serverlessv2_scaling_configuration[0].seconds_until_auto_pause == 300
    )
    error_message = "Aurora Serverless v2 debe escalar de 0 a 2 ACU con pausa automática tras 300 s."
  }

  assert {
    condition = (
      aws_rds_cluster_instance.writer.instance_class == "db.serverless" &&
      aws_rds_cluster_instance.writer.publicly_accessible == false &&
      aws_rds_cluster_instance.writer.performance_insights_enabled == false &&
      aws_rds_cluster_instance.writer.monitoring_interval == 0 &&
      aws_rds_cluster_instance.writer.auto_minor_version_upgrade == false
    )
    error_message = "La instancia writer debe ser db.serverless privada, sin Performance Insights ni Enhanced Monitoring."
  }

  # --- Requisito 5.5: TLS forzado (rds.force_ssl = 1), clave aws/rds gestionada y SG exclusivo ---
  assert {
    condition = (
      aws_rds_cluster_parameter_group.aurora.family == "aurora-postgresql16" &&
      aws_rds_cluster.aurora.db_cluster_parameter_group_name == "monitorglucosa-aurora-pg16" &&
      !can(regex("kms_key_id\\s*=", file("${path.module}/main.tf"))) &&
      length([
        for p in aws_rds_cluster_parameter_group.aurora.parameter : p
        if p.name == "rds.force_ssl" && p.value == "1"
      ]) == 1 &&
      toset(aws_rds_cluster.aurora.vpc_security_group_ids) == toset(["sg-12345678"])
    )
    error_message = "Aurora debe adjuntar monitorglucosa-aurora-pg16 (rds.force_ssl = 1), usar clave KMS aws/rds y solo el SG de Aurora."
  }

  # --- Requisito 8.2: ningún recurso de database sobreescribe default_tags ---
  assert {
    condition = alltrue([
      for res_tags in [
        aws_db_subnet_group.aurora.tags,
        aws_rds_cluster_parameter_group.aurora.tags,
        aws_rds_cluster.aurora.tags,
        aws_rds_cluster_instance.writer.tags,
        ] : (
        try(res_tags["Environment"], "prod") == "prod" &&
        try(res_tags["Project"], "monitorglucosa") == "monitorglucosa" &&
        try(res_tags["Owner"], "ldordellygithub") == "ldordellygithub"
      )
    ])
    error_message = "Ningún recurso de database puede anular Environment, Project u Owner heredados de default_tags."
  }
}

run "rechaza_version_aurora_inferior_a_16_4" {
  command = plan

  module {
    source = "./modules/database"
  }

  variables {
    project                  = "monitorglucosa"
    private_subnet_ids       = ["subnet-11111111", "subnet-22222222"]
    aurora_security_group_id = "sg-12345678"
    engine_version           = "16.3"
  }

  expect_failures = [
    var.engine_version,
  ]
}

run "rechaza_usuario_maestro_por_defecto" {
  command = plan

  module {
    source = "./modules/database"
  }

  variables {
    project                  = "monitorglucosa"
    private_subnet_ids       = ["subnet-11111111", "subnet-22222222"]
    aurora_security_group_id = "sg-12345678"
    master_username          = "postgres"
  }

  expect_failures = [
    var.master_username,
  ]
}

run "rechaza_red_con_una_sola_zona" {
  command = plan

  module {
    source = "./modules/network"
  }

  variables {
    account_id = "123456789012"
    region     = "us-east-1"
    project    = "monitorglucosa"
    private_subnets = {
      "us-east-1a" = "10.20.1.0/24"
    }
  }

  expect_failures = [
    var.private_subnets,
  ]
}
