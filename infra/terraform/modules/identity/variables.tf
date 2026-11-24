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

variable "site_domain" {
  description = "Dominio HTTPS de CloudFront del sitio web para callback y logout del cliente web (Requisito 4.3)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+\\.[a-z]{2,}$", var.site_domain))
    error_message = "site_domain debe ser un nombre de dominio válido sin esquema ni rutas."
  }
}
