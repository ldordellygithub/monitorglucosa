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
    error_message = "Por ADR 0011 toda la red debe vivir exclusivamente en us-east-1."
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

variable "vpc_cidr" {
  description = "Bloque CIDR de la VPC privada (design.md: 10.20.0.0/16)."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr debe ser un bloque CIDR IPv4 válido."
  }
}

variable "private_subnets" {
  description = "Mapa de zonas de disponibilidad a bloques CIDR /24 privados (mínimo 2 AZs para Aurora)."
  type        = map(string)
  default = {
    "us-east-1a" = "10.20.1.0/24"
    "us-east-1b" = "10.20.2.0/24"
  }

  validation {
    condition     = length(var.private_subnets) >= 2 && alltrue([for az, cidr in var.private_subnets : startswith(az, "us-east-1") && can(cidrnetmask(cidr))])
    error_message = "Se requieren al menos 2 subredes privadas en us-east-1 con bloques CIDR válidos."
  }
}
