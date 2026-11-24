variable "api_image_digest" {
  description = "Digest inmutable (sha256:...) de la imagen de la Lambda api en ECR (null durante el bootstrap local inicial)."
  type        = string
  default     = null

  validation {
    condition     = var.api_image_digest == null ? true : can(regex("^sha256:[0-9a-f]{64}$", var.api_image_digest))
    error_message = "api_image_digest debe ser null o cumplir el formato sha256:<64 hex minúsculas>."
  }
}

variable "migrator_image_digest" {
  description = "Digest inmutable (sha256:...) de la imagen de la Lambda migrator en ECR (null durante el bootstrap local inicial)."
  type        = string
  default     = null

  validation {
    condition     = var.migrator_image_digest == null ? true : can(regex("^sha256:[0-9a-f]{64}$", var.migrator_image_digest))
    error_message = "migrator_image_digest debe ser null o cumplir el formato sha256:<64 hex minúsculas>."
  }
}

variable "owner_email_parameter" {
  description = "Nombre del parámetro SecureString en SSM Parameter Store con el correo del propietario (nunca el correo en claro)."
  type        = string
  default     = "/monitorglucosa/prod/owner-email"

  validation {
    condition     = can(regex("^/monitorglucosa/[a-z0-9/_-]+$", var.owner_email_parameter))
    error_message = "owner_email_parameter debe iniciar con /monitorglucosa/ y contener solo caracteres válidos."
  }
}

variable "github_repository" {
  description = "Repositorio GitHub autorizado por OIDC (formato propietario/repositorio)."
  type        = string
  default     = "ldordellygithub/monitorglucosa"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository debe tener formato propietario/repositorio."
  }
}

variable "github_environment" {
  description = "Entorno de GitHub Actions autorizado para asumir el rol de despliegue."
  type        = string
  default     = "prod"

  validation {
    condition     = can(regex("^[a-z0-9_-]+$", var.github_environment))
    error_message = "github_environment debe contener solo letras minúsculas, dígitos, guiones o guiones bajos."
  }
}
