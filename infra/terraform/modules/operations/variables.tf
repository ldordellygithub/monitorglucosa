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

variable "owner_email_parameter" {
  description = "Nombre del parámetro SecureString en SSM Parameter Store con el correo del propietario (D11)."
  type        = string
  default     = "/monitorglucosa/prod/owner-email"

  validation {
    condition     = can(regex("^/monitorglucosa/[a-z0-9/_-]+$", var.owner_email_parameter))
    error_message = "owner_email_parameter debe iniciar con /monitorglucosa/."
  }
}

variable "api_function_name" {
  description = "Nombre de la función Lambda api vigilada por la alarma de errores."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,63}$", var.api_function_name))
    error_message = "api_function_name debe ser un nombre válido de función Lambda."
  }
}

variable "migrator_function_name" {
  description = "Nombre de la función Lambda migrator vigilada por la alarma de errores."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,63}$", var.migrator_function_name))
    error_message = "migrator_function_name debe ser un nombre válido de función Lambda."
  }
}

variable "http_api_id" {
  description = "ID de la HTTP API de API Gateway vigilada por la alarma de respuestas 5xx."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{6,20}$", var.http_api_id))
    error_message = "http_api_id debe ser un identificador alfanumérico válido de API Gateway."
  }
}

variable "aurora_writer_instance_id" {
  description = "Identificador de la instancia writer db.serverless de Aurora vigilada por la alarma de pausa (D14)."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,62}$", var.aurora_writer_instance_id))
    error_message = "aurora_writer_instance_id debe ser un identificador válido de instancia RDS."
  }
}

variable "monthly_budget_limit_usd" {
  description = "Presupuesto mensual total de la cuenta exclusiva en USD (Requisito 8.3, NFR-3)."
  type        = number
  default     = 20

  validation {
    condition     = var.monthly_budget_limit_usd > 0 && var.monthly_budget_limit_usd <= 100
    error_message = "monthly_budget_limit_usd debe ser un importe positivo razonable (por defecto 20 USD)."
  }
}

variable "log_retention_days" {
  description = "Días de retención de todos los grupos de logs de CloudWatch creados por esta spec (Requisito 8.5)."
  type        = number
  default     = 30

  validation {
    condition     = var.log_retention_days == 30
    error_message = "Requisito 8.5: la retención de logs debe fijarse en 30 días."
  }
}
