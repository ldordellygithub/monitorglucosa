variable "project" {
  description = "Prefijo de nombres de recursos del proyecto."
  type        = string
  default     = "monitorglucosa"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,31}$", var.project))
    error_message = "project debe contener solo minúsculas, dígitos y guiones."
  }
}

variable "private_subnet_ids" {
  description = "Lista de IDs de subredes privadas (mínimo 2 AZs) para el grupo de subredes de Aurora."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Aurora requiere al menos 2 subredes privadas en distintas zonas de disponibilidad."
  }
}

variable "aurora_security_group_id" {
  description = "ID del grupo de seguridad exclusivo de Aurora."
  type        = string
}

variable "engine_version" {
  description = "Versión exacta de Aurora PostgreSQL 16 (≥ 16.4 para auto-pausa a 0 ACU; ADR 0002)."
  type        = string
  default     = "16.6"

  validation {
    condition     = can(regex("^16\\.([4-9]|[1-9]\\d+)$", var.engine_version))
    error_message = "engine_version debe ser Aurora PostgreSQL 16.4 o superior (ADR 0002, Requisito 5.2)."
  }
}

variable "database_name" {
  description = "Nombre de la base de datos inicial creada en Aurora."
  type        = string
  default     = "monitorglucosa"

  validation {
    condition     = can(regex("^[a-z_][a-z0-9_]{0,62}$", var.database_name))
    error_message = "database_name debe ser un identificador PostgreSQL en minúsculas."
  }
}

variable "master_username" {
  description = "Usuario maestro de Aurora (su contraseña la gestiona RDS en Secrets Manager; nunca en Terraform)."
  type        = string
  default     = "mg_admin"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{2,31}$", var.master_username)) && !contains(["postgres", "admin", "root"], var.master_username)
    error_message = "master_username debe ser un nombre válido y distinto de postgres/admin/root."
  }
}
