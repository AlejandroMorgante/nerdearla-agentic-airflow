variable "config" {
  description = "Configuración compartida del workshop, definida en infra/config.yaml."
  type        = any
}

locals {
  config      = var.config
  project     = var.config.project
  agent_count = var.agent_image_tag == null ? 0 : 1
}

variable "repository_arn" { type = string }

variable "repository_url" { type = string }

variable "secret_arns" { type = map(string) }

variable "bucket_arn" { type = string }

variable "mwaa_arn" { type = string }

variable "task_log_arn" { type = string }

variable "mwaa_role_id" { type = string }

variable "kms_key_arn" { type = string }

variable "subnet_ids" { type = list(string) }

variable "vpc_id" { type = string }

variable "model_id" { type = string }

variable "agent_image_tag" { type = string }
