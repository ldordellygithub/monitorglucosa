output "vpc_id" {
  description = "ID de la VPC privada de monitorglucosa."
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "IDs ordenados de las subredes privadas en us-east-1a y us-east-1b."
  value       = [for az in sort(keys(aws_subnet.private)) : aws_subnet.private[az].id]
}

output "private_route_table_id" {
  description = "ID de la tabla de rutas privada (sin IGW ni NAT)."
  value       = aws_route_table.private.id
}

output "s3_vpc_endpoint_id" {
  description = "ID del endpoint gateway de VPC para Amazon S3."
  value       = aws_vpc_endpoint.s3.id
}

output "api_security_group_id" {
  description = "ID del grupo de seguridad de la Lambda api."
  value       = aws_security_group.api.id
}

output "migrator_security_group_id" {
  description = "ID del grupo de seguridad de la Lambda migrator."
  value       = aws_security_group.migrator.id
}

output "aurora_security_group_id" {
  description = "ID del grupo de seguridad del clúster Aurora PostgreSQL."
  value       = aws_security_group.aurora.id
}
