output "tfstate_bucket_name" {
  description = "Nombre del bucket S3 de estado remoto de Terraform."
  value       = aws_s3_bucket.tfstate.bucket
  sensitive   = true
}

output "tfstate_bucket_arn" {
  description = "ARN del bucket S3 de estado remoto de Terraform."
  value       = aws_s3_bucket.tfstate.arn
  sensitive   = true
}

output "oidc_provider_arn" {
  description = "ARN del proveedor OIDC de GitHub Actions."
  value       = aws_iam_openid_connect_provider.github.arn
  sensitive   = true
}

output "deploy_role_arn" {
  description = "ARN del rol IAM monitorglucosa-deploy."
  value       = aws_iam_role.deploy.arn
  sensitive   = true
}

output "deploy_role_name" {
  description = "Nombre del rol IAM monitorglucosa-deploy."
  value       = aws_iam_role.deploy.name
}

output "workload_boundary_arn" {
  description = "ARN del permissions boundary monitorglucosa-workload-boundary."
  value       = aws_iam_policy.workload_boundary.arn
  sensitive   = true
}

output "ecr_repository_url" {
  description = "URL del repositorio ECR monitorglucosa-api."
  value       = aws_ecr_repository.api.repository_url
  sensitive   = true
}

output "ecr_repository_arn" {
  description = "ARN del repositorio ECR monitorglucosa-api."
  value       = aws_ecr_repository.api.arn
  sensitive   = true
}
