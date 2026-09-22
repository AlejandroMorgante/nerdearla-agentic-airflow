variable "config" {
  description = "Configuración compartida del workshop, definida en infra/config.yaml."
  type        = any
}

locals {
  config  = var.config
  project = var.config.project
}
