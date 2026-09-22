resource "aws_secretsmanager_secret" "integration" {
  for_each                = toset(["github", "slack"])
  name                    = "${local.project}/${each.key}"
  recovery_window_in_days = 0
}

# Airflow las consulta por nombre mediante SecretsManagerBackend.
resource "aws_secretsmanager_secret" "airflow_variable" {
  for_each                = var.airflow_variables
  name                    = "${local.project}/airflow/variables/${each.key}"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "airflow_variable" {
  for_each      = var.airflow_variables
  secret_id     = aws_secretsmanager_secret.airflow_variable[each.key].id
  secret_string = each.value
}
