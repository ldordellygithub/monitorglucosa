variable "account_id" {
  description = "ID de la cuenta AWS exclusiva de monitorglucosa (12 dígitos)."
  type        = string

  validation {
    condition     = can(regex("^\\d{12}$", var.account_id))
    error_message = "account_id debe tener exactamente 12 dígitos."
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
