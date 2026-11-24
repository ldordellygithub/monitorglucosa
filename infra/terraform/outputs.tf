output "tfstate_bucket_name" {
  description = "Nombre del bucket S3 del estado remoto de Terraform."
  value       = module.bootstrap.tfstate_bucket_name
  sensitive   = true
}

output "deploy_role_arn" {
  description = "ARN del rol IAM de despliegue asumido por GitHub Actions vía OIDC."
  value       = module.bootstrap.deploy_role_arn
  sensitive   = true
}

output "workload_boundary_arn" {
  description = "ARN del permissions boundary obligatorio para los roles de carga de trabajo."
  value       = module.bootstrap.workload_boundary_arn
  sensitive   = true
}

output "ecr_repository_url" {
  description = "URL del repositorio ECR para la imagen única de la API y del migrator."
  value       = module.bootstrap.ecr_repository_url
  sensitive   = true
}

output "ecr_repository_arn" {
  description = "ARN del repositorio ECR de la API."
  value       = module.bootstrap.ecr_repository_arn
  sensitive   = true
}

output "cluster_arn" {
  description = "ARN del clúster Aurora PostgreSQL Serverless v2 (usado por scripts/deploy.py y db_bootstrap.py)."
  value       = module.database.cluster_arn
  sensitive   = true
}

output "master_secret_arn" {
  description = "ARN del secreto maestro gestionado por RDS en Secrets Manager (usado por RDS Data API)."
  value       = module.database.master_secret_arn
  sensitive   = true
}

output "cluster_endpoint" {
  description = "Endpoint writer de Aurora PostgreSQL dentro de la VPC privada."
  value       = module.database.cluster_endpoint
  sensitive   = true
}

output "cluster_resource_id" {
  description = "ID de recurso de Aurora (db-...) para acotar rds-db:connect."
  value       = module.database.cluster_resource_id
  sensitive   = true
}

output "api_image_digest" {
  description = "Digest sha256 actualmente desplegado en la Lambda api (vacío antes del primer despliegue para que deploy.py detecte primer_despliegue=si)."
  value       = var.api_image_digest != null ? var.api_image_digest : ""
}

output "migrator_image_digest" {
  description = "Digest sha256 actualmente desplegado en la Lambda migrator (vacío antes del primer despliegue)."
  value       = var.migrator_image_digest != null ? var.migrator_image_digest : ""
}
