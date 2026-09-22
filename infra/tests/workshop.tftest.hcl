mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
}

run "foundation_before_image" {
  command = plan
  variables { agent_image_tag = null }

  assert {
    condition     = output.runtime_arn == null && output.endpoint_name == null
    error_message = "El primer despliegue debe funcionar sin una imagen publicada."
  }
  assert {
    condition     = length(module.vpc.private_subnet_ids) == 2 && output.mwaa_environment_name == "nerdearla-agentic-airflow"
    error_message = "MWAA debe estar conectado a las dos subnets privadas del workshop."
  }
  assert {
    condition     = toset(keys(output.secret_arns)) == toset(["github", "slack"])
    error_message = "Los módulos deben exponer ambos secretos para las integraciones."
  }
}

run "runtime_after_image" {
  command = plan
  variables { agent_image_tag = "v1" }

  assert {
    condition     = output.endpoint_name == "workshop"
    error_message = "La imagen debe habilitar el endpoint del Runtime."
  }
}

run "invalid_image_tag" {
  command = plan
  variables { agent_image_tag = "invalid tag" }
  expect_failures = [var.agent_image_tag]
}
