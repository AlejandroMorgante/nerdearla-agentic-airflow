terraform {
  required_version = ">= 1.14.0, < 2.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.66.0"
    }
  }
}

provider "aws" {
  region = local.settings.region
  default_tags {
    tags = { Project = local.settings.project, Purpose = "workshop" }
  }
}

data "aws_caller_identity" "current" {}

locals {
  settings = yamldecode(file("${path.module}/config.yaml"))
  config   = merge(local.settings, { account = data.aws_caller_identity.current.account_id })
  model_id = yamldecode(file("${path.module}/../airflow-agent/config.yaml")).model.model_id
}

variable "agent_image_tag" {
  description = "Tag inmutable publicado en ECR. null permite crear primero ECR y MWAA."
  type        = string
  default     = null
  validation {
    condition     = var.agent_image_tag == null ? true : can(regex("^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$", var.agent_image_tag))
    error_message = "Usar un tag válido de ECR, por ejemplo v1."
  }
}

module "vpc" {
  source = "./vpc"
  config = local.config
}

module "s3" {
  source = "./s3"
  config = local.config
}

module "ecr" {
  source = "./ecr"
  config = local.config
}

module "secrets_manager" {
  source = "./secrets-manager"
  config = local.config
  airflow_variables = merge(
    {
      mwaa_environment_name = local.config.project
      sales_input_bucket    = module.s3.sales_input_bucket
      sales_glue_job        = module.glue.job_name
    },
    var.agent_image_tag == null ? {} : { agentcore_runtime_arn = module.agentcore.runtime_arn },
  )
}

module "kms" {
  source = "./kms"
  config = local.config
}

module "glue" {
  source           = "./glue"
  config           = local.config
  artifacts_bucket = module.s3.bucket_name
  input_bucket     = module.s3.sales_input_bucket
  output_bucket    = module.s3.sales_output_bucket
}

module "mwaa" {
  source               = "./mwaa"
  config               = local.config
  bucket_arn           = module.s3.bucket_arn
  kms_key_arn          = module.kms.key_arn
  sales_input_arn      = module.s3.sales_input_arn
  sales_job_arn        = module.glue.job_arn
  requirements_key     = module.s3.requirements_key
  requirements_version = module.s3.requirements_version
  vpc_id               = module.vpc.vpc_id
  subnet_ids           = module.vpc.private_subnet_ids
  # Esperar también las rutas y la política del bucket, no sólo sus IDs.
  depends_on = [module.vpc, module.s3]
}

module "agentcore" {
  source             = "./agentcore"
  config             = local.config
  model_id           = local.model_id
  agent_image_tag    = var.agent_image_tag
  repository_arn     = module.ecr.repository_arn
  repository_url     = module.ecr.repository_url
  secret_arns        = module.secrets_manager.secret_arns
  bucket_arn         = module.s3.bucket_arn
  kms_key_arn        = module.kms.key_arn
  mwaa_arn           = module.mwaa.environment_arn
  mwaa_role_id       = module.mwaa.role_id
  sales_input_bucket = module.s3.sales_input_bucket
  sales_job_arn      = module.glue.job_arn
  task_log_arn       = module.mwaa.task_log_arn
  vpc_id             = module.vpc.vpc_id
  subnet_ids         = module.vpc.private_subnet_ids
  depends_on         = [module.vpc]
}
