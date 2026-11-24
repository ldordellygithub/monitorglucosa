variable "account_id" {
  description = "ID de la cuenta AWS exclusiva de monitorglucosa (12 dígitos)."
  type        = string

  validation {
    condition     = can(regex("^\\d{12}$", var.account_id))
    error_message = "account_id debe tener exactamente 12 dígitos."
  }
}

variable "region" {
  description = "Región exclusiva autorizada por ADR 0011 (us-east-1)."
  type        = string
  default     = "us-east-1"

  validation {
    condition     = var.region == "us-east-1"
    error_message = "Por ADR 0011 toda la infraestructura debe desplegarse exclusivamente en us-east-1."
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

variable "github_repository" {
  description = "Repositorio GitHub autorizado por OIDC (propietario/repositorio)."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository debe tener formato propietario/repositorio sin comodines."
  }
}

variable "github_environment" {
  description = "Entorno de GitHub Actions autorizado (por ejemplo, prod)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9_-]+$", var.github_environment))
    error_message = "github_environment debe contener solo minúsculas, dígitos, guiones o guiones bajos."
  }
}

variable "owner_email_parameter" {
  description = "Nombre del parámetro SecureString en SSM con el correo del propietario."
  type        = string

  validation {
    condition     = can(regex("^/monitorglucosa/[a-z0-9/_-]+$", var.owner_email_parameter))
    error_message = "owner_email_parameter debe iniciar con /monitorglucosa/ y no contener comodines."
  }
}

variable "aurora_cluster_arn" {
  description = "ARN exacto del clúster Aurora (opcional; por defecto usa el nombre determinista monitorglucosa-aurora)."
  type        = string
  default     = null

  validation {
    condition     = var.aurora_cluster_arn == null ? true : can(regex("^arn:aws:rds:us-east-1:\\d{12}:cluster:[a-z0-9-]+$", var.aurora_cluster_arn))
    error_message = "aurora_cluster_arn debe ser null o un ARN exacto de clúster RDS en us-east-1 sin comodines."
  }
}

variable "master_secret_arn" {
  description = "ARN exacto del secreto maestro gestionado por RDS (opcional; si es null se acota al prefijo rds!cluster-* de ADR 0007)."
  type        = string
  default     = null

  validation {
    condition     = var.master_secret_arn == null ? true : can(regex("^arn:aws:secretsmanager:us-east-1:\\d{12}:secret:rds!cluster-[A-Za-z0-9/_+=.@-]+$", var.master_secret_arn))
    error_message = "master_secret_arn debe ser null o un ARN exacto rds!cluster-... en us-east-1 sin comodines (ADR 0007)."
  }
}
