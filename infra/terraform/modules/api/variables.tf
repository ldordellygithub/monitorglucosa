variable "account_id" {
  description = "ID de la cuenta AWS exclusiva de monitorglucosa (12 dígitos)."
  type        = string

  validation {
    condition     = can(regex("^\\d{12}$", var.account_id))
    error_message = "account_id debe tener exactamente 12 dígitos."
  }
}

variable "region" {
  description = "Región AWS autorizada (us-east-1, ADR 0011)."
  type        = string
  default     = "us-east-1"

  validation {
    condition     = var.region == "us-east-1"
    error_message = "Solo se permite desplegar en us-east-1 (ADR 0011)."
  }
}

variable "project" {
  description = "Prefijo de nombres de recursos del proyecto."
  type        = string
  default     = "monitorglucosa"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,31}$", var.project))
    error_message = "project debe contener solo minúsculas, dígitos y guiones."
  }
}

variable "workload_boundary_arn" {
  description = "ARN del permissions boundary obligatorio para los roles de Lambda (ADR 0008)."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::\\d{12}:policy/[a-z0-9_-]+$", var.workload_boundary_arn))
    error_message = "workload_boundary_arn debe ser un ARN válido de política IAM."
  }
}

variable "ecr_repository_url" {
  description = "URL del repositorio ECR que contiene la imagen única de api y migrator."
  type        = string

  validation {
    condition     = can(regex("^\\d{12}\\.dkr\\.ecr\\.us-east-1\\.amazonaws\\.com/[a-z0-9][a-z0-9._/-]*$", var.ecr_repository_url))
    error_message = "ecr_repository_url debe ser una URL válida de ECR en us-east-1."
  }
}

variable "api_image_digest" {
  description = "Digest inmutable (sha256:...) de la imagen para la Lambda api (null antes del primer despliegue)."
  type        = string
  default     = null

  validation {
    condition     = var.api_image_digest == null ? true : can(regex("^sha256:[0-9a-f]{64}$", var.api_image_digest))
    error_message = "api_image_digest debe ser null o cumplir sha256:<64 hex minúsculas>."
  }
}

variable "migrator_image_digest" {
  description = "Digest inmutable (sha256:...) de la imagen para la Lambda migrator (null antes del primer despliegue)."
  type        = string
  default     = null

  validation {
    condition     = var.migrator_image_digest == null ? true : can(regex("^sha256:[0-9a-f]{64}$", var.migrator_image_digest))
    error_message = "migrator_image_digest debe ser null o cumplir sha256:<64 hex minúsculas>."
  }
}

variable "private_subnet_ids" {
  description = "IDs de las subredes privadas de la VPC donde corren las Lambdas."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Se requieren al menos dos subredes privadas en distintas AZ."
  }
}

variable "api_security_group_id" {
  description = "ID del grupo de seguridad de la Lambda api."
  type        = string
}

variable "migrator_security_group_id" {
  description = "ID del grupo de seguridad de la Lambda migrator."
  type        = string
}

variable "database_host" {
  description = "Endpoint writer del clúster Aurora PostgreSQL dentro de la VPC."
  type        = string
}

variable "database_port" {
  description = "Puerto TCP de Aurora PostgreSQL."
  type        = number
  default     = 5432

  validation {
    condition     = var.database_port == 5432
    error_message = "database_port debe ser 5432."
  }
}

variable "database_name" {
  description = "Nombre de la base de datos en Aurora."
  type        = string
  default     = "monitorglucosa"
}

variable "aurora_cluster_resource_id" {
  description = "ID de recurso de Aurora (cluster-...) para acotar rds-db:connect."
  type        = string

  validation {
    condition     = can(regex("^cluster-[A-Z0-9]+$", var.aurora_cluster_resource_id))
    error_message = "aurora_cluster_resource_id debe cumplir el formato cluster-<alfanumérico mayúsculas> sin comodines."
  }
}

variable "cognito_issuer" {
  description = "URL emisora (iss) del Cognito User Pool para el autorizador JWT."
  type        = string

  validation {
    condition     = can(regex("^https://cognito-idp\\.us-east-1\\.amazonaws\\.com/us-east-1_[A-Za-z0-9]+$", var.cognito_issuer))
    error_message = "cognito_issuer debe ser una URL HTTPS válida de Cognito User Pool en us-east-1."
  }
}

variable "cognito_web_client_id" {
  description = "Client ID del cliente público web de Cognito."
  type        = string
}

variable "cognito_collector_client_id" {
  description = "Client ID del cliente público collector de Cognito."
  type        = string
}

variable "site_domain" {
  description = "Dominio HTTPS de CloudFront autorizado en CORS de API Gateway (Requisito 6.5)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+\\.[a-z]{2,}$", var.site_domain))
    error_message = "site_domain debe ser un dominio válido sin esquema ni rutas."
  }
}

variable "access_log_group_arn" {
  description = "ARN del grupo de logs de CloudWatch donde API Gateway escribe los logs de acceso en JSON."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:logs:us-east-1:\\d{12}:log-group:/aws/apigateway/[a-z0-9_-]+$", var.access_log_group_arn))
    error_message = "access_log_group_arn debe ser el ARN de un grupo /aws/apigateway/... en us-east-1."
  }
}
