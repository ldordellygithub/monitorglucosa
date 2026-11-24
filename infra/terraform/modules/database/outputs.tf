output "cluster_arn" {
  description = "ARN del clúster Aurora PostgreSQL Serverless v2."
  value       = aws_rds_cluster.aurora.arn
  sensitive   = true
}

output "cluster_id" {
  description = "Identificador del clúster Aurora."
  value       = aws_rds_cluster.aurora.id
}

output "cluster_resource_id" {
  description = "ID de recurso de Aurora (db-...) usado para acotar rds-db:connect en IAM."
  value       = aws_rds_cluster.aurora.cluster_resource_id
  sensitive   = true
}

output "cluster_endpoint" {
  description = "Endpoint writer de Aurora PostgreSQL dentro de la VPC."
  value       = aws_rds_cluster.aurora.endpoint
  sensitive   = true
}

output "cluster_port" {
  description = "Puerto TCP de Aurora PostgreSQL (5432)."
  value       = aws_rds_cluster.aurora.port
}

output "database_name" {
  description = "Nombre de la base de datos inicial en Aurora."
  value       = aws_rds_cluster.aurora.database_name
}

output "master_secret_arn" {
  description = "ARN del secreto maestro gestionado por RDS en Secrets Manager."
  value       = try(aws_rds_cluster.aurora.master_user_secret[0].secret_arn, "")
  sensitive   = true
}

output "writer_instance_id" {
  description = "Identificador de la instancia writer db.serverless (usado por la alarma de pausa en operaciones)."
  value       = aws_rds_cluster_instance.writer.identifier
}
