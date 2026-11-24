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

output "api_image_digest" {
  description = "Digest sha256 actualmente desplegado en la Lambda api (vacío antes del primer despliegue para que deploy.py detecte primer_despliegue=si)."
  value       = var.api_image_digest != null ? var.api_image_digest : ""
}

output "migrator_image_digest" {
  description = "Digest sha256 actualmente desplegado en la Lambda migrator (vacío antes del primer despliegue)."
  value       = var.migrator_image_digest != null ? var.migrator_image_digest : ""
}
