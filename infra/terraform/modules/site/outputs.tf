output "site_domain" {
  description = "Dominio HTTPS de la distribución CloudFront del sitio (usado en CORS de API Gateway y callbacks de Cognito)."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "distribution_id" {
  description = "ID de la distribución CloudFront del sitio."
  value       = aws_cloudfront_distribution.site.id
  sensitive   = true
}

output "distribution_arn" {
  description = "ARN de la distribución CloudFront del sitio."
  value       = aws_cloudfront_distribution.site.arn
  sensitive   = true
}

output "bucket_name" {
  description = "Nombre del bucket S3 privado del sitio."
  value       = aws_s3_bucket.site.bucket
  sensitive   = true
}

output "bucket_arn" {
  description = "ARN del bucket S3 privado del sitio."
  value       = aws_s3_bucket.site.arn
  sensitive   = true
}
