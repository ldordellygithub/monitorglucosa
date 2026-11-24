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
