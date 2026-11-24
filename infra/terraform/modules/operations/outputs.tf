output "alarms_topic_arn" {
  description = "ARN del tema SNS monitorglucosa-alarms."
  value       = aws_sns_topic.alarms.arn
  sensitive   = true
}

output "api_log_group_arn" {
  description = "ARN del grupo de logs de CloudWatch de la Lambda api."
  value       = aws_cloudwatch_log_group.api.arn
  sensitive   = true
}

output "migrator_log_group_arn" {
  description = "ARN del grupo de logs de CloudWatch de la Lambda migrator."
  value       = aws_cloudwatch_log_group.migrator.arn
  sensitive   = true
}

output "apigateway_log_group_arn" {
  description = "ARN del grupo de logs de CloudWatch para logs de acceso de HTTP API."
  value       = aws_cloudwatch_log_group.apigateway.arn
  sensitive   = true
}

output "budget_name" {
  description = "Nombre del presupuesto mensual en AWS Budgets."
  value       = aws_budgets_budget.monthly_cost.name
}
