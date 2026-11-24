output "user_pool_id" {
  description = "ID del Cognito User Pool de monitorglucosa."
  value       = aws_cognito_user_pool.main.id
  sensitive   = true
}

output "user_pool_arn" {
  description = "ARN del Cognito User Pool."
  value       = aws_cognito_user_pool.main.arn
  sensitive   = true
}

output "user_pool_endpoint" {
  description = "Endpoint emisor (iss) del Cognito User Pool para el autorizador JWT de HTTP API."
  value       = "https://${aws_cognito_user_pool.main.endpoint}"
  sensitive   = true
}

output "domain_prefix" {
  description = "Prefijo del dominio alojado de Cognito."
  value       = aws_cognito_user_pool_domain.main.domain
}

output "web_client_id" {
  description = "ID del cliente público web en Cognito."
  value       = aws_cognito_user_pool_client.web.id
}

output "collector_client_id" {
  description = "ID del cliente público collector en Cognito."
  value       = aws_cognito_user_pool_client.collector.id
}
