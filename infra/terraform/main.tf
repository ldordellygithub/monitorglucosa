data "aws_caller_identity" "current" {}

module "bootstrap" {
  source = "./modules/bootstrap"

  account_id            = data.aws_caller_identity.current.account_id
  region                = "us-east-1"
  project               = "monitorglucosa"
  github_repository     = var.github_repository
  github_environment    = var.github_environment
  owner_email_parameter = var.owner_email_parameter
}

module "network" {
  source = "./modules/network"

  account_id = data.aws_caller_identity.current.account_id
  region     = "us-east-1"
  project    = "monitorglucosa"
}

module "database" {
  source = "./modules/database"

  project                  = "monitorglucosa"
  private_subnet_ids       = module.network.private_subnet_ids
  aurora_security_group_id = module.network.aurora_security_group_id
}

module "site" {
  source = "./modules/site"

  account_id = data.aws_caller_identity.current.account_id
  project    = "monitorglucosa"
}

module "identity" {
  source = "./modules/identity"

  project               = "monitorglucosa"
  owner_email_parameter = var.owner_email_parameter
  site_domain           = module.site.site_domain
}

module "api" {
  source = "./modules/api"

  account_id                  = data.aws_caller_identity.current.account_id
  region                      = "us-east-1"
  project                     = "monitorglucosa"
  workload_boundary_arn       = module.bootstrap.workload_boundary_arn
  ecr_repository_url          = module.bootstrap.ecr_repository_url
  api_image_digest            = var.api_image_digest
  migrator_image_digest       = var.migrator_image_digest
  private_subnet_ids          = module.network.private_subnet_ids
  api_security_group_id       = module.network.api_security_group_id
  migrator_security_group_id  = module.network.migrator_security_group_id
  database_host               = module.database.cluster_endpoint
  database_port               = module.database.cluster_port
  database_name               = module.database.database_name
  aurora_cluster_resource_id  = module.database.cluster_resource_id
  cognito_issuer              = module.identity.user_pool_endpoint
  cognito_web_client_id       = module.identity.web_client_id
  cognito_collector_client_id = module.identity.collector_client_id
  site_domain                 = module.site.site_domain
  # En tarea 19 se conecta a module.operations.apigateway_log_group_arn.
  access_log_group_arn = "arn:aws:logs:us-east-1:${data.aws_caller_identity.current.account_id}:log-group:/aws/apigateway/monitorglucosa"
}
