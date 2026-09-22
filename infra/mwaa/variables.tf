variable "config" {
  description = "Configuración compartida del workshop, definida en infra/config.yaml."
  type        = any
}

locals {
  config  = var.config
  project = var.config.project
}

variable "bucket_arn" { type = string }

variable "kms_key_arn" { type = string }

variable "requirements_key" { type = string }

variable "requirements_version" { type = string }

variable "subnet_ids" { type = list(string) }

variable "vpc_id" { type = string }

variable "sales_input_arn" { type = string }
