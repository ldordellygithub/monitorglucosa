output "http_api_id" {
  description = "ID de la HTTP API de API Gateway (usado por la alarma de 5xx en operations)."
  value       = aws_apigatewayv2_api.main.id
  sensitive   = true
}

output "api_endpoint" {
  description = "URL base HTTPS de la HTTP API (usada por scripts/deploy.py y smoke_test.py)."
  value       = aws_apigatewayv2_api.main.api_endpoint
  sensitive   = true
}

output "api_function_name" {
  description = "Nombre de la función Lambda api."
  value       = local.api_function_name
}

output "migrator_function_name" {
  description = "Nombre de la función Lambda migrator."
  value       = local.migrator_function_name
}

output "api_role_arn" {
  description = "ARN del rol IAM de la Lambda api."
  value       = aws_iam_role.api.arn
  sensitive   = true
}

output "migrator_role_arn" {
  description = "ARN del rol IAM de la Lambda migrator."
  value       = aws_iam_role.migrator.arn
  sensitive   = true
}
