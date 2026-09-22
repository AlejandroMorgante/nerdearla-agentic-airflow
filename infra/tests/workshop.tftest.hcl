mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
}

run "complete_workshop" {
  command = plan

  assert {
    condition     = output.endpoint_name == "workshop"
    error_message = "El primer plan debe incluir el Runtime sin configurar un tag manual."
  }
  assert {
    condition     = length(module.vpc.private_subnet_ids) == 2 && output.mwaa_environment_name == "nerdearla-agentic-airflow"
    error_message = "MWAA debe estar conectado a las dos subnets privadas del workshop."
  }
  assert {
    condition     = toset(keys(output.secret_arns)) == toset(["github", "slack"])
    error_message = "Los módulos deben reutilizar ambos secretos de integración."
  }
}
