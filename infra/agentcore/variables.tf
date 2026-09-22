variable "config" {
  description = "Configuración compartida del workshop, definida en infra/config.yaml."
  type        = any
}

locals {
  config      = var.config
  project     = var.config.project
  agent_count = 1
}

variable "repository_arn" { type = string }

variable "image_uri" { type = string }

variable "secret_arns" { type = map(string) }

variable "bucket_arn" { type = string }

variable "mwaa_arn" { type = string }

variable "task_log_arn" { type = string }

variable "mwaa_role_id" { type = string }

variable "kms_key_arn" { type = string }

variable "model_id" { type = string }


variable "sales_input_bucket" { type = string }
