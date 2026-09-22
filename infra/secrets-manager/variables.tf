variable "config" {
  description = "Configuración compartida del workshop, definida en infra/config.yaml."
  type        = any
}

locals {
  config  = var.config
  project = var.config.project
}

variable "airflow_variables" {
  description = "Variables de Airflow resueltas por Terraform, sin carga manual en la UI."
  type        = map(string)
}
